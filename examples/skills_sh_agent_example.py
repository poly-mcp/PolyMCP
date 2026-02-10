#!/usr/bin/env python3
"""
skills.sh Agent Example (Python)

1) Start a local MCP server in another terminal:
   python examples/simple_example.py

2) Install at least one skills.sh skill:
   polymcp skills add vercel-labs/agent-skills

3) Run this example:
   python examples/skills_sh_agent_example.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from polymcp.polyagent import UnifiedPolyAgent
from polymcp.polyagent.llm_providers import OpenAIProvider, OllamaProvider


def _make_provider():
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    if os.getenv("OLLAMA_MODEL") or os.getenv("OLLAMA_BASE_URL"):
        return OllamaProvider(
            model=os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    else:
        return OllamaProvider(
            model=os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )


def main():
    provider = _make_provider()

    agent = UnifiedPolyAgent(
        llm_provider=provider,
        mcp_servers=["http://localhost:8000/mcp"],
        skills_sh_enabled=True,  # default
        verbose=True,
    )

    prompt = (
        "Use the tools to greet Sarah and then add 39 + 2. "
        "Follow any relevant skills if they apply."
    )
    result = agent.run(prompt)
    print("\n--- FINAL ---\n")
    print(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ {e}\n")
        sys.exit(1)
