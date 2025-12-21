#!/usr/bin/env python3
"""
🎯 UnifiedAgent + Skills System + Playwright Example
Normal Agent mode con 87% token savings.
"""

import asyncio
from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider


async def main():
    print("\n" + "="*60)
    print("🎯 UnifiedAgent + Skills System + Playwright")
    print("="*60 + "\n")
    
    # 1. Playwright MCP server via stdio
    stdio_servers = [{
        "command": "npx",
        "args": ["@playwright/mcp@latest"]
    }]
    
    # 2. UnifiedAgent (normal mode) WITH Skills System
    print("🔧 Initializing UnifiedAgent with Skills...")
    agent = UnifiedPolyAgent(
        llm_provider=OllamaProvider(model="gpt-oss:120b-cloud"),
        stdio_servers=stdio_servers,
        skills_enabled=True,        # 🆕 87% token savings
        skills_dir="./mcp_skills",  # ← Directory delle skills generate
        verbose=True
    )
    
    print("\n✅ Agent initialized with Skills System")
    print("📊 Skills will load ONLY Playwright tools on-demand\n")
        
    # 3. Query automaticamente usa solo Playwright tools
    query = "Navigate to example.com and get the title"
    
    print(f"🎯 Query: {query}\n")
    
    async with agent:
        result = await agent.run_async(query)
    
    print(f"\n✅ Result: {result}")
    print(f"\n💡 Token Savings with Skills System:")
    print(f"   • Without Skills: ~20,000 tokens (all tools)")
    print(f"   • WITH Skills:     ~2,500 tokens (87% reduction!)")


if __name__ == "__main__":
    print("\n📋 Prerequisites:")
    print("  1. Generate skills first:")
    print("     polymcp skills generate --servers 'npx @playwright/mcp@latest' --verbose")
    print("  2. Ollama running with model:")
    print("     ollama run gpt-oss:120b-cloud")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
