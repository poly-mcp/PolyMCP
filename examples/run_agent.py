#!/usr/bin/env python3
"""
PolyAgent Example - Text Analysis (Tools inline)
Production-ready example demonstrating agent usage with MCP tools,
with MCP server started from this script (no external tool imports).
"""

import os
import sys
import time
import socket
import multiprocessing
from pathlib import Path

# Ensure local package import (repo layout)
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from polymcp import PolyAgent, OpenAIProvider, OllamaProvider, expose_tools


# ---------------------------------------------------------------------
# Inline tools (no imports from polymcp.tools.*)
# (Same behavior as summarize_tool.py)
# ---------------------------------------------------------------------

def summarize(text: str, max_length: int = 50) -> str:
    """
    Summarize text by truncating to specified length.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length].strip() + "..."


def analyze_sentiment(text: str) -> str:
    """
    Analyze sentiment of text using keyword matching.
    Returns: positive / negative / neutral
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
    """
    return len(text.split())


# ---------------------------------------------------------------------
# MCP server helpers
# ---------------------------------------------------------------------

def pick_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def wait_for_mcp_ready(mcp_base_url: str, timeout_s: float = 15.0) -> bool:
    """
    Wait until MCP server responds to /list_tools.
    PolyAgent expects server_url like http://host:port/mcp
    """
    deadline = time.time() + timeout_s
    list_url = f"{mcp_base_url}/list_tools"

    while time.time() < deadline:
        try:
            r = requests.get(list_url, timeout=1.0)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and "tools" in j:
                    return True
        except Exception:
            pass
        time.sleep(0.2)

    return False


def start_mcp_server(host: str, port: int):
    """Start MCP server in background process."""
    import uvicorn

    app = expose_tools(
        tools=[summarize, analyze_sentiment, word_count],
        title="Text Analysis MCP Server"
    )

    uvicorn.run(app, host=host, port=port, log_level="error")


# ---------------------------------------------------------------------
# LLM provider
# ---------------------------------------------------------------------

def create_llm_provider():
    """Create LLM provider with fallback to Ollama."""
    if os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIProvider(model=os.getenv("OPENAI_MODEL", "gpt-4"))
        except Exception as e:
            print(f"OpenAI initialization failed: {e}")

    print("Falling back to Ollama (make sure it's running)")
    return OllamaProvider(model=os.getenv("OLLAMA_MODEL", "llama2"))


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("🤖 PolyAgent Example - Text Analysis (MCP embedded, tools inline)")
    print("=" * 60 + "\n")

    host = "127.0.0.1"
    port = pick_free_port(host)
    mcp_url = f"http://{host}:{port}/mcp"

    server_process = multiprocessing.Process(
        target=start_mcp_server,
        args=(host, port),
        daemon=True
    )
    server_process.start()

    print(f"Starting MCP server at {mcp_url} ...")

    if not wait_for_mcp_ready(mcp_url, timeout_s=15.0):
        server_process.terminate()
        server_process.join(timeout=3.0)
        raise RuntimeError("MCP server did not become ready in time.")

    print("✅ MCP server ready.\n")

    llm_provider = create_llm_provider()

    agent = PolyAgent(
        llm_provider=OllamaProvider(model="gpt-oss:120b-cloud"),
        mcp_servers=[mcp_url],
        verbose=True
    )

    print("\n" + "=" * 60)
    print("Running Examples")
    print("=" * 60 + "\n")

    examples = [
        "Summarize: Artificial Intelligence is transforming technology and society in unprecedented ways.",
        "What's the sentiment of: This product is amazing! Best purchase ever!",
        "Count words in: The quick brown fox jumps over the lazy dog"
    ]

    for i, query in enumerate(examples, 1):
        print(f"\nExample {i}: {query}")
        print("-" * 60)
        try:
            response = agent.run(query)
            print(f"Response: {response}\n")
        except Exception as e:
            print(f"Error: {e}\n")
        time.sleep(0.5)

    print("=" * 60)
    print("Interactive Mode - Type 'quit' to exit")
    print("=" * 60 + "\n")

    try:
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in {"quit", "exit", "q"}:
                print("\nGoodbye!")
                break
            if not user_input:
                continue

            response = agent.run(user_input)
            print(f"\nAgent: {response}\n")

    except KeyboardInterrupt:
        print("\n\nGoodbye!")

    finally:
        if server_process.is_alive():
            server_process.terminate()
            server_process.join(timeout=3.0)
        print("✅ MCP server stopped.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
