"""
LLM Provider Implementations
Production-ready providers for OpenAI, Anthropic, Ollama, Kimi, and DeepSeek.
"""

from abc import ABC, abstractmethod
from typing import Optional
import os


class LLMProvider(ABC):
    """Base class for LLM providers."""
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response from LLM.
        
        Args:
            prompt: Input prompt
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Generated text
        """
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: float = 60.0,
    ):
        """
        Initialize OpenAI provider.
        
        Args:
            api_key: OpenAI API key (or set OPENAI_API_KEY env var)
            model: Model name
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout seconds
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("OpenAI not installed. Run: pip install openai")
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not provided. Set OPENAI_API_KEY or pass api_key parameter")
        
        self.client = OpenAI(api_key=self.api_key, timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using OpenAI API."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens)
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {e}")


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: float = 60.0,
    ):
        """
        Initialize Anthropic provider.
        """
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError("Anthropic not installed. Run: pip install anthropic")
        
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key not provided. Set ANTHROPIC_API_KEY or pass api_key parameter")
        
        self.client = Anthropic(api_key=self.api_key, timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Anthropic API."""
        try:
            response = self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens)
            )
            return response.content[0].text
        except Exception as e:
            raise RuntimeError(f"Anthropic API call failed: {e}")


class OllamaProvider(LLMProvider):
    """Ollama provider for local models."""
    
    def __init__(
        self,
        model: str = "llama2",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.7,
        timeout: float = 120.0,
    ):
        """
        Initialize Ollama provider.
        """
        try:
            import requests
        except ImportError:
            raise ImportError("Requests not installed. Run: pip install requests")
        
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.temperature = temperature
        self.timeout = float(timeout)
        self.requests = requests
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Ollama API."""
        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": kwargs.get("temperature", self.temperature)}
            }
            response = self.requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()["response"]
        except Exception as e:
            raise RuntimeError(f"Ollama API call failed: {e}")


class KimiProvider(LLMProvider):
    """Kimi (Moonshot AI) provider."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "moonshot-v1-8k",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ):
        try:
            import requests
        except ImportError:
            raise ImportError("Requests not installed. Run: pip install requests")
        
        self.api_key = api_key or os.getenv("KIMI_API_KEY")
        if not self.api_key:
            raise ValueError("Kimi API key not provided. Set KIMI_API_KEY or pass api_key parameter")
        
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = float(timeout)
        self.requests = requests
        self.base_url = "https://api.moonshot.cn/v1"
    
    def generate(self, prompt: str, **kwargs) -> str:
        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": kwargs.get("temperature", self.temperature),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens)
            }
            response = self.requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Kimi API call failed: {e}")


class DeepSeekProvider(LLMProvider):
    """DeepSeek provider."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ):
        try:
            import requests
        except ImportError:
            raise ImportError("Requests not installed. Run: pip install requests")
        
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DeepSeek API key not provided. Set DEEPSEEK_API_KEY or pass api_key parameter")
        
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = float(timeout)
        self.requests = requests
        self.base_url = "https://api.deepseek.com/v1"
    
    def generate(self, prompt: str, **kwargs) -> str:
        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": kwargs.get("temperature", self.temperature),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens)
            }
            response = self.requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"DeepSeek API call failed: {e}")
