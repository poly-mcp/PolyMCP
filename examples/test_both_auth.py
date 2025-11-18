#!/usr/bin/env python3
"""
Simple MCP Client Example
Works with or without authentication
"""

import os
import asyncio
from dotenv import load_dotenv
from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider

# Load environment
load_dotenv()

async def main():
    # Setup LLM
    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)
    
    # Configure server connection
    server_config = {
        "url": f"http://localhost:{os.getenv('MCP_SERVER_PORT', '8000')}"
    }
    
    # Add authentication if enabled
    if os.getenv("MCP_AUTH_ENABLED", "false") == "true":
        api_key = os.getenv("MCP_API_KEY_POLYMCP")
        if api_key:
            server_config["headers"] = {"X-API-Key": api_key}
            print(f"🔐 Using authentication")
        else:
            print("⚠️  Auth enabled but no API key found!")
    else:
        print("🔓 No authentication (dev mode)")
    
    # Create agent
    agent = UnifiedPolyAgent(
        llm_provider=llm,
        http_servers=[server_config],
        verbose=True
    )
    
    async with agent:
        print("\n✅ Connected to MCP server!\n")
        
        # Test calculations
        result = await agent.run_async(
            "Add 15 and 25, then multiply the result by 2",
            max_steps=5
        )
        print(f"Result: {result}")

if __name__ == "__main__":
    print("\n🤖 PolyMCP Client Test")
    print("="*50)
    asyncio.run(main())