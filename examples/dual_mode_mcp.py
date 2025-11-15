#!/usr/bin/env python3
"""
Dual Mode MCP Example
Demonstrates both HTTP and In-Process MCP server modes with performance comparison.
"""

import asyncio
import sys
import time
import multiprocessing
from pathlib import Path
import json
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent))

from polymcp.polyagent import CodeModeAgent, PolyAgent, OllamaProvider, OpenAIProvider
from polymcp.polymcp_toolkit import expose_tools_http, expose_tools_inprocess
import os


# ============================================================================
# SAMPLE BUSINESS TOOLS
# ============================================================================

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


async def calculate_tax(income: float, deductions: float = 0) -> Dict[str, Any]:
    """
    Calculate tax (async function example).
    
    Args:
        income: Total income
        deductions: Total deductions
        
    Returns:
        Tax calculation details
    """
    await asyncio.sleep(0.1)  # Simulate async operation
    
    taxable = max(0, income - deductions)
    tax = taxable * 0.25
    
    return {
        "status": "success",
        "income": income,
        "deductions": deductions,
        "taxable_income": taxable,
        "tax_amount": tax,
        "net_income": income - tax
    }


# ============================================================================
# HTTP MODE
# ============================================================================

def start_http_mcp_server():
    """Start HTTP MCP server with business tools."""
    import uvicorn
    
    app = expose_tools_http(
        tools=[
            create_transaction, 
            get_financial_summary, 
            generate_invoice,
            calculate_tax
        ],
        title="Business Tools MCP Server",
        description="Financial and invoicing tools via HTTP",
        verbose=True
    )
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")


# ============================================================================
# IN-PROCESS MODE
# ============================================================================

class InProcessCodeModeAgent(CodeModeAgent):
    """Code Mode Agent with in-process MCP server support."""
    
    def __init__(self, llm_provider, inprocess_server=None, **kwargs):
        super().__init__(llm_provider, **kwargs)
        self.inprocess_server = inprocess_server
        
    async def _execute_tool_async(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Execute tool using in-process server if available."""
        if self.inprocess_server:
            result = await self.inprocess_server.invoke(tool_name, params)
            return result
        else:
            return await super()._execute_tool_async(tool_name, params)
    
    async def _get_tools_async(self) -> list:
        """Get tools from in-process server if available."""
        if self.inprocess_server:
            result = await self.inprocess_server.list_tools()
            return result.get("tools", [])
        else:
            return await super()._get_tools_async()


# ============================================================================
# COMPARISON FUNCTIONS
# ============================================================================

def create_llm_provider():
    """Create LLM provider with fallback."""
    if os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIProvider(model="gpt-4")
        except Exception:
            pass
    
    print("Using Ollama (ensure it's running: ollama serve)")
    return OllamaProvider(model="llama3.2")


async def test_inprocess_mode():
    """Test in-process MCP server mode."""
    print("\n" + "="*70)
    print("🚀 IN-PROCESS MODE TEST")
    print("="*70 + "\n")
    
    # Create in-process server
    server = expose_tools_inprocess(
        tools=[
            create_transaction,
            get_financial_summary,
            generate_invoice,
            calculate_tax
        ],
        verbose=True
    )
    
    print(f"Created: {server}")
    
    # List tools
    print("\n📋 Available tools:")
    tools = await server.list_tools()
    for tool in tools["tools"]:
        print(f"  • {tool['name']}: {tool['description']}")
    
    # Test synchronous function
    print("\n🔧 Testing sync function (create_transaction):")
    result = await server.invoke("create_transaction", {
        "transaction_type": "expense",
        "category": "rent",
        "amount": 2500.0,
        "description": "Monthly rent"
    })
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Test async function
    print("\n🔧 Testing async function (calculate_tax):")
    result = await server.invoke("calculate_tax", {
        "income": 100000.0,
        "deductions": 15000.0
    })
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Test error handling
    print("\n❌ Testing error handling:")
    result = await server.invoke("invalid_tool", {})
    print(f"Error result: {json.dumps(result, indent=2)}")
    
    # Show stats
    print(f"\n📊 Stats: {server.get_stats()}")
    
    return server


async def compare_server_modes():
    """Compare HTTP vs In-Process server performance."""
    print("\n" + "="*70)
    print("🔬 HTTP vs IN-PROCESS PERFORMANCE COMPARISON")
    print("="*70 + "\n")
    
    # Test query
    test_operations = [
        ("create_transaction", {
            "transaction_type": "expense",
            "category": "utilities",
            "amount": 150.0,
            "description": "Electric bill"
        }),
        ("get_financial_summary", {}),
        ("generate_invoice", {
            "client_name": "Acme Corp",
            "amount": 5000.0,
            "items": "Consulting,Development,Support"
        }),
        ("calculate_tax", {
            "income": 75000.0,
            "deductions": 10000.0
        })
    ]
    
    # Test 1: HTTP Server Mode
    print("🌐 Starting HTTP MCP Server...")
    server_process = multiprocessing.Process(target=start_http_mcp_server, daemon=True)
    server_process.start()
    await asyncio.sleep(3)  # Wait for server to start
    
    print("\n📊 Testing HTTP Mode:")
    print("-" * 40)
    
    http_times = []
    for tool_name, params in test_operations:
        start_time = time.time()
        
        # Simulate HTTP call (you'd normally use aiohttp here)
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"http://localhost:8000/mcp/invoke/{tool_name}"
            async with session.post(url, json=params) as response:
                result = await response.json()
        
        elapsed = time.time() - start_time
        http_times.append(elapsed)
        print(f"  {tool_name}: {elapsed*1000:.2f}ms")
    
    http_total = sum(http_times)
    print(f"\n  Total HTTP time: {http_total*1000:.2f}ms")
    
    server_process.terminate()
    server_process.join()
    
    # Test 2: In-Process Mode
    print("\n📊 Testing In-Process Mode:")
    print("-" * 40)
    
    inprocess_server = expose_tools_inprocess(
        tools=[
            create_transaction,
            get_financial_summary,
            generate_invoice,
            calculate_tax
        ],
        verbose=False
    )
    
    inprocess_times = []
    for tool_name, params in test_operations:
        start_time = time.time()
        result = await inprocess_server.invoke(tool_name, params)
        elapsed = time.time() - start_time
        inprocess_times.append(elapsed)
        print(f"  {tool_name}: {elapsed*1000:.2f}ms")
    
    inprocess_total = sum(inprocess_times)
    print(f"\n  Total In-Process time: {inprocess_total*1000:.2f}ms")
    
    # Comparison
    speedup = ((http_total - inprocess_total) / http_total) * 100
    
    print("\n" + "="*70)
    print("📈 PERFORMANCE SUMMARY")
    print("="*70)
    print(f"\n  HTTP Mode:        {http_total*1000:.2f}ms")
    print(f"  In-Process Mode:  {inprocess_total*1000:.2f}ms")
    print(f"\n  🚀 Speedup:       {speedup:.1f}% faster")
    print("\n  Benefits of In-Process:")
    print("    • No network overhead")
    print("    • No serialization/deserialization")
    print("    • Direct function calls")
    print("    • Better for embedded agents")
    print("\n  Benefits of HTTP:")
    print("    • Language agnostic")
    print("    • Distributed architecture")
    print("    • Scalability")
    print("    • Isolation")
    print("="*70 + "\n")


async def agent_mode_comparison():
    """Compare agents using HTTP vs In-Process servers."""
    print("\n" + "="*70)
    print("🤖 AGENT COMPARISON: HTTP vs IN-PROCESS")
    print("="*70 + "\n")
    
    llm = create_llm_provider()
    query = """Record these transactions and calculate tax:
    - Income: $50000
    - Expense: Rent $2000
    - Expense: Food $500
    Calculate tax on income with $5000 deductions."""
    
    print(f"📋 Task: {query}\n")
    
    # Test 1: Agent with HTTP Server
    print("🌐 Agent with HTTP MCP Server:")
    print("-" * 40)
    
    server_process = multiprocessing.Process(target=start_http_mcp_server, daemon=True)
    server_process.start()
    await asyncio.sleep(3)
    
    http_agent = CodeModeAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        verbose=True
    )
    
    start_time = time.time()
    try:
        result = http_agent.run(query)
        http_time = time.time() - start_time
        print(f"\n✅ Result: {result}")
        print(f"⏱️  Time: {http_time:.2f}s")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        http_time = 0
    
    server_process.terminate()
    server_process.join()
    
    # Test 2: Agent with In-Process Server
    print("\n\n🚀 Agent with In-Process MCP Server:")
    print("-" * 40)
    
    inprocess_server = expose_tools_inprocess(
        tools=[
            create_transaction,
            get_financial_summary,
            generate_invoice,
            calculate_tax
        ],
        verbose=True
    )
    
    inprocess_agent = InProcessCodeModeAgent(
        llm_provider=llm,
        inprocess_server=inprocess_server,
        verbose=True
    )
    
    start_time = time.time()
    try:
        result = await inprocess_agent.run_async(query)
        inprocess_time = time.time() - start_time
        print(f"\n✅ Result: {result}")
        print(f"⏱️  Time: {inprocess_time:.2f}s")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        inprocess_time = 0
    
    # Comparison
    if http_time > 0 and inprocess_time > 0:
        speedup = ((http_time - inprocess_time) / http_time) * 100
        
        print("\n" + "="*70)
        print("📊 AGENT PERFORMANCE COMPARISON")
        print("="*70)
        print(f"\n  HTTP Agent:       {http_time:.2f}s")
        print(f"  In-Process Agent: {inprocess_time:.2f}s")
        print(f"\n  🚀 Speedup:       {speedup:.1f}% faster")
        print("="*70 + "\n")


# ============================================================================
# INTERACTIVE MODE
# ============================================================================

async def interactive_dual_mode():
    """Interactive mode with choice of HTTP or In-Process."""
    print("\n" + "="*70)
    print("🎭 DUAL MODE MCP - INTERACTIVE")
    print("="*70 + "\n")
    
    print("Choose mode:")
    print("  1. HTTP Server (traditional)")
    print("  2. In-Process (faster)")
    print("  3. Side-by-side comparison")
    
    choice = input("\nYour choice (1-3): ").strip()
    
    llm = create_llm_provider()
    
    if choice == "1":
        # HTTP Mode
        print("\n🌐 Starting HTTP Mode...")
        server_process = multiprocessing.Process(target=start_http_mcp_server, daemon=True)
        server_process.start()
        await asyncio.sleep(3)
        
        agent = CodeModeAgent(
            llm_provider=llm,
            mcp_servers=["http://localhost:8000/mcp"],
            verbose=True
        )
        
        print("\nReady! Type 'quit' to exit.\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    break
                
                if not user_input:
                    continue
                
                result = agent.run(user_input)
                print(f"\n🤖 Agent: {result}\n")
            
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
        
        server_process.terminate()
        server_process.join()
    
    elif choice == "2":
        # In-Process Mode
        print("\n🚀 Starting In-Process Mode...")
        
        server = expose_tools_inprocess(
            tools=[
                create_transaction,
                get_financial_summary,
                generate_invoice,
                calculate_tax
            ],
            verbose=True
        )
        
        agent = InProcessCodeModeAgent(
            llm_provider=llm,
            inprocess_server=server,
            verbose=True
        )
        
        print("\nReady! Type 'quit' to exit.\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    break
                
                if not user_input:
                    continue
                
                result = await agent.run_async(user_input)
                print(f"\n🤖 Agent: {result}\n")
            
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
    
    else:
        # Comparison Mode
        await agent_mode_comparison()
    
    print("\n👋 Goodbye!")


# ============================================================================
# MAIN
# ============================================================================

async def main_async():
    """Async main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Dual Mode MCP Example")
    parser.add_argument(
        '--mode',
        choices=['test-inprocess', 'compare-servers', 'compare-agents', 'interactive'],
        default='compare-servers',
        help='Run mode'
    )
    
    args = parser.parse_args()
    
    if args.mode == 'test-inprocess':
        await test_inprocess_mode()
    elif args.mode == 'compare-servers':
        await compare_server_modes()
    elif args.mode == 'compare-agents':
        await agent_mode_comparison()
    else:
        await interactive_dual_mode()


def main():
    """Main entry point."""
    print("\n📋 Dual Mode MCP Example")
    print("  Demonstrates both HTTP and In-Process server modes")
    print()
    
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()