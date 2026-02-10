#!/usr/bin/env python3
"""
Playwright MCP Example with PolyMCP (FIXED)

Why this version works better:
- ✅ memory_enabled=True so the agent can reuse context across user requests
- ✅ a "snapshot-first" pattern for actions that require element refs (click/type)
- ✅ optional single-shot task that does everything in one run (most reliable)

Notes:
- This does NOT hardcode Playwright specifics; it simply asks the agent to
  take a snapshot before interacting with page elements, which is a generic
  requirement for any MCP that needs element references.
"""

import asyncio
import sys
from pathlib import Path

# Ensure local project import works
sys.path.insert(0, str(Path(__file__).parent.parent))

from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider


async def run_scripted_demo(agent: UnifiedPolyAgent) -> None:
    """
    Scripted demo using a robust "snapshot → interact" approach.
    Each step is a separate run_async, but memory_enabled=True keeps context.
    """
    steps = [
        # Navigation
        "Go to https://auto-doc.it",

        # Snapshot to expose element refs for later actions
        "Take a snapshot of the current page (DOM snapshot) so we can reference elements.",

        # Type into the license plate input
        (
            "Using the snapshot refs, find the license plate / targa input field, "
            "click/focus it if needed, and type: AB123CD"
        ),

        # Snapshot again (optional but helps if UI changes after typing)
        "Take another snapshot to confirm the input contains AB123CD and to get updated refs if needed.",

        # Click Search
        (
            "Using the latest snapshot refs, click the button labeled 'Search' "
            "(or equivalent submit/search action)."
        ),

        # Screenshot (optional)
        "Take a screenshot of the current page.",
    ]

    for i, query in enumerate(steps, 1):
        print(f"\n{'='*60}")
        print(f"Step {i}/{len(steps)}: {query}")
        print(f"{'='*60}\n")

        try:
            result = await agent.run_async(query, max_steps=10)
            print(f"\nResult: {result}\n")
        except Exception as e:
            print(f"\nError: {e}\n")
        await asyncio.sleep(0.75)


async def run_single_shot(agent: UnifiedPolyAgent) -> None:
    """
    Single-shot demo (most reliable): one prompt, one run.
    """
    query = (
        "Go to https://auto-doc.it. "
        "Take a snapshot of the page. "
        "Find the license plate (targa) search input and type AB123CD. "
        "Then click the Search button. "
        "Finally, take a screenshot."
    )

    print(f"\n{'='*60}")
    print("Single-shot task")
    print(f"{'='*60}\n")

    try:
        result = await agent.run_async(query, max_steps=12)
        print(f"\nResult: {result}\n")
    except Exception as e:
        print(f"\nError: {e}\n")


async def main() -> None:
    print("\n" + "=" * 60)
    print("🎭 Playwright MCP Example with PolyMCP + Ollama (FIXED)")
    print("=" * 60 + "\n")

    # Create Ollama LLM provider
    print("Initializing Ollama...")
    llm = OllamaProvider(
        model="gpt-oss:120b-cloud",
        base_url="http://localhost:11434",
    )

    # Configure Playwright stdio server
    stdio_servers = [
        {
            "command": "npx",
            "args": ["@playwright/mcp@latest"],
            "env": {
                # For Linux, remove on Windows/Mac
                "DISPLAY": ":1"
            },
        }
    ]

    # Create unified agent with stdio support
    print("Starting Playwright MCP server...")
    agent = UnifiedPolyAgent(
        llm_provider=llm,
        stdio_servers=stdio_servers,
        verbose=True,

        # ✅ IMPORTANT: keep memory between separate user queries
        memory_enabled=True,

        # Disable budgets for debugging (optional)
        max_wall_time=None,
        max_tokens=None,
        max_tool_calls=None,
    )

    async with agent:
        # Choose ONE of the following:
        # 1) The single-shot run is generally the most reliable:
        await run_single_shot(agent)

        # 2) Or the step-by-step scripted demo:
        # await run_scripted_demo(agent)

        # Interactive mode (keeps memory too)
        print("\n" + "=" * 60)
        print("Interactive Mode - Type 'quit' to exit")
        print("=" * 60 + "\n")

        while True:
            try:
                user_input = input("You: ").strip()
                if user_input.lower() in {"quit", "exit", "q"}:
                    print("\nGoodbye!")
                    break
                if not user_input:
                    continue

                # Tip: if user wants to click/type, advise snapshot-first:
                # user can type: "snapshot" or "take a snapshot" before interactions.
                result = await agent.run_async(user_input, max_steps=12)
                print(f"\nAgent: {result}\n")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}\n")


if __name__ == "__main__":
    print("\n📋 Prerequisites:")
    print("  1. Ollama running: ollama serve")
    print("  2. Playwright MCP available: npx @playwright/mcp@latest")
    print("  3. Your Ollama model is available locally")
    print()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)
