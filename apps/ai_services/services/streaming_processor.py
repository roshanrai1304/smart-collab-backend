"""
Streaming AI processing service for Smart Collaborative Backend.

Provides real-time result delivery and progressive enhancement capabilities.
"""

import asyncio
import json
import logging
import re
import time
from typing import Dict, List, Any, Optional, AsyncGenerator, Callable
from dataclasses import dataclass, asdict
from enum import Enum

from django.core.cache import cache
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


class ProcessingStage(Enum):
    """Stages of AI processing for streaming updates."""
    STARTED = "started"
    CHUNKING = "chunking"
    CLASSIFICATION = "classification"
    TAGGING = "tagging"
    SUMMARIZATION = "summarization"
    EMBEDDING = "embedding"
    ANALYSIS = "analysis"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StreamingResult:
    """Container for streaming AI processing results."""
    stage: ProcessingStage
    document_id: str
    progress: float  # 0.0 to 1.0
    data: Dict[str, Any]
    timestamp: float
    processing_time_ms: Optional[int] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['stage'] = self.stage.value
        return result


class StreamingProcessor:
    """
    Streaming AI processor that delivers results as they become available.
    
    Provides real-time updates through WebSocket connections and progressive
    enhancement of AI analysis results.
    """
    
    def __init__(self):
        self.channel_layer = get_channel_layer()
        self.active_streams = {}  # Track active streaming sessions
        
        # Processing stage weights for progress calculation
        self.stage_weights = {
            ProcessingStage.STARTED: 0.0,
            ProcessingStage.CHUNKING: 0.1,
            ProcessingStage.CLASSIFICATION: 0.2,
            ProcessingStage.TAGGING: 0.4,
            ProcessingStage.SUMMARIZATION: 0.7,
            ProcessingStage.EMBEDDING: 0.9,
            ProcessingStage.ANALYSIS: 0.95,
            ProcessingStage.COMPLETED: 1.0
        }
    
    async def stream_document_processing(
        self, 
        document_id: str, 
        content: str,
        user_id: str,
        websocket_group: str = None,
        callback: Callable[[StreamingResult], None] = None
    ) -> AsyncGenerator[StreamingResult, None]:
        """
        Stream AI processing results in real-time.
        
        Args:
            document_id: Document ID being processed
            content: Document content
            user_id: User requesting the processing
            websocket_group: WebSocket group for real-time updates
            callback: Optional callback function for each result
            
        Yields:
            StreamingResult objects as processing progresses
        """
        start_time = time.time()
        session_id = f"{document_id}_{user_id}_{int(start_time)}"
        
        try:
            # Register streaming session
            self.active_streams[session_id] = {
                'document_id': document_id,
                'user_id': user_id,
                'start_time': start_time,
                'websocket_group': websocket_group
            }
            
            # Stage 1: Started
            result = StreamingResult(
                stage=ProcessingStage.STARTED,
                document_id=document_id,
                progress=0.0,
                data={'session_id': session_id, 'content_length': len(content)},
                timestamp=time.time()
            )
            yield result
            await self._send_update(result, websocket_group, callback)
            
            # Stage 2: Document Chunking (if needed)
            if len(content) > 2000:
                chunk_start = time.time()
                from apps.ai_services.services.document_chunker import get_document_chunker
                
                chunker = get_document_chunker()
                chunks = chunker.chunk_document(content, strategy="auto")
                chunk_stats = chunker.get_chunk_statistics(chunks)
                
                result = StreamingResult(
                    stage=ProcessingStage.CHUNKING,
                    document_id=document_id,
                    progress=self.stage_weights[ProcessingStage.CHUNKING],
                    data={
                        'chunks_created': len(chunks),
                        'chunking_strategy': 'auto',
                        'chunk_statistics': chunk_stats
                    },
                    timestamp=time.time(),
                    processing_time_ms=int((time.time() - chunk_start) * 1000)
                )
                yield result
                await self._send_update(result, websocket_group, callback)
            else:
                chunks = None
            
            # Stage 3: Fast Classification (Content Type Detection)
            classify_start = time.time()
            from apps.ai_services.services.ollama_client import get_ollama_client
            
            client = get_ollama_client()
            content_type = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: client.detect_content_type(content[:1000])  # Use first 1000 chars for speed
            )
            
            result = StreamingResult(
                stage=ProcessingStage.CLASSIFICATION,
                document_id=document_id,
                progress=self.stage_weights[ProcessingStage.CLASSIFICATION],
                data={'content_type': content_type},
                timestamp=time.time(),
                processing_time_ms=int((time.time() - classify_start) * 1000)
            )
            yield result
            await self._send_update(result, websocket_group, callback)
            
            # Stage 4: Fast Tagging
            tag_start = time.time()
            tags = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.extract_tags(content, max_tags=8)
            )
            
            result = StreamingResult(
                stage=ProcessingStage.TAGGING,
                document_id=document_id,
                progress=self.stage_weights[ProcessingStage.TAGGING],
                data={'tags': tags, 'tag_count': len(tags)},
                timestamp=time.time(),
                processing_time_ms=int((time.time() - tag_start) * 1000)
            )
            yield result
            await self._send_update(result, websocket_group, callback)
            
            # Stage 5: Summarization (parallel with chunked processing if applicable)
            summary_start = time.time()
            
            if chunks and len(chunks) > 1:
                # Process chunks in parallel for large documents
                summary = await self._parallel_summarization(chunks, client)
            else:
                # Direct summarization for smaller documents
                summary = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.summarize_document(content, max_length=200)
                )
            
            result = StreamingResult(
                stage=ProcessingStage.SUMMARIZATION,
                document_id=document_id,
                progress=self.stage_weights[ProcessingStage.SUMMARIZATION],
                data={
                    'summary': summary,
                    'summary_length': len(summary.split()) if summary else 0,
                    'processing_method': 'parallel' if chunks and len(chunks) > 1 else 'direct'
                },
                timestamp=time.time(),
                processing_time_ms=int((time.time() - summary_start) * 1000)
            )
            yield result
            await self._send_update(result, websocket_group, callback)
            
            # Stage 6: Embedding Generation
            embed_start = time.time()
            embedding = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.generate_embeddings(content[:8000])  # Limit for embedding model
            )
            
            result = StreamingResult(
                stage=ProcessingStage.EMBEDDING,
                document_id=document_id,
                progress=self.stage_weights[ProcessingStage.EMBEDDING],
                data={
                    'embedding_dimensions': len(embedding) if embedding else 0,
                    'embedding_generated': bool(embedding)
                },
                timestamp=time.time(),
                processing_time_ms=int((time.time() - embed_start) * 1000)
            )
            yield result
            await self._send_update(result, websocket_group, callback)
            
            # Stage 7: Additional Analysis (sentiment, key points)
            analysis_start = time.time()
            
            # Run sentiment analysis and key point extraction in parallel
            sentiment_task = asyncio.get_event_loop().run_in_executor(
                None, lambda: client.analyze_sentiment(content)
            )
            
            # For key points, we'll do a simplified version for speed
            key_points_task = asyncio.get_event_loop().run_in_executor(
                None, lambda: self._extract_key_points_fast(content, client)
            )
            
            sentiment_score, key_points = await asyncio.gather(sentiment_task, key_points_task)
            
            result = StreamingResult(
                stage=ProcessingStage.ANALYSIS,
                document_id=document_id,
                progress=self.stage_weights[ProcessingStage.ANALYSIS],
                data={
                    'sentiment_score': sentiment_score,
                    'key_points': key_points,
                    'analysis_complete': True
                },
                timestamp=time.time(),
                processing_time_ms=int((time.time() - analysis_start) * 1000)
            )
            yield result
            await self._send_update(result, websocket_group, callback)
            
            # Stage 8: Completed
            total_time = int((time.time() - start_time) * 1000)
            result = StreamingResult(
                stage=ProcessingStage.COMPLETED,
                document_id=document_id,
                progress=1.0,
                data={
                    'total_processing_time_ms': total_time,
                    'session_id': session_id,
                    'stages_completed': len(self.stage_weights) - 1
                },
                timestamp=time.time(),
                processing_time_ms=total_time
            )
            yield result
            await self._send_update(result, websocket_group, callback)
            
        except Exception as e:
            logger.error(f"Streaming processing failed for document {document_id}: {str(e)}")
            
            error_result = StreamingResult(
                stage=ProcessingStage.FAILED,
                document_id=document_id,
                progress=0.0,
                data={'error_details': str(e)},
                timestamp=time.time(),
                error=str(e)
            )
            yield error_result
            await self._send_update(error_result, websocket_group, callback)
        
        finally:
            # Clean up streaming session
            if session_id in self.active_streams:
                del self.active_streams[session_id]
    
    async def _parallel_summarization(self, chunks, client) -> str:
        """
        Perform parallel summarization of document chunks.
        
        Args:
            chunks: List of document chunks
            client: Ollama client instance
            
        Returns:
            Combined summary
        """
        # Summarize chunks in parallel (limit concurrency to avoid overwhelming the model)
        max_concurrent = 3
        chunk_summaries = []
        
        async def summarize_chunk(chunk):
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.summarize_document(chunk.content, max_length=100)
            )
        
        # Process chunks in batches
        for i in range(0, len(chunks), max_concurrent):
            batch = chunks[i:i + max_concurrent]
            batch_summaries = await asyncio.gather(*[summarize_chunk(chunk) for chunk in batch])
            chunk_summaries.extend(batch_summaries)
        
        # Combine chunk summaries into final summary
        combined_content = " ".join(chunk_summaries)
        final_summary = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.summarize_document(combined_content, max_length=200)
        )
        
        return final_summary
    
    def _extract_key_points_fast(self, content: str, client) -> List[Dict[str, Any]]:
        """
        Fast key point extraction using simplified approach.
        
        Args:
            content: Document content
            client: Ollama client
            
        Returns:
            List of key points
        """
        # For speed, extract key points from first part of content
        sample_content = content[:2000] if len(content) > 2000 else content
        
        try:
            # Use a simpler prompt for faster processing
            system_prompt = "Extract 3-5 key points from this text. Return as a simple numbered list."
            prompt = f"Key points from this text:\n\n{sample_content}\n\nKey points:"
            
            response = client.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=200,
                temperature=0.3
            )
            
            # Parse response into structured format
            lines = response.strip().split('\n')
            key_points = []
            
            for i, line in enumerate(lines[:5]):  # Limit to 5 points
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith('-') or line.startswith('•')):
                    # Clean up the line
                    point = re.sub(r'^[\d\-•.\s]+', '', line).strip()
                    if point:
                        key_points.append({
                            'point': point,
                            'importance': max(1, 5 - i)  # Decreasing importance
                        })
            
            return key_points
            
        except Exception as e:
            logger.warning(f"Fast key point extraction failed: {str(e)}")
            return []
    
    async def _send_update(
        self, 
        result: StreamingResult, 
        websocket_group: str = None,
        callback: Callable[[StreamingResult], None] = None
    ):
        """
        Send update through WebSocket and/or callback.
        
        Args:
            result: Streaming result to send
            websocket_group: WebSocket group name
            callback: Optional callback function
        """
        # Send via callback if provided
        if callback:
            try:
                callback(result)
            except Exception as e:
                logger.error(f"Callback error: {str(e)}")
        
        # Send via WebSocket if group provided
        if websocket_group and self.channel_layer:
            try:
                await self.channel_layer.group_send(
                    websocket_group,
                    {
                        'type': 'ai_processing_update',
                        'data': result.to_dict()
                    }
                )
            except Exception as e:
                logger.error(f"WebSocket send error: {str(e)}")
        
        # Cache latest result for polling clients
        cache_key = f"ai_stream:{result.document_id}:latest"
        cache.set(cache_key, result.to_dict(), timeout=300)  # 5 minutes
    
    def get_stream_status(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current streaming status for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            Current status or None if not found
        """
        cache_key = f"ai_stream:{document_id}:latest"
        return cache.get(cache_key)
    
    def get_active_streams(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about currently active streaming sessions.
        
        Returns:
            Dictionary of active streaming sessions
        """
        current_time = time.time()
        active = {}
        
        for session_id, session_info in self.active_streams.items():
            duration = current_time - session_info['start_time']
            active[session_id] = {
                **session_info,
                'duration_seconds': duration,
                'status': 'active' if duration < 300 else 'stale'  # 5 minute timeout
            }
        
        return active
    
    def cancel_stream(self, document_id: str, user_id: str) -> bool:
        """
        Cancel an active streaming session.
        
        Args:
            document_id: Document ID
            user_id: User ID
            
        Returns:
            True if session was cancelled, False if not found
        """
        sessions_to_remove = []
        
        for session_id, session_info in self.active_streams.items():
            if (session_info['document_id'] == document_id and 
                session_info['user_id'] == user_id):
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del self.active_streams[session_id]
        
        return len(sessions_to_remove) > 0


# Global streaming processor instance
_streaming_processor = None


def get_streaming_processor() -> StreamingProcessor:
    """
    Get singleton StreamingProcessor instance.
    
    Returns:
        StreamingProcessor instance
    """
    global _streaming_processor
    if _streaming_processor is None:
        _streaming_processor = StreamingProcessor()
    return _streaming_processor
