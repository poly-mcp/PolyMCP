#!/usr/bin/env python3
"""
Text Analysis MCP Tools
Production-ready tools for text processing and analysis.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def summarize(text: str, max_length: int = 50) -> str:
    """
    Summarize text by truncating to specified length.
    
    Args:
        text: The text to summarize
        max_length: Maximum length of the summary
        
    Returns:
        Summarized text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length].strip() + "..."


def analyze_sentiment(text: str) -> str:
    """
    Analyze sentiment of text using keyword matching.
    
    Args:
        text: The text to analyze
        
    Returns:
        Sentiment classification: positive, negative, or neutral
    """
    positive_words = ['good', 'great', 'excellent', 'amazing', 'wonderful', 'love', 'best', 'fantastic']
    negative_words = ['bad', 'terrible', 'awful', 'worst', 'hate', 'poor', 'disappointing', 'horrible']
    
    text_lower = text.lower()
    
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    if positive_count > negative_count:
        return "positive"
    elif negative_count > positive_count:
        return "negative"
    else:
        return "neutral"


def word_count(text: str) -> int:
    """
    Count the number of words in text.
    
    Args:
        text: The text to count words in
        
    Returns:
        Number of words
    """
    return len(text.split())


def main():
    """Run MCP server with text analysis tools."""
    try:
        from polymcp import expose_tools
        import uvicorn
        
        app = expose_tools(
            tools=[summarize, analyze_sentiment, word_count],
            title="Text Analysis MCP Server",
            description="MCP server for text processing and analysis",
            version="1.0.0"
        )
        
        print("\n" + "="*60)
        print("🚀 Text Analysis MCP Server")
        print("="*60)
        print("\nAvailable tools:")
        print("  • summarize - Summarize text")
        print("  • analyze_sentiment - Analyze text sentiment")
        print("  • word_count - Count words in text")
        print("\nServer: http://localhost:8000")
        print("API Docs: http://localhost:8000/docs")
        print("List tools: http://localhost:8000/mcp/list_tools")
        print("\nPress Ctrl+C to stop")
        print("="*60 + "\n")
        
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    
    except KeyboardInterrupt:
        print("\n\nServer stopped.")
    except ImportError as e:
        print(f"\nError: {e}")
        print("\nPlease install dependencies:")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
