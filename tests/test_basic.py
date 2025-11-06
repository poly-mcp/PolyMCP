"""
Basic Tests for PolyMCP
Production-ready test suite for core functionality.
"""

import pytest
from fastapi.testclient import TestClient
from polymcp_toolkit import expose_tools


def test_simple_tool_exposure():
    """Test exposing a simple function as MCP tool."""
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    
    app = expose_tools(add)
    client = TestClient(app)
    
    response = client.get("/mcp/list_tools")
    assert response.status_code == 200
    
    data = response.json()
    assert "tools" in data
    assert len(data["tools"]) == 1
    assert data["tools"][0]["name"] == "add"


def test_tool_invocation():
    """Test invoking an MCP tool."""
    def multiply(x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y
    
    app = expose_tools(multiply)
    client = TestClient(app)
    
    response = client.post(
        "/mcp/invoke/multiply",
        json={"x": 5, "y": 3}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] == 15


def test_multiple_tools():
    """Test exposing multiple tools."""
    def add(a: int, b: int) -> int:
        """Add numbers."""
        return a + b
    
    def subtract(a: int, b: int) -> int:
        """Subtract numbers."""
        return a - b
    
    app = expose_tools([add, subtract])
    client = TestClient(app)
    
    response = client.get("/mcp/list_tools")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["tools"]) == 2
    
    tool_names = {tool["name"] for tool in data["tools"]}
    assert "add" in tool_names
    assert "subtract" in tool_names


def test_tool_with_default_params():
    """Test tool with default parameters."""
    def greet(name: str, greeting: str = "Hello") -> str:
        """Greet someone."""
        return f"{greeting}, {name}!"
    
    app = expose_tools(greet)
    client = TestClient(app)
    
    response = client.post(
        "/mcp/invoke/greet",
        json={"name": "Alice"}
    )
    assert response.status_code == 200
    assert response.json()["result"] == "Hello, Alice!"
    
    response = client.post(
        "/mcp/invoke/greet",
        json={"name": "Bob", "greeting": "Hi"}
    )
    assert response.status_code == 200
    assert response.json()["result"] == "Hi, Bob!"


def test_invalid_tool_name():
    """Test invoking non-existent tool."""
    def dummy() -> str:
        """Dummy function."""
        return "dummy"
    
    app = expose_tools(dummy)
    client = TestClient(app)
    
    response = client.post("/mcp/invoke/nonexistent", json={})
    assert response.status_code == 404


def test_invalid_parameters():
    """Test invoking tool with invalid parameters."""
    def divide(a: int, b: int) -> float:
        """Divide two numbers."""
        return a / b
    
    app = expose_tools(divide)
    client = TestClient(app)
    
    response = client.post("/mcp/invoke/divide", json={"a": 10})
    assert response.status_code == 422


def test_root_endpoint():
    """Test root endpoint."""
    def sample() -> str:
        """Sample function."""
        return "sample"
    
    app = expose_tools(sample)
    client = TestClient(app)
    
    response = client.get("/")
    assert response.status_code == 200
    
    data = response.json()
    assert "endpoints" in data
    assert "available_tools" in data
    assert "sample" in data["available_tools"]


@pytest.mark.asyncio
async def test_async_tool():
    """Test async tool function."""
    import asyncio
    
    async def async_add(a: int, b: int) -> int:
        """Add two numbers asynchronously."""
        await asyncio.sleep(0.01)
        return a + b
    
    app = expose_tools(async_add)
    client = TestClient(app)
    
    response = client.post(
        "/mcp/invoke/async_add",
        json={"a": 3, "b": 7}
    )
    assert response.status_code == 200
    assert response.json()["result"] == 10


def test_tool_schema_generation():
    """Test that tool schemas are generated correctly."""
    def process(text: str, count: int = 10) -> str:
        """Process text."""
        return text[:count]
    
    app = expose_tools(process)
    client = TestClient(app)
    
    response = client.get("/mcp/list_tools")
    assert response.status_code == 200
    
    tool = response.json()["tools"][0]
    assert "input_schema" in tool
    assert "output_schema" in tool
    
    schema = tool["input_schema"]
    assert "properties" in schema
    assert "text" in schema["properties"]
    assert "count" in schema["properties"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])