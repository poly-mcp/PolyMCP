#!/usr/bin/env python3
"""
Code Mode Example
Demonstrates the performance benefits of code generation vs traditional tool calling.
"""

import asyncio
import sys
import time
import multiprocessing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from polyagent import CodeModeAgent, PolyAgent, OllamaProvider, OpenAIProvider
from polymcp_toolkit import expose_tools
import os


# business tools for demonstration
def create_transaction(
    transaction_type: str,
    category: str,
    amount: float,
    description: str
) -> str:
    """
    Create a financial transaction.
    
    Args:
        transaction_type: Type (income/expense/transfer)
        category: Transaction category
        amount: Amount in dollars
        description: Transaction description
        
    Returns:
        JSON string with transaction details
    """
    import json
    import random
    
    transaction = {
        "id": f"TXN{random.randint(1000, 9999)}",
        "type": transaction_type,
        "category": category,
        "amount": amount,
        "description": description,
        "timestamp": "2025-01-15T10:30:00Z"
    }
    
    return json.dumps({
        "status": "success",
        "transaction": transaction,
        "new_balance": 10000.00 - amount if transaction_type == "expense" else 10000.00 + amount
    })


def get_financial_summary() -> str:
    """
    Get financial summary.
    
    Returns:
        JSON string with summary
    """
    import json
    
    summary = {
        "total_income": 15000.00,
        "total_expenses": 8500.00,
        "net_balance": 6500.00,
        "transaction_count": 42
    }
    
    return json.dumps({
        "status": "success",
        "summary": summary
    })


def generate_invoice(
    client_name: str,
    amount: float,
    items: str
) -> str:
    """
    Generate an invoice.
    
    Args:
        client_name: Client name
        amount: Invoice amount
        items: Comma-separated items
        
    Returns:
        JSON string with invoice
    """
    import json
    import random
    
    invoice = {
        "invoice_id": f"INV{random.randint(1000, 9999)}",
        "client": client_name,
        "amount": amount,
        "items": items.split(","),
        "status": "pending",
        "due_date": "2025-02-15"
    }
    
    return json.dumps({
        "status": "success",
        "invoice": invoice
    })


def start_mcp_server():
    """Start MCP server with business tools."""
    import uvicorn
    
    app = expose_tools(
        tools=[create_transaction, get_financial_summary, generate_invoice],
        title="Business Tools MCP Server",
        description="Financial and invoicing tools"
    )
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")


def create_llm_provider():
    """Create LLM provider with fallback."""
    if os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIProvider(model="gpt-4")
        except Exception:
            pass
    
    print("Using Ollama (ensure it's running: ollama serve)")
    return OllamaProvider(model="gpt-oss:120b-cloud")


def compare_approaches():
    """
    Compare traditional agent vs code mode agent.
    Demonstrates the performance benefits.
    """
    print("\n" + "="*70)
    print("🎯 CODE MODE vs TRADITIONAL AGENT COMPARISON")
    print("="*70 + "\n")
    
    # Start MCP server
    server_process = multiprocessing.Process(target=start_mcp_server, daemon=True)
    server_process.start()
    
    print("Starting MCP server...")
    time.sleep(3)
    
    llm = create_llm_provider()
    mcp_server = "http://localhost:8000/mcp"
    
    # Test query
    query = """Record these expenses and provide a summary:
    - Rent: $2500
    - Utilities: $150
    - Food: $300
    Then tell me the total expenses."""
    
    print("\n" + "-"*70)
    print("📋 TASK:", query)
    print("-"*70)
    
    # Test 1: Traditional Agent
    print("\n\n🔹 TEST 1: Traditional Agent (Multiple Tool Calls)")
    print("="*70)
    
    traditional_agent = PolyAgent(
        llm_provider=llm,
        mcp_servers=[mcp_server],
        verbose=True
    )
    
    start_time = time.time()
    try:
        result1 = traditional_agent.run(query)
        traditional_time = time.time() - start_time
        print(f"\n✅ Result: {result1}")
        print(f"⏱️  Time: {traditional_time:.2f}s")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        traditional_time = 0
    
    # Test 2: Code Mode Agent
    print("\n\n🔹 TEST 2: Code Mode Agent (Single Code Generation)")
    print("="*70)
    
    codemode_agent = CodeModeAgent(
        llm_provider=llm,
        mcp_servers=[mcp_server],
        verbose=True
    )
    
    start_time = time.time()
    try:
        result2 = codemode_agent.run(query)
        codemode_time = time.time() - start_time
        print(f"\n✅ Result: {result2}")
        print(f"⏱️  Time: {codemode_time:.2f}s")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        codemode_time = 0
    
    # Comparison
    if traditional_time > 0 and codemode_time > 0:
        speedup = ((traditional_time - codemode_time) / traditional_time) * 100
        
        print("\n\n" + "="*70)
        print("📊 PERFORMANCE COMPARISON")
        print("="*70)
        print(f"\n  Traditional Agent:  {traditional_time:.2f}s")
        print(f"  Code Mode Agent:    {codemode_time:.2f}s")
        print(f"\n  🚀 Speedup:         {speedup:.1f}% faster")
        print(f"\n  Expected benefits:")
        print(f"     - Fewer LLM calls (1 vs multiple)")
        print(f"     - Lower token usage (~68% reduction)")
        print(f"     - Better for complex workflows")
        print("="*70 + "\n")
    
    # Cleanup
    server_process.terminate()
    server_process.join()


def interactive_mode():
    """Run Code Mode Agent in interactive mode."""
    print("\n" + "="*70)
    print("🎭 CODE MODE AGENT - INTERACTIVE MODE")
    print("="*70 + "\n")
    
    # Start MCP server
    server_process = multiprocessing.Process(target=start_mcp_server, daemon=True)
    server_process.start()
    
    print("Starting MCP server...")
    time.sleep(3)
    
    llm = create_llm_provider()
    
    agent = CodeModeAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        verbose=True
    )
    
    print("\n" + "="*70)
    print("💡 Try these example queries:")
    print("="*70)
    print("  • Record 5 different expenses and show me the summary")
    print("  • Create invoices for 3 different clients")
    print("  • Record income and expenses, then calculate net profit")
    print("\nType 'quit' to exit")
    print("="*70 + "\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if not user_input:
                continue
            
            result = agent.run(user_input)
            print(f"\n🤖 Agent: {result}\n")
        
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
    
    # Cleanup
    server_process.terminate()
    server_process.join()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Code Mode Agent Example")
    parser.add_argument(
        '--mode',
        choices=['compare', 'interactive'],
        default='compare',
        help='Run mode (compare or interactive)'
    )
    
    args = parser.parse_args()
    
    if args.mode == 'compare':
        compare_approaches()
    else:
        interactive_mode()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    print("\n📋 Prerequisites:")
    print("  1. Ollama running (or OpenAI API key set)")
    print("  2. Python packages: pip install restrictedpython")
    print()
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

        sys.exit(1)
