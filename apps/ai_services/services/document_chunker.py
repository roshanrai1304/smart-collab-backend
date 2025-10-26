"""
Document chunking service for Smart Collaborative Backend.

Handles intelligent document splitting for parallel processing and improved AI performance.
"""

import hashlib
import logging
import re
from typing import Dict, List, Tuple, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio

logger = logging.getLogger(__name__)


class DocumentChunk:
    """Represents a chunk of document content with metadata."""
    
    def __init__(self, content: str, start_pos: int, end_pos: int, chunk_type: str = "paragraph"):
        self.content = content
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.chunk_type = chunk_type
        self.word_count = len(content.split())
        self.char_count = len(content)
        self.hash = hashlib.md5(content.encode()).hexdigest()
        
    def __repr__(self):
        return f"DocumentChunk(type={self.chunk_type}, words={self.word_count}, chars={self.char_count})"


class DocumentChunker:
    """
    Intelligent document chunking service for parallel AI processing.
    
    Supports multiple chunking strategies:
    - Semantic chunking (by paragraphs, sections)
    - Fixed-size chunking with overlap
    - Sentence-based chunking
    - Hybrid chunking based on content type
    """
    
    def __init__(self, 
                 max_chunk_size: int = 2000,
                 overlap_size: int = 200,
                 min_chunk_size: int = 100):
        """
        Initialize document chunker.
        
        Args:
            max_chunk_size: Maximum characters per chunk
            overlap_size: Overlap between chunks for context preservation
            min_chunk_size: Minimum chunk size to avoid tiny fragments
        """
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size
        self.min_chunk_size = min_chunk_size
        
        # Patterns for different content structures
        self.section_pattern = re.compile(r'^#{1,6}\s+.+$', re.MULTILINE)
        self.paragraph_pattern = re.compile(r'\n\s*\n')
        self.sentence_pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')
        
    def chunk_document(self, content: str, strategy: str = "auto") -> List[DocumentChunk]:
        """
        Chunk document using specified strategy.
        
        Args:
            content: Document content to chunk
            strategy: Chunking strategy ('auto', 'semantic', 'fixed', 'sentence', 'hybrid')
            
        Returns:
            List of document chunks
        """
        if not content or len(content.strip()) < self.min_chunk_size:
            return [DocumentChunk(content, 0, len(content), "full")]
        
        # Auto-select strategy based on content
        if strategy == "auto":
            strategy = self._detect_optimal_strategy(content)
        
        # Apply chunking strategy
        if strategy == "semantic":
            return self._semantic_chunking(content)
        elif strategy == "fixed":
            return self._fixed_size_chunking(content)
        elif strategy == "sentence":
            return self._sentence_chunking(content)
        elif strategy == "hybrid":
            return self._hybrid_chunking(content)
        else:
            return self._semantic_chunking(content)  # Default fallback
    
    def _detect_optimal_strategy(self, content: str) -> str:
        """
        Detect the optimal chunking strategy based on content characteristics.
        
        Args:
            content: Document content
            
        Returns:
            Optimal chunking strategy
        """
        # Check for markdown structure
        if self.section_pattern.search(content):
            return "semantic"
        
        # Check content length
        if len(content) < self.max_chunk_size:
            return "semantic"  # No chunking needed, but use semantic for consistency
        
        # Check paragraph structure
        paragraphs = self.paragraph_pattern.split(content)
        avg_paragraph_length = sum(len(p) for p in paragraphs) / len(paragraphs) if paragraphs else 0
        
        if avg_paragraph_length > self.max_chunk_size:
            return "sentence"  # Long paragraphs need sentence-level chunking
        elif len(paragraphs) > 10:
            return "semantic"  # Well-structured content
        else:
            return "fixed"  # Unstructured content
    
    def _semantic_chunking(self, content: str) -> List[DocumentChunk]:
        """
        Chunk document by semantic boundaries (sections, paragraphs).
        
        Args:
            content: Document content
            
        Returns:
            List of semantic chunks
        """
        chunks = []
        
        # First, try to split by sections (markdown headers)
        sections = self._split_by_sections(content)
        
        for section_content, section_start in sections:
            if len(section_content) <= self.max_chunk_size:
                # Section fits in one chunk
                chunks.append(DocumentChunk(
                    section_content, 
                    section_start, 
                    section_start + len(section_content),
                    "section"
                ))
            else:
                # Section too large, split by paragraphs
                para_chunks = self._split_by_paragraphs(section_content, section_start)
                chunks.extend(para_chunks)
        
        return chunks
    
    def _split_by_sections(self, content: str) -> List[Tuple[str, int]]:
        """Split content by markdown sections."""
        sections = []
        section_matches = list(self.section_pattern.finditer(content))
        
        if not section_matches:
            return [(content, 0)]
        
        # Add content before first section
        if section_matches[0].start() > 0:
            sections.append((content[:section_matches[0].start()], 0))
        
        # Add sections
        for i, match in enumerate(section_matches):
            start_pos = match.start()
            end_pos = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(content)
            section_content = content[start_pos:end_pos]
            sections.append((section_content, start_pos))
        
        return sections
    
    def _split_by_paragraphs(self, content: str, base_offset: int = 0) -> List[DocumentChunk]:
        """Split content by paragraphs with size limits."""
        chunks = []
        paragraphs = self.paragraph_pattern.split(content)
        
        current_chunk = ""
        current_start = base_offset
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            # Check if adding this paragraph would exceed max size
            if current_chunk and len(current_chunk) + len(paragraph) > self.max_chunk_size:
                # Save current chunk
                chunks.append(DocumentChunk(
                    current_chunk.strip(),
                    current_start,
                    current_start + len(current_chunk),
                    "paragraph_group"
                ))
                
                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk)
                current_chunk = overlap_text + paragraph
                current_start = current_start + len(current_chunk) - len(overlap_text)
            else:
                # Add paragraph to current chunk
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
        
        # Add final chunk
        if current_chunk:
            chunks.append(DocumentChunk(
                current_chunk.strip(),
                current_start,
                current_start + len(current_chunk),
                "paragraph_group"
            ))
        
        return chunks
    
    def _fixed_size_chunking(self, content: str) -> List[DocumentChunk]:
        """
        Chunk document into fixed-size pieces with overlap.
        
        Args:
            content: Document content
            
        Returns:
            List of fixed-size chunks
        """
        chunks = []
        start = 0
        
        while start < len(content):
            end = min(start + self.max_chunk_size, len(content))
            
            # Try to break at word boundary
            if end < len(content):
                # Look for last space within reasonable distance
                for i in range(end, max(end - 100, start), -1):
                    if content[i].isspace():
                        end = i
                        break
            
            chunk_content = content[start:end].strip()
            if chunk_content:
                chunks.append(DocumentChunk(
                    chunk_content,
                    start,
                    end,
                    "fixed"
                ))
            
            # Move start position with overlap
            start = max(start + self.max_chunk_size - self.overlap_size, end)
        
        return chunks
    
    def _sentence_chunking(self, content: str) -> List[DocumentChunk]:
        """
        Chunk document by sentences, grouping to optimal sizes.
        
        Args:
            content: Document content
            
        Returns:
            List of sentence-based chunks
        """
        chunks = []
        sentences = self.sentence_pattern.split(content)
        
        current_chunk = ""
        current_start = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # Check if adding this sentence would exceed max size
            if current_chunk and len(current_chunk) + len(sentence) > self.max_chunk_size:
                # Save current chunk
                chunks.append(DocumentChunk(
                    current_chunk.strip(),
                    current_start,
                    current_start + len(current_chunk),
                    "sentence_group"
                ))
                
                # Start new chunk
                current_chunk = sentence
                current_start = current_start + len(current_chunk)
            else:
                # Add sentence to current chunk
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
        
        # Add final chunk
        if current_chunk:
            chunks.append(DocumentChunk(
                current_chunk.strip(),
                current_start,
                current_start + len(current_chunk),
                "sentence_group"
            ))
        
        return chunks
    
    def _hybrid_chunking(self, content: str) -> List[DocumentChunk]:
        """
        Hybrid chunking that combines multiple strategies based on content structure.
        
        Args:
            content: Document content
            
        Returns:
            List of hybrid chunks
        """
        # Start with semantic chunking
        semantic_chunks = self._semantic_chunking(content)
        
        # Further split large chunks using sentence chunking
        final_chunks = []
        for chunk in semantic_chunks:
            if chunk.char_count > self.max_chunk_size:
                sentence_chunks = self._sentence_chunking(chunk.content)
                # Update positions relative to original document
                for sc in sentence_chunks:
                    sc.start_pos += chunk.start_pos
                    sc.end_pos += chunk.start_pos
                    sc.chunk_type = "hybrid"
                final_chunks.extend(sentence_chunks)
            else:
                chunk.chunk_type = "hybrid"
                final_chunks.append(chunk)
        
        return final_chunks
    
    def _get_overlap_text(self, text: str) -> str:
        """Get overlap text from the end of a chunk."""
        if len(text) <= self.overlap_size:
            return text
        
        # Try to get overlap at sentence boundary
        overlap_start = len(text) - self.overlap_size
        sentences = self.sentence_pattern.split(text[overlap_start:])
        
        if len(sentences) > 1:
            # Start from the beginning of the last complete sentence
            return sentences[-2] + " " + sentences[-1]
        else:
            # Fallback to character-based overlap
            return text[-self.overlap_size:]
    
    def get_chunk_statistics(self, chunks: List[DocumentChunk]) -> Dict[str, Any]:
        """
        Get statistics about the chunking results.
        
        Args:
            chunks: List of document chunks
            
        Returns:
            Dictionary with chunking statistics
        """
        if not chunks:
            return {}
        
        total_chars = sum(chunk.char_count for chunk in chunks)
        total_words = sum(chunk.word_count for chunk in chunks)
        
        return {
            "total_chunks": len(chunks),
            "total_characters": total_chars,
            "total_words": total_words,
            "avg_chunk_size": total_chars / len(chunks),
            "avg_words_per_chunk": total_words / len(chunks),
            "chunk_types": {chunk_type: len([c for c in chunks if c.chunk_type == chunk_type]) 
                           for chunk_type in set(chunk.chunk_type for chunk in chunks)},
            "size_distribution": {
                "small": len([c for c in chunks if c.char_count < 500]),
                "medium": len([c for c in chunks if 500 <= c.char_count < 1500]),
                "large": len([c for c in chunks if c.char_count >= 1500])
            }
        }


# Global chunker instance
_document_chunker = None


def get_document_chunker() -> DocumentChunker:
    """
    Get singleton DocumentChunker instance.
    
    Returns:
        DocumentChunker instance
    """
    global _document_chunker
    if _document_chunker is None:
        _document_chunker = DocumentChunker()
    return _document_chunker
