#!/usr/bin/env python3
"""
PolyAgent Example - Text Analysis
Production-ready example demonstrating agent usage with MCP tools.
"""

import os
import sys
import time
import multiprocessing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from polymcp.polyagent import PolyAgent, OpenAIProvider, OllamaProvider
from polymcp import expose_tools
from polymcp.tools.summarize_tool import summarize, analyze_sentiment, word_count


def start_mcp_server():
    """Start MCP server in background process."""
    import uvicorn
    
    app = expose_tools(
        tools=[summarize, analyze_sentiment, word_count],
        title="Text Analysis MCP Server"
    )
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")


def create_llm_provider():
    """Create LLM provider with fallback to Ollama."""
    if os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIProvider(model="gpt-4")
        except Exception as e:
            print(f"OpenAI initialization failed: {e}")
    
    print("Falling back to Ollama (make sure it's running)")
    return OllamaProvider(model="llama2")


def main():
    """Main execution function."""
    print("\n" + "="*60)
    print("🤖 PolyAgent Example - Text Analysis")
    print("="*60 + "\n")
    
    server_process = multiprocessing.Process(target=start_mcp_server, daemon=True)
    server_process.start()
    
    print("Starting MCP server...")
    time.sleep(3)
    
    llm_provider = create_llm_provider()
    
    agent = PolyAgent(
        llm_provider=llm_provider,
        mcp_servers=["http://localhost:8000/mcp"],
        verbose=True
    )
    
    print("\n" + "="*60)
    print("Running Examples")
    print("="*60 + "\n")
    
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
        time.sleep(1)
    
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
            
            response = agent.run(user_input)
            print(f"\nAgent: {response}\n")
        
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")
    
    server_process.terminate()
    server_process.join()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
