#!/usr/bin/env python3
"""
UnifiedAgent + skills.sh + Playwright example.

Includes multiple scenarios so you can run stronger end-to-end checks
instead of a single trivial title query.
"""

import asyncio
import argparse
import json
import re
from typing import Dict, List

from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider


def _scenarios() -> Dict[str, List[Dict[str, object]]]:
    return {
        "quick": [
            {
                "name": "Basic title check",
                "query": "Navigate to https://example.com and return only the page title.",
                "expect": ["example domain"],
            }
        ],
        "deep": [
            {
                "name": "Navigate + title",
                "query": (
                    "Navigate to https://example.com and return only the page title."
                ),
                "expect": ["example domain"],
            },
            {
                "name": "DOM extraction",
                "query": (
                    "From the current page, extract h1 text and first paragraph text. "
                    "Return JSON with keys h1 and paragraph."
                ),
                "expect": ["h1", "paragraph", "example domain"],
                "expect_json_keys": ["h1", "paragraph"],
            },
            {
                "name": "Link inventory",
                "query": (
                    "From the current page, count all links and return a JSON object "
                    "with link_count and hrefs (array)."
                ),
                "expect": ["link_count", "href", "iana"],
                "expect_json_keys": ["link_count", "hrefs"],
            },
            {
                "name": "Second navigation",
                "query": (
                    "Navigate to https://www.iana.org/domains/reserved and return JSON "
                    "with title and one-line summary."
                ),
                "expect": ["iana", "title"],
                "expect_json_keys": ["title", "summary"],
            },
            {
                "name": "Screenshot confirmation",
                "query": "Take a full-page screenshot and save it as screenshot.png.",
                "expect": ["screenshot"],
            },
        ],
        "tabs": [
            {
                "name": "Open first page",
                "query": "Navigate to https://example.com and confirm page title.",
                "expect": ["example domain"],
            },
            {
                "name": "Open second tab",
                "query": (
                    "Open a new browser tab, navigate it to https://example.org, "
                    "then list all open tabs with index, title, and url."
                ),
                "expect": ["tab", "example", "url"],
            },
            {
                "name": "Compare tabs",
                "query": (
                    "Return a compact comparison of tab titles and identify the active tab."
                ),
                "expect": ["active", "tab"],
            },
        ],
    }


def _contains_expectations(result_text: str, expected_tokens: List[str]) -> bool:
    text = (result_text or "").lower()
    return all(tok.lower() in text for tok in expected_tokens)


def _extract_first_json(text: str) -> Dict[str, object]:
    if not text:
        return {}
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)
    starts = [m.start() for m in re.finditer(r"\{", s)]
    for start in starts:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = s[start : i + 1].strip()
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break
    return {}


def _json_has_keys(result_text: str, keys: List[str]) -> bool:
    if not keys:
        return True
    obj = _extract_first_json(result_text)
    if not isinstance(obj, dict) or not obj:
        return False
    return all(k in obj for k in keys)


async def _run_scenario(
    agent: UnifiedPolyAgent,
    scenario_name: str,
    max_steps: int,
    strict: bool,
) -> int:
    scenarios = _scenarios()
    steps = scenarios[scenario_name]
    failures = 0

    print(f"\nRunning scenario: {scenario_name} ({len(steps)} steps)\n")

    for idx, step in enumerate(steps, start=1):
        name = str(step["name"])
        query = str(step["query"])
        expected = [str(x) for x in step.get("expect", [])]
        expected_json_keys = [str(x) for x in step.get("expect_json_keys", [])]

        print("-" * 72)
        print(f"Step {idx}/{len(steps)}: {name}")
        print(f"Query: {query}\n")

        result = await agent.run_async(query, max_steps=max_steps)
        print(f"Result: {result}\n")

        ok_tokens = _contains_expectations(result, expected) if expected else True
        ok_json = _json_has_keys(result, expected_json_keys) if expected_json_keys else True
        ok = ok_tokens and ok_json
        status = "PASS" if ok else "WARN"
        print(
            f"Check: {status} | expected tokens={expected}"
            + (f" | expected json keys={expected_json_keys}" if expected_json_keys else "")
            + "\n"
        )
        if not ok:
            failures += 1

    print("=" * 72)
    print(f"Scenario completed with {failures} issue(s).")
    print("=" * 72)

    if strict and failures > 0:
        raise RuntimeError(f"Scenario '{scenario_name}' failed with {failures} issue(s)")

    return failures


async def main():
    parser = argparse.ArgumentParser(description="UnifiedAgent + skills.sh + Playwright scenario runner")
    parser.add_argument(
        "--scenario",
        choices=["quick", "deep", "tabs"],
        default="deep",
        help="Scenario to run (default: deep)",
    )
    parser.add_argument(
        "--model",
        default="gpt-oss:120b-cloud",
        help="Ollama model name (default: gpt-oss:120b-cloud)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Max agent steps per query (default: 12)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error if a scenario step check fails",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("UnifiedAgent + skills.sh + Playwright")
    print("=" * 60 + "\n")

    stdio_servers = [{
        "command": "npx",
        "args": ["@playwright/mcp@latest"],
    }]

    print("Initializing UnifiedAgent with skills.sh only...")
    agent = UnifiedPolyAgent(
        llm_provider=OllamaProvider(model=args.model),
        stdio_servers=stdio_servers,
        skills_sh_enabled=True,
        verbose=True,
        memory_enabled=True,
    )

    print("\nAgent ready. Running Playwright scenario via skills.sh context.\n")

    async with agent:
        await _run_scenario(
            agent=agent,
            scenario_name=args.scenario,
            max_steps=args.max_steps,
            strict=args.strict,
        )


if __name__ == "__main__":
    print("\nPrerequisites:")
    print("  1. Install at least one skills.sh package:")
    print("     polymcp skills add vercel-labs/agent-skills")
    print("  2. Verify installed skills:")
    print("     polymcp skills list")
    print("  3. Ollama running with model:")
    print("     ollama run gpt-oss:120b-cloud")
    print()
    print("Examples:")
    print("  python examples/unified_skills_playwright_example.py --scenario deep")
    print("  python examples/unified_skills_playwright_example.py --scenario tabs --strict")
    print()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise
