#!/usr/bin/env python3
"""
UnifiedAgent + skills.sh + filesystem server example (skills.sh only).
"""

import asyncio
from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider


async def main():
    print("\n" + "=" * 60)
    print("UnifiedAgent + skills.sh + Filesystem")
    print("=" * 60 + "\n")

    stdio_servers = [{
        "command": "npx",
        "args": [
            "-y",
            "@modelcontextprotocol/server-filesystem",
            "C:\\Users\\sarah\\Desktop\\Polymcp-main\\tests",
        ],
    }]

    print("Initializing UnifiedAgent with skills.sh only...")
    agent = UnifiedPolyAgent(
        llm_provider=OllamaProvider(model="gpt-oss:120b-cloud"),
        stdio_servers=stdio_servers,
        skills_sh_enabled=True,
        verbose=True,
    )

    queries = [
        "List all files in the current directory",
        "Read the content of package.json file",
        "Create a new file called test.txt with content Hello World",
    ]

    async with agent:
        for i, query in enumerate(queries, 1):
            print(f"\n{'=' * 60}")
            print(f"Query {i}/{len(queries)}: {query}")
            print(f"{'=' * 60}\n")

            try:
                result = await agent.run_async(query)
                print(f"\nResult: {result}")
                if i < len(queries):
                    await asyncio.sleep(2)
            except Exception as e:
                print(f"\nError: {e}")


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
