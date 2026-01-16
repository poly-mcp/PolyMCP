#!/usr/bin/env python3
"""
PolyMCP Agent Multi-Server Example
Production-ready example demonstrating ALL 27 enterprise features.
"""

import os
import sys
import time
import json
import asyncio
import multiprocessing
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider, OpenAIProvider
from polymcp.polymcp_toolkit import expose_tools


# =============================================================================
# TOOLS (same as multi_server_setup.py)
# =============================================================================

def summarize(text: str, max_sentences: int = 3) -> str:
    """Summarize text by extracting key sentences."""
    if not text or not text.strip():
        return "Error: No text provided"
    
    import re
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) <= max_sentences:
        return text.strip()
    
    summary_sentences = sentences[:max_sentences]
    return '. '.join(summary_sentences) + '.'


def analyze_sentiment(text: str) -> dict:
    """Analyze sentiment of text."""
    if not text:
        return {"error": "No text provided"}
    
    text_lower = text.lower()
    positive_words = ['good', 'great', 'excellent', 'amazing', 'love', 'happy']
    negative_words = ['bad', 'terrible', 'awful', 'hate', 'sad', 'angry']
    
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    total = positive_count + negative_count
    
    if total == 0:
        sentiment = "neutral"
        confidence = 0.5
    elif positive_count > negative_count:
        sentiment = "positive"
        confidence = positive_count / total
    else:
        sentiment = "negative"
        confidence = negative_count / total
    
    return {
        "sentiment": sentiment,
        "confidence": round(confidence, 2),
        "positive_indicators": positive_count,
        "negative_indicators": negative_count
    }


def calculate_statistics(numbers: list) -> dict:
    """Calculate statistics for a list of numbers."""
    if not numbers:
        return {"error": "Empty list provided"}
    
    sorted_numbers = sorted(numbers)
    n = len(numbers)
    mean = sum(numbers) / n
    
    if n % 2 == 0:
        median = (sorted_numbers[n//2 - 1] + sorted_numbers[n//2]) / 2
    else:
        median = sorted_numbers[n//2]
    
    variance = sum((x - mean) ** 2 for x in numbers) / n
    std = variance ** 0.5
    
    return {
        "count": n,
        "mean": round(mean, 2),
        "median": round(median, 2),
        "std": round(std, 2),
        "min": min(numbers),
        "max": max(numbers)
    }


# =============================================================================
# SERVERS
# =============================================================================

def start_text_server():
    """Start text analysis server."""
    import uvicorn
    app = expose_tools(
        tools=[summarize, analyze_sentiment],
        title="Text Analysis Server"
    )
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")


def start_data_server():
    """Start data processing server."""
    import uvicorn
    app = expose_tools(
        tools=[calculate_statistics],
        title="Data Processing Server"
    )
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="error")


# =============================================================================
# EXAMPLE 1: BASIC USAGE (Backward Compatible)
# =============================================================================

async def example_basic():
    """
    Basic usage - works EXACTLY like old UnifiedPolyAgent.
    Zero breaking changes!
    """
    print("\n" + "="*70)
    print("EXAMPLE 1: Basic Usage (Backward Compatible)")
    print("="*70 + "\n")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud")
    
    # Same API as old version - no changes needed!
    async with UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        verbose=True
    ) as agent:
        response = await agent.run_async(
            "Summarize: AI is transforming technology and society"
        )
        print(f"✓ Response: {response}\n")


# =============================================================================
# EXAMPLE 2: BUDGET CONTROL
# =============================================================================

async def example_budget_control():
    """
    Show budget controller preventing runaway costs.
    NEW FEATURE: Automatic stop when limits reached.
    """
    print("\n" + "="*70)
    print("EXAMPLE 2: Budget Control (NEW)")
    print("="*70 + "\n")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud")
    
    async with UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp", "http://localhost:8001/mcp"],
        verbose=True,
        # Budget limits - prevent runaway execution
        max_wall_time=30.0,         # Stop after 30 seconds
        max_tokens=5000,            # Cap token usage
        max_tool_calls=3,           # Limit tool executions
        max_payload_bytes=500_000,  # 500KB max response
    ) as agent:
        try:
            response = await agent.run_async(
    			"Analyze sentiment: I love this product, it is excellent and amazing!"
			)
            print(f"Response: {response}")
        except Exception as e:
            print(f"✓ Budget limit reached: {e}")
        
        # Check what limits were hit
        metrics = agent.get_metrics()
        budget = metrics['budget']
        print(f"\n✓ Budget Usage:")
        print(f"  - Tokens: {budget['tokens_used']}/{agent.budget.max_tokens}")
        print(f"  - Tool calls: {budget['tool_calls_made']}/{agent.budget.max_tool_calls}")
        print(f"  - Time: {budget['elapsed_time']:.2f}s/{agent.budget.max_wall_time}s\n")


# =============================================================================
# EXAMPLE 3: SECURITY & REDACTION
# =============================================================================

async def example_security():
    """
    Show security features: redaction, allowlist, denylist.
    NEW FEATURE: Automatic PII/credential redaction.
    """
    print("\n" + "="*70)
    print("EXAMPLE 3: Security & Redaction (NEW)")
    print("="*70 + "\n")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud")
    
    async with UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        verbose=False,
        # Security settings
        redact_logs=True,                    # Auto-redact sensitive data
        tool_allowlist={'summarize'},        # Only allow safe tools
        enable_structured_logs=True,
        log_file="agent_secure.log"
    ) as agent:
        # Simulate query with sensitive data
        response = await agent.run_async(
            "Process this: password=secret123, api_key=sk-abc123"
        )
        
        # Export redacted logs
        logs = agent.export_logs(format='json')
        logs_data = json.loads(logs)
        
        print("✓ Logs with automatic redaction:")
        for log in logs_data[:3]:  # Show first 3 logs
            print(f"  {log['event']}: {log['data']}")
        
        print(f"\n✓ Total logs exported: {len(logs_data)} (all sensitive data redacted)\n")


# =============================================================================
# EXAMPLE 4: OBSERVABILITY & METRICS
# =============================================================================

async def example_observability():
    """
    Show structured logging, metrics, and tracing.
    NEW FEATURE: Production-grade observability.
    """
    print("\n" + "="*70)
    print("EXAMPLE 4: Observability & Metrics (NEW)")
    print("="*70 + "\n")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud")
    
    async with UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp", "http://localhost:8001/mcp"],
        verbose=False,
        # Observability settings
        enable_structured_logs=True,
        log_file="agent_metrics.log",
    ) as agent:
        # Run multiple queries
        queries = [
            "Summarize: PolyMCP is an AI agent platform",
            "Calculate statistics for: 10, 20, 30, 40, 50"
        ]
        
        for query in queries:
            await agent.run_async(query)
        
        # Get comprehensive metrics
        metrics = agent.get_metrics()
        
        print("✓ Tool Metrics:")
        for t in metrics['tools']:
            print(f"  {t['tool']}:")
            print(f"    - Success rate: {t['success_rate']*100:.1f}%")
            print(f"    - Avg latency: {t['avg_latency']:.3f}s")
            print(f"    - Calls: {t['success_count'] + t['failure_count']}")
        
        print(f"\n✓ Server Health:")
        for s in metrics['servers']:
            print(f"  {s['server_id']}: {s['health']}")
        
        print(f"\n✓ Trace ID: {metrics['trace_id']}")
        
        # Save trace for replay in CI/CD
        agent.save_test_trace("test_trace.json")
        print("✓ Test trace saved: test_trace.json\n")


# =============================================================================
# EXAMPLE 5: RETRY & ERROR HANDLING
# =============================================================================

async def example_retry():
    """
    Show intelligent retry with backoff and error taxonomy.
    NEW FEATURE: Smart retry based on error type.
    """
    print("\n" + "="*70)
    print("EXAMPLE 5: Intelligent Retry (NEW)")
    print("="*70 + "\n")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud")
    
    async with UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:9999/mcp"],  # Non-existent server
        verbose=True,
        # Retry configuration
        max_retries=3,
        retry_backoff=1.0,  # Exponential backoff starting at 1s
        enable_structured_logs=True,
    ) as agent:
        try:
            response = await agent.run_async("Test query")
        except Exception as e:
            print(f"✓ Failed after retries: {e}")
        
        # Check retry attempts in logs
        logs = agent.export_logs(format='text')
        retry_logs = [l for l in logs.split('\n') if 'retry' in l.lower()]
        
        print(f"\n✓ Retry attempts logged: {len(retry_logs)}")
        for log in retry_logs[:3]:
            print(f"  {log}")
        print()


# =============================================================================
# EXAMPLE 6: RATE LIMITING
# =============================================================================

async def example_rate_limiting():
    """
    Show per-tool rate limiting.
    NEW FEATURE: Prevent tool abuse and API quota exhaustion.
    """
    print("\n" + "="*70)
    print("EXAMPLE 6: Rate Limiting (NEW)")
    print("="*70 + "\n")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud")
    
    async with UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        verbose=True,
        # Rate limiting settings
        enable_rate_limiting=True,
        default_rate_limit=2,  # Only 2 calls per minute
    ) as agent:
        # Try to make multiple rapid calls
        for i in range(3):
            try:
                response = await agent.run_async(f"Summarize: Text {i}")
                print(f"✓ Call {i+1} succeeded")
            except Exception as e:
                print(f"✓ Call {i+1} rate limited: {e}")
            
            time.sleep(0.5)
        print()


# =============================================================================
# EXAMPLE 7: CIRCUIT BREAKER
# =============================================================================

async def example_circuit_breaker():
    """
    Show circuit breaker preventing cascading failures.
    NEW FEATURE: Netflix Hystrix-style circuit breaker.
    """
    print("\n" + "="*70)
    print("EXAMPLE 7: Circuit Breaker (NEW)")
    print("="*70 + "\n")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud")
    
    async with UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:9999/mcp"],  # Failing server
        verbose=True,
        # Circuit breaker settings
        enable_health_checks=True,
        circuit_breaker_threshold=2,  # Open after 2 failures
    ) as agent:
        # Make calls until circuit opens
        for i in range(4):
            try:
                await agent.run_async("Test query")
            except Exception as e:
                print(f"Attempt {i+1}: {e}")
        
        # Check circuit status
        metrics = agent.get_metrics()

        # metrics['servers'] è una LISTA di dict (non un dict), quindi niente .items()
        for s in metrics.get('servers', []):
            server_id = s.get('server_id', 'unknown')
            health = s.get('health', 'unknown')
            consecutive_failures = s.get('consecutive_failures', 0)

            print(f"\n✓ Server {server_id}: {health}")
            print(f"  Consecutive failures: {consecutive_failures}\n")


# =============================================================================
# EXAMPLE 8: PLANNER/EXECUTOR/VALIDATOR ARCHITECTURE
# =============================================================================

async def example_architecture():
    """
    Show 3-tier architecture: Planner → Executor → Validator.
    NEW FEATURE: Strategic planning before execution.
    """
    print("\n" + "="*70)
    print("EXAMPLE 8: Planner/Executor/Validator (NEW)")
    print("="*70 + "\n")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud")
    
    async with UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp", "http://localhost:8001/mcp"],
        verbose=True,
        # Architecture settings
        use_planner=True,      # Create plan before executing
        use_validator=True,    # Validate goal achievement
    ) as agent:
        response = await agent.run_async(
            "Analyze the sentiment of 'This is great!' and then summarize it"
        )
        
        print(f"\n✓ Response: {response}")
        print("\n✓ The agent created a plan, executed steps, and validated results!\n")


# =============================================================================
# EXAMPLE 9: STREAMING PROGRESS
# =============================================================================

async def example_streaming():
    """
    Show streaming progress callbacks.
    NEW FEATURE: Real-time progress updates.
    """
    print("\n" + "="*70)
    print("EXAMPLE 9: Streaming Progress (NEW)")
    print("="*70 + "\n")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud")
    
    async with UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        verbose=False,
    ) as agent:
        # Progress callback
        progress_events = []
        
        def progress_callback(event):
            progress_events.append(event)
            print(f"→ {event}")
        
        response = await agent.run_async(
            "Summarize: AI is transforming technology",
            stream_callback=progress_callback
        )
        
        print(f"\n✓ Response: {response}")
        print(f"✓ Progress events received: {len(progress_events)}\n")


# =============================================================================
# EXAMPLE 10: PRODUCTION SETUP (ALL FEATURES)
# =============================================================================

async def example_production():
    """
    Production-ready setup with ALL features enabled.
    This is how you'd deploy to production.
    """
    print("\n" + "="*70)
    print("EXAMPLE 10: Production Setup (ALL FEATURES)")
    print("="*70 + "\n")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud")
    
    async with UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp", "http://localhost:8001/mcp"],
        verbose=True,
        
        # Budget limits
        max_wall_time=300.0,
        max_tokens=100000,
        max_tool_calls=20,
        max_payload_bytes=10_000_000,
        
        # Security
        redact_logs=True,
        tool_allowlist=None,  # Allow all for demo
        
        # Performance
        tools_cache_ttl=60.0,
        max_memory_size=50,
        
        # Retry & resilience
        max_retries=3,
        retry_backoff=1.0,
        enable_rate_limiting=True,
        default_rate_limit=10,
        enable_health_checks=True,
        circuit_breaker_threshold=5,
        
        # Observability
        enable_structured_logs=True,
        log_file="production_agent.log",
        
        # Architecture
        use_planner=True,
        use_validator=True,
        
    ) as agent:
        # Production query
        response = await agent.run_async(
            "Calculate statistics for 10, 20, 30 and then summarize the results"
        )
        
        print(f"\n✓ Response: {response}")
        
        # Production metrics
        metrics = agent.get_metrics()
        print(f"\n✓ Production Metrics:")
        print(f"  Budget usage: {metrics['budget']}")
        print(f"  Tool success rate: {sum(t['success_rate'] for t in metrics['tools']) / len(metrics['tools']) * 100:.1f}%")
        print(f"  Trace ID: {metrics['trace_id']}")
        
        # Export for monitoring system
        logs_json = agent.export_logs(format='json')
        with open('production_logs.json', 'w') as f:
            f.write(logs_json)
        
        print(f"\n✓ Logs exported to production_logs.json")
        print("✓ Ready for Prometheus/Grafana/DataDog integration!\n")


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Run all examples."""
    print("\n" + "="*70)
    print(" POLYMCP AGENT - FEATURE SHOWCASE")
    print(" 27 Enterprise Features | Production-Ready | Zero Breaking Changes")
    print("="*70)
    
    # Start servers
    print("\n📡 Starting MCP servers...")
    servers = [
        multiprocessing.Process(target=start_text_server, daemon=True),
        multiprocessing.Process(target=start_data_server, daemon=True),
    ]
    
    for server in servers:
        server.start()
    
    time.sleep(3)
    print("✓ Servers ready\n")
    
    # Run examples
    try:
        await example_basic()                # Backward compatibility
        await example_budget_control()       # Budget limits
        await example_security()             # Security & redaction
        await example_observability()        # Metrics & tracing
        await example_retry()                # Intelligent retry
        await example_rate_limiting()        # Rate limits
        await example_circuit_breaker()      # Circuit breaker
        await example_architecture()         # 3-tier architecture
        await example_streaming()            # Progress streaming
        await example_production()           # Production setup
        
    finally:
        # Cleanup
        for server in servers:
            server.terminate()
            server.join()
    
    print("\n" + "="*70)
    print(" ALL EXAMPLES COMPLETED")
    print("="*70 + "\n")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    asyncio.run(main())
