#!/usr/bin/env python3
"""
Multi-Server Setup Example
Production example demonstrating multiple MCP servers working together.
All tools are defined inline - no external imports required.
"""

import os
import sys
import re
import json
import random
import string
import time
import multiprocessing
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from polymcp.polyagent import PolyAgent, OllamaProvider, OpenAIProvider
from polymcp.polymcp_toolkit import expose_tools


# =============================================================================
# TEXT ANALYSIS TOOLS
# =============================================================================

def summarize(text: str, max_sentences: int = 3) -> str:
    """
    Summarize a given text by extracting key sentences.
    
    Args:
        text: The text to summarize
        max_sentences: Maximum number of sentences in summary
        
    Returns:
        Summarized text
    """
    if not text or not text.strip():
        return "Error: No text provided"
    
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) <= max_sentences:
        return text.strip()
    
    # Simple extraction: take first sentences (basic summarization)
    summary_sentences = sentences[:max_sentences]
    return '. '.join(summary_sentences) + '.'


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    Analyze the sentiment of a given text.
    
    Args:
        text: The text to analyze
        
    Returns:
        Sentiment analysis results
    """
    if not text or not text.strip():
        return {"error": "No text provided"}
    
    text_lower = text.lower()
    
    positive_words = [
        'good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic',
        'love', 'happy', 'joy', 'beautiful', 'best', 'awesome', 'perfect',
        'brilliant', 'outstanding', 'superb', 'nice', 'pleasant', 'delightful'
    ]
    
    negative_words = [
        'bad', 'terrible', 'awful', 'horrible', 'hate', 'worst', 'poor',
        'sad', 'angry', 'disappointing', 'ugly', 'disgusting', 'failure',
        'wrong', 'boring', 'annoying', 'frustrating', 'useless', 'pathetic'
    ]
    
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    total = positive_count + negative_count
    
    if total == 0:
        sentiment = "neutral"
        confidence = 0.5
    elif positive_count > negative_count:
        sentiment = "positive"
        confidence = positive_count / total
    elif negative_count > positive_count:
        sentiment = "negative"
        confidence = negative_count / total
    else:
        sentiment = "mixed"
        confidence = 0.5
    
    return {
        "text": text[:100] + "..." if len(text) > 100 else text,
        "sentiment": sentiment,
        "confidence": round(confidence, 2),
        "positive_indicators": positive_count,
        "negative_indicators": negative_count
    }


def word_count(text: str) -> Dict[str, int]:
    """
    Count words, characters, and sentences in text.
    
    Args:
        text: The text to analyze
        
    Returns:
        Word count statistics
    """
    if not text or not text.strip():
        return {"error": "No text provided"}
    
    words = text.split()
    sentences = re.split(r'[.!?]+', text)
    sentences = [s for s in sentences if s.strip()]
    paragraphs = text.split('\n\n')
    paragraphs = [p for p in paragraphs if p.strip()]
    
    return {
        "characters": len(text),
        "characters_no_spaces": len(text.replace(" ", "")),
        "words": len(words),
        "sentences": len(sentences),
        "paragraphs": len(paragraphs),
        "average_word_length": round(sum(len(w) for w in words) / len(words), 2) if words else 0
    }


# =============================================================================
# ADVANCED UTILITY TOOLS
# =============================================================================

def calculate_statistics(numbers: List[float]) -> Dict[str, float]:
    """
    Calculate statistical measures for a list of numbers.
    
    Args:
        numbers: List of numerical values
        
    Returns:
        Dictionary with mean, median, std, min, max
    """
    if not numbers:
        return {"error": "Empty list provided"}
    
    try:
        sorted_numbers = sorted(numbers)
        n = len(numbers)
        
        mean = sum(numbers) / n
        
        if n % 2 == 0:
            median = (sorted_numbers[n//2 - 1] + sorted_numbers[n//2]) / 2
        else:
            median = sorted_numbers[n//2]
        
        variance = sum((x - mean) ** 2 for x in numbers) / n
        std = variance ** 0.5
        
        return {
            "count": n,
            "mean": round(mean, 2),
            "median": round(median, 2),
            "std": round(std, 2),
            "min": min(numbers),
            "max": max(numbers),
            "range": max(numbers) - min(numbers)
        }
    except Exception as e:
        return {"error": str(e)}


def format_date(
    date_string: str,
    input_format: str = "%Y-%m-%d",
    output_format: str = "%B %d, %Y"
) -> str:
    """
    Format a date string from one format to another.
    
    Args:
        date_string: Date string to format
        input_format: Current format (strftime format)
        output_format: Desired format (strftime format)
        
    Returns:
        Formatted date string
    """
    try:
        date_obj = datetime.strptime(date_string, input_format)
        return date_obj.strftime(output_format)
    except ValueError as e:
        return f"Error: Invalid date format - {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


def generate_password(
    length: int = 16,
    include_uppercase: bool = True,
    include_numbers: bool = True,
    include_symbols: bool = True
) -> str:
    """
    Generate a random secure password.
    
    Args:
        length: Length of the password (minimum 4)
        include_uppercase: Include uppercase letters
        include_numbers: Include numbers
        include_symbols: Include special symbols
        
    Returns:
        Generated password
    """
    if length < 4:
        return "Error: Password length must be at least 4 characters"
    
    characters = string.ascii_lowercase
    
    if include_uppercase:
        characters += string.ascii_uppercase
    if include_numbers:
        characters += string.digits
    if include_symbols:
        characters += "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    try:
        password = ''.join(random.choice(characters) for _ in range(length))
        return password
    except Exception as e:
        return f"Error: {str(e)}"


def validate_email(email: str) -> Dict[str, Any]:
    """
    Validate an email address format.
    
    Args:
        email: Email address to validate
        
    Returns:
        Validation result with details
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    is_valid = bool(re.match(pattern, email))
    
    result = {
        "email": email,
        "is_valid": is_valid,
    }
    
    if is_valid:
        try:
            username, domain = email.split('@')
            result["username"] = username
            result["domain"] = domain
            result["length"] = len(email)
        except Exception:
            pass
    else:
        result["error"] = "Invalid email format"
    
    return result


def convert_units(
    value: float,
    from_unit: str,
    to_unit: str,
    category: str = "length"
) -> Dict[str, Any]:
    """
    Convert between different units of measurement.
    
    Args:
        value: Value to convert
        from_unit: Source unit
        to_unit: Target unit
        category: Category (length, weight, temperature)
        
    Returns:
        Conversion result
    """
    conversions = {
        "length": {
            "m": 1.0, "km": 0.001, "cm": 100.0, "mm": 1000.0,
            "mile": 0.000621371, "yard": 1.09361, "foot": 3.28084, "inch": 39.3701,
        },
        "weight": {
            "kg": 1.0, "g": 1000.0, "mg": 1000000.0,
            "lb": 2.20462, "oz": 35.274,
        },
    }
    
    if category == "temperature":
        if from_unit == "C" and to_unit == "F":
            result = (value * 9/5) + 32
        elif from_unit == "F" and to_unit == "C":
            result = (value - 32) * 5/9
        elif from_unit == "C" and to_unit == "K":
            result = value + 273.15
        elif from_unit == "K" and to_unit == "C":
            result = value - 273.15
        else:
            return {"error": "Unsupported temperature conversion"}
    elif category not in conversions:
        return {"error": f"Unknown category: {category}"}
    else:
        factors = conversions[category]
        
        if from_unit not in factors or to_unit not in factors:
            return {"error": f"Unknown unit in category {category}"}
        
        base_value = value / factors[from_unit]
        result = base_value * factors[to_unit]
    
    return {
        "original_value": value,
        "original_unit": from_unit,
        "converted_value": round(result, 4),
        "converted_unit": to_unit,
        "category": category
    }


# =============================================================================
# SERVER FUNCTIONS
# =============================================================================

def start_text_server():
    """Start text analysis server."""
    import uvicorn
    app = expose_tools(
        tools=[summarize, analyze_sentiment, word_count],
        title="Text Analysis Server"
    )
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")


def start_utility_server():
    """Start utility tools server."""
    import uvicorn
    app = expose_tools(
        tools=[format_date, generate_password, validate_email, convert_units],
        title="Utility Tools Server"
    )
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="error")


def start_data_server():
    """Start data processing server."""
    import uvicorn
    app = expose_tools(
        tools=[calculate_statistics],
        title="Data Processing Server"
    )
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="error")


# =============================================================================
# LLM PROVIDER
# =============================================================================

def create_llm_provider():
    """Create LLM provider with fallback."""
    if os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIProvider(model="gpt-4")
        except Exception:
            pass
    
    print("Using Ollama (ensure it's running)")
    return OllamaProvider(model="gpt-oss:120b-cloud")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main execution function."""
    print("\n" + "="*60)
    print("🌐 Multi-Server MCP Setup")
    print("="*60 + "\n")
    
    # Start all servers
    servers = [
        multiprocessing.Process(target=start_text_server, daemon=True),
        multiprocessing.Process(target=start_utility_server, daemon=True),
        multiprocessing.Process(target=start_data_server, daemon=True),
    ]
    
    for server in servers:
        server.start()
    
    print("Starting servers...")
    time.sleep(4)
    
    # Create LLM provider
    llm = create_llm_provider()
    
    # Create agent with multiple MCP servers
    agent = PolyAgent(
        llm_provider=llm,
        mcp_servers=[
            "http://localhost:8000/mcp",
            "http://localhost:8001/mcp",
            "http://localhost:8002/mcp",
        ],
        verbose=True
    )
    
    print("\n" + "="*60)
    print(f"Agent connected to {len(agent.mcp_servers)} servers")
    print(f"Total tools: {sum(len(tools) for tools in agent.tools_cache.values())}")
    print("="*60 + "\n")
    
    # Run example queries
    examples = [
        "Summarize: AI is transforming technology",
        "Generate a 16 character password",
        "Calculate statistics for: 10, 20, 30, 40, 50",
        "What's the sentiment of: This is amazing!",
    ]
    
    for i, query in enumerate(examples, 1):
        print(f"\nExample {i}: {query}")
        print("-" * 60)
        try:
            response = agent.run(query)
            print(f"Response: {response}\n")
        except Exception as e:
            print(f"Error: {e}\n")
        time.sleep(1)
    
    # Interactive mode
    print("="*60)
    print("Interactive Mode - Type 'quit' to exit")
    print("="*60 + "\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye!")
                break
            
            if not user_input:
                continue
            
            if user_input.lower() == 'servers':
                print(f"\nConnected servers: {len(agent.mcp_servers)}")
                for i, server in enumerate(agent.mcp_servers, 1):
                    tool_count = len(agent.tools_cache.get(server, []))
                    print(f"  {i}. {server} ({tool_count} tools)")
                print()
                continue
            
            if user_input.lower() == 'tools':
                print("\nAvailable tools:")
                print("  Text Analysis: summarize, analyze_sentiment, word_count")
                print("  Utilities: format_date, generate_password, validate_email, convert_units")
                print("  Data: calculate_statistics")
                print()
                continue
            
            response = agent.run(user_input)
            print(f"\nAgent: {response}\n")
        
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")
    
    # Cleanup
    for server in servers:
        server.terminate()
        server.join()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
