#!/usr/bin/env python3
"""
📁 UnifiedAgent + Skills System + Filesystem Example
Esempio con filesystem skill per vedere token count diverso da web skill.
"""

import asyncio
from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider


async def main():
    print("\n" + "="*60)
    print("📁 UnifiedAgent + Skills System + Filesystem")
    print("="*60 + "\n")
    
    # 1. Filesystem MCP server via stdio
    # Usa il server filesystem di MCP
    stdio_servers = [{
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", ".Polymcp\\tests"]
    }]
    
    # 2. UnifiedAgent con Skills System
    print("🔧 Initializing UnifiedAgent with Skills...")
    agent = UnifiedPolyAgent(
        llm_provider=OllamaProvider(model="gpt-oss:120b-cloud"),
        stdio_servers=stdio_servers,
        skills_enabled=True,
        skills_dir="./mcp_skills",
        verbose=True
    )
    
    print("\n✅ Agent initialized with Skills System")
    print("📊 Skills will load ONLY Filesystem tools on-demand\n")
    
    # 3. Query che dovrebbe matchare filesystem skill
    queries = [
        "List all files in the current directory",
        "Read the content of package.json file",
        "Create a new file called test.txt with content 'Hello World'"
    ]
    
    async with agent:
        for i, query in enumerate(queries, 1):
            print(f"\n{'='*60}")
            print(f"Query {i}/{len(queries)}: {query}")
            print(f"{'='*60}\n")
            
            try:
                result = await agent.run_async(query)
                print(f"\n✅ Result: {result}")
                
                # Pausa tra query
                if i < len(queries):
                    await asyncio.sleep(2)
                    
            except Exception as e:
                print(f"\n❌ Error: {e}")
                import traceback
                traceback.print_exc()
    
    print(f"\n{'='*60}")
    print(f"💡 Token Comparison:")
    print(f"   • Web skill:        ~2,348 tokens (13 tools)")
    print(f"   • Filesystem skill: ~[different] tokens (different # tools)")
    print(f"   • Without Skills:   ~20,000 tokens (all 80+ tools)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print("\n📋 Prerequisites:")
    print("  1. Generate skills first:")
    print("     polymcp skills generate --servers 'npx -y @modelcontextprotocol/server-filesystem /tmp' --verbose")
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
