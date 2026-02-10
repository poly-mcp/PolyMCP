#!/usr/bin/env python3
"""
UnifiedAgent + skills.sh + Playwright example (skills.sh only).
"""

import asyncio
from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider


async def main():
    print("\n" + "=" * 60)
    print("UnifiedAgent + skills.sh + Playwright")
    print("=" * 60 + "\n")

    stdio_servers = [{
        "command": "npx",
        "args": ["@playwright/mcp@latest"],
    }]

    print("Initializing UnifiedAgent with skills.sh only...")
    agent = UnifiedPolyAgent(
        llm_provider=OllamaProvider(model="gpt-oss:120b-cloud"),
        stdio_servers=stdio_servers,
        skills_sh_enabled=True,
        verbose=True,
    )

    query = "Navigate to example.com and get the title"
    print(f"Query: {query}\n")

    async with agent:
        result = await agent.run_async(query)

    print(f"\nResult: {result}")


if __name__ == "__main__":
    print("\nPrerequisites:")
    print("  1. Install at least one skills.sh package:")
    print("     polymcp skills add vercel-labs/agent-skills")
    print("  2. Verify installed skills:")
    print("     polymcp skills list")
    print("  3. Ollama running with model:")
    print("     ollama run gpt-oss:120b-cloud")
    print()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise
