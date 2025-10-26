"""
Ollama client service for Smart Collaborative Backend.

Provides a clean interface to interact with Ollama API for:
- Text generation and completion
- Document summarization
- Embedding generation
- Content analysis
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any
import httpx
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class OllamaClientError(Exception):
    """Custom exception for Ollama client errors."""
    pass


class OllamaClient:
    """
    Client for interacting with Ollama API.
    Handles model management, text generation, and embeddings.
    """

    def __init__(self, base_url: str = None, timeout: int = 120):
        """
        Initialize Ollama client.
        
        Args:
            base_url: Ollama server URL (defaults to settings or localhost)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434')
        self.timeout = timeout
        
        # Multi-model strategy configuration
        self.default_model = getattr(settings, 'OLLAMA_DEFAULT_MODEL', 'qwen2.5:7b')
        self.embedding_model = getattr(settings, 'OLLAMA_EMBEDDING_MODEL', 'qwen2.5:7b')
        self.summarization_model = getattr(settings, 'OLLAMA_SUMMARIZATION_MODEL', 'qwen2.5:7b')
        self.tagging_model = getattr(settings, 'OLLAMA_TAGGING_MODEL', 'mistral:latest')
        self.classification_model = getattr(settings, 'OLLAMA_CLASSIFICATION_MODEL', 'mistral:latest')
        self.analysis_model = getattr(settings, 'OLLAMA_ANALYSIS_MODEL', 'qwen2.5:7b')
        
        # Model performance profiles
        self.model_profiles = {
            'fast': self.tagging_model,      # For quick tasks like tagging, classification
            'balanced': self.default_model,   # For general tasks
            'quality': self.summarization_model,  # For high-quality summaries
            'analysis': self.analysis_model   # For deep analysis tasks
        }
        
        # Remove trailing slash
        self.base_url = self.base_url.rstrip('/')
    
    def get_optimal_model(self, task_type: str, content_length: int = 0) -> str:
        """
        Get the optimal model for a specific task based on content and requirements.
        
        Args:
            task_type: Type of task ('summarization', 'tagging', 'classification', 'analysis', 'embedding')
            content_length: Length of content to process
            
        Returns:
            Model name to use for the task
        """
        # For very long content, prefer faster models
        if content_length > 10000:
            if task_type in ['tagging', 'classification']:
                return self.model_profiles['fast']
            elif task_type == 'summarization':
                return self.model_profiles['balanced']  # Balance speed vs quality for long content
        
        # Task-specific model selection
        model_mapping = {
            'summarization': self.summarization_model,
            'tagging': self.tagging_model,
            'classification': self.classification_model,
            'analysis': self.analysis_model,
            'embedding': self.embedding_model,
            'sentiment': self.classification_model,  # Fast model for sentiment
            'content_type': self.classification_model,
        }
        
        return model_mapping.get(task_type, self.default_model)
        
    async def _make_request(self, endpoint: str, data: Dict[str, Any] = None, method: str = "POST") -> Dict[str, Any]:
        """
        Make HTTP request to Ollama API.
        
        Args:
            endpoint: API endpoint
            data: Request payload (for POST requests)
            method: HTTP method (GET or POST)
            
        Returns:
            Response data
            
        Raises:
            OllamaClientError: If request fails
        """
        url = f"{self.base_url}/{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url)
                else:
                    response = await client.post(url, json=data)
                response.raise_for_status()
                return response.json()
                
        except httpx.TimeoutException:
            raise OllamaClientError(f"Request timeout after {self.timeout} seconds")
        except httpx.HTTPStatusError as e:
            raise OllamaClientError(f"HTTP error {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise OllamaClientError(f"Request failed: {str(e)}")

    def _make_sync_request(self, endpoint: str, data: Dict[str, Any] = None, method: str = "POST") -> Dict[str, Any]:
        """
        Make synchronous HTTP request to Ollama API.
        
        Args:
            endpoint: API endpoint
            data: Request payload (for POST requests)
            method: HTTP method (GET or POST)
            
        Returns:
            Response data
            
        Raises:
            OllamaClientError: If request fails
        """
        url = f"{self.base_url}/{endpoint}"
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                if method.upper() == "GET":
                    response = client.get(url)
                else:
                    response = client.post(url, json=data)
                response.raise_for_status()
                return response.json()
                
        except httpx.TimeoutException:
            raise OllamaClientError(f"Request timeout after {self.timeout} seconds")
        except httpx.HTTPStatusError as e:
            raise OllamaClientError(f"HTTP error {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise OllamaClientError(f"Request failed: {str(e)}")

    def generate_text(
        self, 
        prompt: str, 
        model: str = None, 
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system_prompt: str = None
    ) -> str:
        """
        Generate text using Ollama.
        
        Args:
            prompt: Input prompt
            model: Model name (defaults to default_model)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system_prompt: System prompt for context
            
        Returns:
            Generated text
            
        Raises:
            OllamaClientError: If generation fails
        """
        model = model or self.default_model
        
        # Build messages format for chat models
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        data = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            }
        }
        
        start_time = time.time()
        
        try:
            response = self._make_sync_request("api/chat", data)
            
            # Log performance metrics
            duration = time.time() - start_time
            logger.info(f"Text generation completed in {duration:.2f}s using {model}")
            
            if "message" in response and "content" in response["message"]:
                return response["message"]["content"].strip()
            else:
                raise OllamaClientError("Invalid response format from Ollama")
                
        except Exception as e:
            logger.error(f"Text generation failed: {str(e)}")
            raise

    def generate_embeddings(self, text: str, model: str = None, dimensions: int = None) -> List[float]:
        """
        Generate embeddings for text using qwen3-embedding:8b.
        
        Args:
            text: Input text
            model: Embedding model name (defaults to qwen3-embedding:8b)
            dimensions: Output dimensions (32-4096 for qwen3-embedding:8b)
            
        Returns:
            Embedding vector with specified dimensions
            
        Raises:
            OllamaClientError: If embedding generation fails
        """
        model = model or self.embedding_model
        
        # Set default dimensions based on settings
        if dimensions is None:
            from django.conf import settings
            dimensions = getattr(settings, 'EMBEDDING_DIMENSIONS', 4096)
        
        # Check cache first (include dimensions in cache key)
        cache_key = f"embedding:{model}:{dimensions}:{hash(text)}"
        cached_embedding = cache.get(cache_key)
        if cached_embedding:
            return cached_embedding
        
        data = {
            "model": model,
            "prompt": text
        }
        
        # Add dimensions parameter for qwen3-embedding models
        if "qwen3-embedding" in model.lower():
            data["options"] = {
                "embedding_size": dimensions
            }
        
        start_time = time.time()
        
        try:
            response = self._make_sync_request("api/embeddings", data)
            
            # Log performance metrics
            duration = time.time() - start_time
            logger.info(f"Embedding generation completed in {duration:.2f}s using {model}")
            
            if "embedding" in response:
                embedding = response["embedding"]
                
                # Cache the embedding for 24 hours
                cache.set(cache_key, embedding, 60 * 60 * 24)
                
                return embedding
            else:
                raise OllamaClientError("Invalid embedding response format from Ollama")
                
        except Exception as e:
            logger.error(f"Embedding generation failed: {str(e)}")
            raise

    def summarize_document(
        self, 
        content: str, 
        max_length: int = 200,
        model: str = None
    ) -> str:
        """
        Generate document summary using the best model for summarization.
        
        Args:
            content: Document content
            max_length: Maximum summary length in words
            model: Model to use for summarization (defaults to summarization_model)
            
        Returns:
            Document summary
        """
        model = model or self.summarization_model
        
        system_prompt = f"""You are an expert at summarizing documents. Create a concise, informative summary that captures the key points and main ideas. Keep the summary under {max_length} words while maintaining accuracy and clarity."""
        
        prompt = f"""Please summarize the following document:

{content}

Summary:"""

        try:
            summary = self.generate_text(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                max_tokens=max_length * 2,  # Rough token estimate
                temperature=0.3  # Lower temperature for more focused summaries
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Document summarization failed: {str(e)}")
            raise

    def extract_tags(
        self, 
        content: str, 
        max_tags: int = 10,
        model: str = None
    ) -> List[str]:
        """
        Extract relevant tags from content using fast tagging model.
        
        Args:
            content: Document content
            max_tags: Maximum number of tags to extract
            model: Model to use for tag extraction (defaults to tagging_model)
            
        Returns:
            List of extracted tags
        """
        model = model or self.tagging_model
        
        system_prompt = f"""You are an expert at analyzing content and extracting relevant tags. Generate up to {max_tags} concise, relevant tags that best describe the content. Return only the tags as a comma-separated list, no explanations."""
        
        prompt = f"""Analyze the following content and extract the most relevant tags:

{content}

Tags:"""

        try:
            response = self.generate_text(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                max_tokens=100,
                temperature=0.3
            )
            
            # Parse tags from response
            tags = [tag.strip() for tag in response.split(',') if tag.strip()]
            
            # Clean and filter tags
            cleaned_tags = []
            for tag in tags[:max_tags]:
                # Remove quotes and extra whitespace
                tag = tag.strip('"\'').strip()
                if tag and len(tag) > 1:
                    cleaned_tags.append(tag.lower())
            
            return cleaned_tags
            
        except Exception as e:
            logger.error(f"Tag extraction failed: {str(e)}")
            raise

    def analyze_sentiment(self, content: str, model: str = None) -> float:
        """
        Analyze sentiment of content.
        
        Args:
            content: Text to analyze
            model: Model to use for analysis
            
        Returns:
            Sentiment score between -1.0 (negative) and 1.0 (positive)
        """
        model = model or self.default_model
        
        system_prompt = """You are an expert at sentiment analysis. Analyze the sentiment of the given text and return a single number between -1.0 (very negative) and 1.0 (very positive), where 0.0 is neutral. Return only the number, no explanations."""
        
        prompt = f"""Analyze the sentiment of this text:

{content}

Sentiment score:"""

        try:
            response = self.generate_text(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                max_tokens=10,
                temperature=0.1
            )
            
            # Extract numeric score
            try:
                score = float(response.strip())
                # Clamp to valid range
                return max(-1.0, min(1.0, score))
            except ValueError:
                logger.warning(f"Could not parse sentiment score: {response}")
                return 0.0
                
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {str(e)}")
            return 0.0

    def detect_content_type(self, content: str, model: str = None) -> str:
        """
        Detect the type/category of content using fast classification model.
        
        Args:
            content: Document content
            model: Model to use for detection (defaults to classification_model)
            
        Returns:
            Detected content type
        """
        model = model or self.classification_model
        
        content_types = [
            "article", "report", "meeting_notes", "proposal", 
            "technical_doc", "presentation", "other"
        ]
        
        system_prompt = f"""You are an expert at classifying document types. Analyze the content and classify it into one of these categories: {', '.join(content_types)}. Return only the category name, no explanations."""
        
        prompt = f"""Classify this document content:

{content}

Document type:"""

        try:
            response = self.generate_text(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                max_tokens=20,
                temperature=0.1
            )
            
            detected_type = response.strip().lower()
            
            # Validate against known types
            if detected_type in content_types:
                return detected_type
            else:
                return "other"
                
        except Exception as e:
            logger.error(f"Content type detection failed: {str(e)}")
            return "other"

    def health_check(self) -> bool:
        """
        Check if Ollama server is healthy and responsive.
        
        Returns:
            True if server is healthy, False otherwise
        """
        try:
            # Simple health check - try to list models
            response = self._make_sync_request("api/tags", method="GET")
            return "models" in response
            
        except Exception as e:
            logger.error(f"Ollama health check failed: {str(e)}")
            return False

    def list_models(self) -> List[Dict[str, Any]]:
        """
        List available models on Ollama server.
        
        Returns:
            List of available models with metadata
        """
        try:
            response = self._make_sync_request("api/tags", method="GET")
            return response.get("models", [])
            
        except Exception as e:
            logger.error(f"Failed to list models: {str(e)}")
            return []


# Global client instance
_ollama_client = None


def get_ollama_client() -> OllamaClient:
    """
    Get singleton Ollama client instance.
    
    Returns:
        OllamaClient instance
    """
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client
