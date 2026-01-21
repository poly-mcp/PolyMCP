#!/usr/bin/env python3
"""
Multi-Server Setup Example
Production example demonstrating multiple MCP servers working together.
"""

import os
import sys
import time
import multiprocessing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from polyagent import PolyAgent, OllamaProvider, OpenAIProvider
from polymcp_toolkit import expose_tools
from tools.summarize_tool import summarize, analyze_sentiment, word_count
from tools.advanced_tools import (
    calculate_statistics, format_date, generate_password,
    validate_email, convert_units
)


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


def create_llm_provider():
    """Create LLM provider with fallback."""
    if os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIProvider(model="gpt-4")
        except Exception:
            pass
    
    print("Using Ollama (ensure it's running)")
    return OllamaProvider(model="llama2")


def main():
    """Main execution function."""
    print("\n" + "="*60)
    print("🌐 Multi-Server MCP Setup")
    print("="*60 + "\n")
    
    servers = [
        multiprocessing.Process(target=start_text_server, daemon=True),
        multiprocessing.Process(target=start_utility_server, daemon=True),
        multiprocessing.Process(target=start_data_server, daemon=True),
    ]
    
    for server in servers:
        server.start()
    
    print("Starting servers...")
    time.sleep(4)
    
    llm = create_llm_provider()
    
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
            
            response = agent.run(user_input)
            print(f"\nAgent: {response}\n")
        
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")
    
    for server in servers:
        server.terminate()
        server.join()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()