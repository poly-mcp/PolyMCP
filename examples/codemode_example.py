#!/usr/bin/env python3
"""
Code Mode Demo (Docker-only Sandbox) - Windows Compatible

- Compares Traditional (multi tool-calling) vs CodeMode (codegen + Docker execution)
- Starts a local HTTP MCP server exposing demo business tools
- Uses threading (not multiprocessing) for Windows compatibility

Prereqs:
  1) Docker running (e.g. `docker ps` works)
  2) Python deps:
       pip install docker uvicorn requests
     + your project deps (polymcp / polymcp_toolkit / provider libs)
  3) Ollama running OR OPENAI_API_KEY set
"""

import os
import time
import json
import threading  # ✅ Changed from multiprocessing
from typing import Optional

import requests

# Adjust these imports to your project layout
from polymcp.polyagent import CodeModeAgent, UnifiedPolyAgent, OllamaProvider, OpenAIProvider
from polymcp.polymcp_toolkit import expose_tools


# ----------------------------
# Demo business tools
# ----------------------------

def create_transaction(transaction_type: str, category: str, amount: float, description: str) -> str:
    import random
    transaction = {
        "id": f"TXN{random.randint(1000, 9999)}",
        "type": transaction_type,
        "category": category,
        "amount": float(amount),
        "description": description,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    new_balance = 10000.0 - transaction["amount"] if transaction_type == "expense" else 10000.0 + transaction["amount"]
    return json.dumps({"status": "success", "transaction": transaction, "new_balance": new_balance})


def get_financial_summary() -> str:
    summary = {
        "total_income": 15000.00,
        "total_expenses": 8500.00,
        "net_balance": 6500.00,
        "transaction_count": 42,
    }
    return json.dumps({"status": "success", "summary": summary})


def generate_invoice(client_name: str, amount: float, items: str) -> str:
    import random
    invoice = {
        "invoice_id": f"INV{random.randint(1000, 9999)}",
        "client": client_name,
        "amount": float(amount),
        "items": [x.strip() for x in items.split(",") if x.strip()],
        "status": "pending",
        "due_date": "2026-02-15",
    }
    return json.dumps({"status": "success", "invoice": invoice})


# ----------------------------
# MCP server thread (✅ Changed)
# ----------------------------

def start_mcp_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """
    Start MCP server with business tools.
    Runs in current thread.
    """
    import uvicorn

    app = expose_tools(
        tools=[create_transaction, get_financial_summary, generate_invoice],
        title="Business Tools MCP Server",
        description="Financial and invoicing tools",
    )

    # ✅ Suppress uvicorn startup messages
    uvicorn.run(app, host=host, port=port, log_level="error")


def wait_for_mcp(base_url: str, timeout_s: float = 10.0) -> None:
    """Wait until the MCP server responds to /mcp/list_tools."""
    deadline = time.time() + timeout_s
    last_err: Optional[Exception] = None

    while time.time() < deadline:
        try:
            # Server has /mcp prefix in endpoints
            r = requests.get(f"{base_url}/mcp/list_tools", timeout=1.5)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and isinstance(j.get("tools"), list):
                    print(f"✓ MCP server ready with {len(j['tools'])} tools")
                    return
        except Exception as e:
            last_err = e

        time.sleep(0.25)

    raise RuntimeError(f"MCP server not ready at {base_url}/mcp (last error: {last_err})")


# ----------------------------
# LLM provider selection
# ----------------------------

def create_llm_provider():
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    print("Using Ollama (ensure it's running: `ollama serve`)")
    return OllamaProvider(model=os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud"))


# ----------------------------
# Docker check
# ----------------------------

def check_docker_available() -> None:
    try:
        import docker as docker_sdk
        client = docker_sdk.from_env()
        client.ping()
        print("✓ Docker is available")
    except Exception as e:
        raise RuntimeError(
            "Docker is required for CodeModeAgent (Docker-only) but is not available.\n"
            "Fix:\n"
            "  - Install Docker Desktop\n"
            "  - Start Docker Desktop\n"
            "  - Ensure Docker daemon is running\n"
            f"Details: {type(e).__name__}: {e}"
        )


# ----------------------------
# Demo flows
# ----------------------------

def compare_approaches():
    print("\n" + "=" * 78)
    print("CODE MODE (Docker-only) vs TRADITIONAL AGENT COMPARISON")
    print("=" * 78 + "\n")

    host = "127.0.0.1"
    port = 8000
    base_url = f"http://{host}:{port}"

    # ✅ Start server in background thread instead of process
    server_thread = threading.Thread(
        target=start_mcp_server,
        args=(host, port),
        daemon=True,
        name="MCPServerThread"
    )
    server_thread.start()

    try:
        print(f"Starting MCP server at {base_url} ...")
        wait_for_mcp(base_url, timeout_s=12.0)
        print("MCP server ready.\n")

        # Check Docker before running tests
        check_docker_available()

        llm = create_llm_provider()

        query = (
            "Record these expenses and provide a summary:\n"
            "- Rent: $2500\n"
            "- Utilities: $150\n"
            "- Food: $300\n"
            "Then tell me the total expenses."
        )

        print("-" * 78)
        print("TASK:")
        print(query)
        print("-" * 78)

        # Traditional Agent
        print("\n\n[TEST 1] Traditional Agent (multiple tool calls)")
        print("=" * 78)
        traditional_agent = UnifiedPolyAgent(
            llm_provider=llm,
            mcp_servers=[base_url],  # ✅ No /mcp needed (auto-normalized)
            verbose=True,
        )

        start_time = time.time()
        try:
            result1 = traditional_agent.run(query)
            traditional_time = time.time() - start_time
            print(f"\n✓ Result:\n{result1}")
            print(f"\n⏱  Time: {traditional_time:.2f}s")
        except Exception as e:
            traditional_time = 0.0
            print(f"\n✗ ERROR (Traditional): {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        # Code Mode Agent (Docker-only)
        print("\n\n[TEST 2] Code Mode Agent (single codegen + Docker execution)")
        print("=" * 78)

        codemode_agent = CodeModeAgent(
            llm_provider=llm,
            mcp_servers=[base_url],  # ✅ No /mcp needed (auto-normalized)
            verbose=True,
        )

        start_time = time.time()
        try:
            result2 = codemode_agent.run(query)
            codemode_time = time.time() - start_time
            print(f"\n✓ Result:\n{result2}")
            print(f"\n⏱  Time: {codemode_time:.2f}s")
        except Exception as e:
            codemode_time = 0.0
            print(f"\n✗ ERROR (CodeMode): {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        # Comparison
        if traditional_time > 0 and codemode_time > 0:
            speedup = ((traditional_time - codemode_time) / traditional_time) * 100.0
            print("\n" + "=" * 78)
            print("PERFORMANCE COMPARISON")
            print("=" * 78)
            print(f"Traditional Agent:  {traditional_time:.2f}s")
            print(f"Code Mode Agent:    {codemode_time:.2f}s")
            
            if speedup > 0:
                print(f"Speedup:            {speedup:.1f}% faster ⚡")
            else:
                print(f"Performance:        {abs(speedup):.1f}% slower")
            
            print("\nCodeMode benefits:")
            print("  • Fewer LLM calls (1 vs multiple)")
            print("  • Lower token usage")
            print("  • Better for multi-step workflows")
            print("  • More deterministic execution")
            print("=" * 78)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n✗ Fatal error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Thread will auto-cleanup (daemon=True)
        print("\nServer thread will cleanup automatically")


def interactive_mode():
    print("\n" + "=" * 78)
    print("CODE MODE AGENT - INTERACTIVE MODE (Docker-only)")
    print("=" * 78 + "\n")

    check_docker_available()

    host = "127.0.0.1"
    port = 8000
    base_url = f"http://{host}:{port}"

    # ✅ Start server in background thread
    server_thread = threading.Thread(
        target=start_mcp_server,
        args=(host, port),
        daemon=True,
        name="MCPServerThread"
    )
    server_thread.start()

    try:
        print(f"Starting MCP server at {base_url} ...")
        wait_for_mcp(base_url, timeout_s=12.0)
        print("MCP server ready.\n")

        llm = create_llm_provider()

        agent = CodeModeAgent(
            llm_provider=llm,
            mcp_servers=[base_url],  # ✅ No /mcp needed (auto-normalized)
            verbose=True,
        )

        print("=" * 78)
        print("Try example queries:")
        print("  • Record 5 different expenses and show me the summary")
        print("  • Create invoices for 3 different clients")
        print("  • Record income and expenses, then calculate net profit")
        print("Type 'quit' to exit.")
        print("=" * 78 + "\n")

        while True:
            try:
                user_input = input("You: ").strip()
                if user_input.lower() in ("quit", "exit", "q"):
                    print("\nGoodbye!")
                    break
                if not user_input:
                    continue

                result = agent.run(user_input)
                print(f"\nAgent:\n{result}\n")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"\n✗ ERROR: {type(e).__name__}: {e}\n")

    finally:
        # Thread will auto-cleanup
        pass


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Code Mode Agent Demo (Docker-only)")
    parser.add_argument("--mode", choices=["compare", "interactive"], default="compare")
    args = parser.parse_args()

    print("\n" + "=" * 78)
    print("CodeMode Demo - Windows Compatible Edition")
    print("=" * 78)
    print("\nPrereqs:")
    print("  1) Docker running (`docker ps` works)")
    print("  2) MCP deps installed (uvicorn, requests, docker, polymcp_toolkit)")
    print("  3) Ollama running OR OPENAI_API_KEY set")
    print()

    if args.mode == "compare":
        compare_approaches()
    else:
        interactive_mode()


if __name__ == "__main__":
    main()