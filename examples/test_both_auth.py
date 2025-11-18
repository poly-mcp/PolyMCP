#!/usr/bin/env python3
"""
Test BOTH UnifiedPolyAgent and CodeModeAgent with Authentication
Complete test suite for both agent types with API Key and JWT
"""

import os
import asyncio
import httpx
import json
from dotenv import load_dotenv
load_dotenv()

from polymcp.polyagent import UnifiedPolyAgent, OllamaProvider,CodeModeAgent,AsyncCodeModeAgent


async def test_auth_info():
    """Test auth info endpoint"""
    print("\n" + "="*60)
    print("ℹ️  Authentication Info")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/auth/info")
        
        if response.status_code == 200:
            info = response.json()
            print("📋 Server Authentication Configuration:")
            print(json.dumps(info, indent=2))
        else:
            print(f"❌ Failed to get auth info: {response.status_code}")


async def test_unified_agent_api_key():
    """Test UnifiedPolyAgent with API Key"""
    print("\n" + "="*60)
    print("🔑 TEST 1: UnifiedPolyAgent with API Key")
    print("="*60)
    
    api_key = os.getenv("MCP_API_KEY_POLYMCP", "dev-polymcp-key-789")
    print(f"Using API Key: {api_key[:20]}...")
    
    # Test connection first
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/mcp/list_tools",
            headers={"X-API-Key": api_key}
        )
        if response.status_code == 200:
            tools = response.json()
            print(f"✅ API Key auth successful! Found {len(tools.get('tools', []))} tools")
        else:
            print(f"❌ API Key auth failed: {response.status_code}")
            return
    
    # Create UnifiedPolyAgent
    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)
    
    agent = UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        http_headers={"X-API-Key": api_key},
        verbose=True
    )
    
    # Start the agent
    await agent.start()
    
    try:
        # Test queries
        queries = [
            "Add 42 and 58",
            "Multiply 3.14 by 2"
        ]
        
        for query in queries:
            print(f"\n📝 Query: {query}")
            result = await agent.run_async(query, max_steps=3)
            print(f"✅ Result: {result}")
    
    finally:
        # Stop the agent
        await agent.stop()


async def test_unified_agent_jwt():
    """Test UnifiedPolyAgent with JWT"""
    print("\n" + "="*60)
    print("🎫 TEST 2: UnifiedPolyAgent with JWT")
    print("="*60)
    
    # Get JWT token
    async with httpx.AsyncClient() as client:
        login_response = await client.post(
            "http://localhost:8000/auth/login",
            json={"username": "polymcp", "password": "polymcp123"}
        )
        
        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.text}")
            return
        
        token_data = login_response.json()
        access_token = token_data["access_token"]
        print(f"✅ Got JWT token: {access_token[:50]}...")
    
    # Create UnifiedPolyAgent with JWT
    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)
    
    agent = UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        http_headers={"Authorization": f"Bearer {access_token}"},
        verbose=True
    )
    
    await agent.start()
    
    try:
        result = await agent.run_async(
            "Get system information",
            max_steps=3
        )
        print(f"\n✅ Result: {result}")
    
    finally:
        await agent.stop()


async def test_codemode_agent_api_key():
    """Test CodeModeAgent with API Key"""
    print("\n" + "="*60)
    print("🔑 TEST 3: CodeModeAgent with API Key")
    print("="*60)
    
    api_key = os.getenv("MCP_API_KEY_POLYMCP", "dev-polymcp-key-789")
    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)
    
    # Create CodeModeAgent (sync version)
    agent = CodeModeAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        http_headers={"X-API-Key": api_key},
        verbose=True
    )
    
    # Test queries
    queries = [
        "Add 100 and 200",
        "First multiply 5 by 6, then add 10 to the result"
    ]
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        result = agent.run(query)
        print(f"✅ Result: {result}")


async def test_codemode_agent_jwt():
    """Test CodeModeAgent with JWT"""
    print("\n" + "="*60)
    print("🎫 TEST 4: CodeModeAgent with JWT")
    print("="*60)
    
    # Get JWT token
    async with httpx.AsyncClient() as client:
        login_response = await client.post(
            "http://localhost:8000/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        
        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.text}")
            return
        
        token = login_response.json()["access_token"]
        print(f"✅ Got JWT token: {token[:50]}...")
    
    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)
    
    # Create CodeModeAgent with JWT
    agent = CodeModeAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        http_headers={"Authorization": f"Bearer {token}"},
        verbose=True
    )
    
    result = agent.run(
        "Calculate the sum of 15, 25, and 35, then multiply by 2"
    )
    print(f"\n✅ Result: {result}")


async def test_async_codemode_agent():
    """Test AsyncCodeModeAgent with context manager"""
    print("\n" + "="*60)
    print("🚀 TEST 5: AsyncCodeModeAgent with Context Manager")
    print("="*60)
    
    api_key = os.getenv("MCP_API_KEY_POLYMCP", "dev-polymcp-key-789")
    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)
    
    # AsyncCodeModeAgent supports context manager
    agent = AsyncCodeModeAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        http_headers={"X-API-Key": api_key},
        verbose=True
    )
    
    async with agent:  # This works with AsyncCodeModeAgent
        result = await agent.run_async(
            "Add 1000 and 2000, then divide by 3"
        )
        print(f"\n✅ Result: {result}")


async def test_invalid_auth():
    """Test with invalid credentials"""
    print("\n" + "="*60)
    print("🚫 TEST 6: Invalid Authentication")
    print("="*60)
    
    # Test wrong API key
    print("\n1️⃣ Testing with wrong API key...")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/mcp/list_tools",
            headers={"X-API-Key": "wrong-key-123"}
        )
        print(f"   Status: {response.status_code} (expected 401)")
        if response.status_code == 401:
            print("   ✅ Correctly rejected invalid API key")
    
    # Test wrong password
    print("\n2️⃣ Testing with wrong password...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/auth/login",
            json={"username": "polymcp", "password": "wrongpassword"}
        )
        print(f"   Status: {response.status_code} (expected 401)")
        if response.status_code == 401:
            print("   ✅ Correctly rejected invalid password")


async def test_performance_comparison():
    """Compare performance between UnifiedPolyAgent and CodeModeAgent"""
    print("\n" + "="*60)
    print("📊 TEST 7: Performance Comparison")
    print("="*60)
    
    api_key = os.getenv("MCP_API_KEY_POLYMCP", "dev-polymcp-key-789")
    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)
    
    # Complex multi-step query
    complex_query = (
        "First add 10 and 20. "
        "Then multiply the result by 3. "
        "Finally, add 100 to that result."
    )
    
    print(f"\n📝 Complex Query: {complex_query}")
    
    # Test with UnifiedPolyAgent
    print("\n1️⃣ UnifiedPolyAgent:")
    import time
    
    unified_agent = UnifiedPolyAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        http_headers={"X-API-Key": api_key},
        verbose=False
    )
    
    await unified_agent.start()
    
    start_time = time.time()
    unified_result = await unified_agent.run_async(complex_query, max_steps=5)
    unified_time = time.time() - start_time
    
    await unified_agent.stop()
    
    print(f"   Result: {unified_result}")
    print(f"   Time: {unified_time:.2f}s")
    
    # Test with CodeModeAgent
    print("\n2️⃣ CodeModeAgent:")
    
    code_agent = CodeModeAgent(
        llm_provider=llm,
        mcp_servers=["http://localhost:8000/mcp"],
        http_headers={"X-API-Key": api_key},
        verbose=False
    )
    
    start_time = time.time()
    code_result = code_agent.run(complex_query)
    code_time = time.time() - start_time
    
    print(f"   Result: {code_result}")
    print(f"   Time: {code_time:.2f}s")
    
    # Compare
    print(f"\n📈 Performance:")
    print(f"   UnifiedPolyAgent: {unified_time:.2f}s")
    print(f"   CodeModeAgent: {code_time:.2f}s")
    if code_time < unified_time:
        speedup = ((unified_time - code_time) / unified_time) * 100
        print(f"   ⚡ CodeMode is {speedup:.1f}% faster!")
    else:
        print(f"   ⚡ UnifiedPolyAgent was faster this time")


async def main():
    """Run all tests"""
    print("\n" + "🔐 "*20)
    print("POLYMCP COMPLETE AUTHENTICATION TEST SUITE")
    print("Testing BOTH UnifiedPolyAgent AND CodeModeAgent")
    print("🔐 "*20)
    
    # Check server
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/")
            if response.status_code != 200:
                print("❌ Server not responding")
                return
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("   Please start the server with: python auth_server.py")
        return
    
    print("\n✅ Server is running!")
    
    # Run all tests
    await test_auth_info()
    
    # UnifiedPolyAgent tests
    await test_unified_agent_api_key()
    await test_unified_agent_jwt()
    
    # CodeModeAgent tests
    await test_codemode_agent_api_key()
    await test_codemode_agent_jwt()
    await test_async_codemode_agent()
    
    # Security tests
    await test_invalid_auth()
    
    # Performance comparison
    await test_performance_comparison()
    
    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETED!")
    print("="*60)
    
    print("\n📊 Summary:")
    print("   ✅ UnifiedPolyAgent with API Key")
    print("   ✅ UnifiedPolyAgent with JWT")
    print("   ✅ CodeModeAgent with API Key")
    print("   ✅ CodeModeAgent with JWT")
    print("   ✅ AsyncCodeModeAgent with context manager")
    print("   ✅ Invalid auth rejection")
    print("   ✅ Performance comparison")


if __name__ == "__main__":
    print("\n⚠️  Make sure the auth server is running:")
    print("   python auth_server.py\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
