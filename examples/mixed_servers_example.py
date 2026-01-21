#!/usr/bin/env python3
"""
Mixed Servers Example
Using both HTTP and stdio MCP servers together.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider


async def main():
    """Main example with mixed server types."""
    
    print("\n" + "="*60)
    print("🌐 Mixed Servers Example (HTTP + Stdio)")
    print("="*60 + "\n")
    
    # Create LLM provider
    llm = OllamaProvider(model="llama2")
    
    # Configure both HTTP and stdio servers
    http_servers = [
        "http://localhost:8000/mcp",  # Your polymcp tools
        "http://localhost:8001/mcp",  # Advanced tools
    ]
    
    stdio_servers = [
        {
            "command": "npx",
            "args": ["@playwright/mcp@latest"],
            "env": {"DISPLAY": ":1"}
        },
        # Add more stdio servers here
        # {
        #     "command": "npx",
        #     "args": ["@modelcontextprotocol/server-filesystem@latest"],
        #     "env": {}
        # }
    ]
    
    print("Starting all servers...")
    agent = UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=http_servers,
        stdio_servers=stdio_servers,
        verbose=True
    )
    
    async with agent:
        # Example: Mix tools from different sources
        queries = [
            # HTTP tool (text analysis)
            "Summarize: PolyMCP supports both HTTP and stdio MCP servers",
            
            # Stdio tool (Playwright)
            "Go to github.com",
            
            # HTTP tool (password generation)
            "Generate a secure 16-character password",
            
            # Stdio tool (browser automation)
            "Take a screenshot of the current page",
        ]
        
        for i, query in enumerate(queries, 1):
            print(f"\n{'='*60}")
            print(f"Query {i}: {query}")
            print(f"{'='*60}\n")
            
            try:
                result = await agent.run_async(query)
                print(f"Result: {result}\n")
            except Exception as e:
                print(f"Error: {e}\n")
            
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
