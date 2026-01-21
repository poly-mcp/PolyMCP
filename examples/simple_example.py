#!/usr/bin/env python3
"""
Simple PolyMCP Example - Guaranteed to Work

This is the simplest possible example to get started with PolyMCP.
No external dependencies required beyond the core package.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def create_simple_tool():
    """Create a simple MCP tool server."""
    from polymcp.polymcp_toolkit import expose_tools
    
    def greet(name: str) -> str:
        """
        Greet someone by name.
        
        Args:
            name: The person's name
            
        Returns:
            A friendly greeting
        """
        return f"Hello, {name}! Welcome to PolyMCP."
    
    def add(a: int, b: int) -> int:
        """
        Add two numbers together.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            The sum of a and b
        """
        return a + b
    
    def reverse(text: str) -> str:
        """
        Reverse a text string.
        
        Args:
            text: Text to reverse
            
        Returns:
            Reversed text
        """
        return text[::-1]
    
    # Create FastAPI app with all tools
    app = expose_tools(
        tools=[greet, add, reverse],
        title="Simple MCP Server",
        description="Example server with basic tools",
        version="1.0.0"
    )
    
    return app


def main():
    """Main function to run the server."""
    print("\n" + "="*60)
    print("🚀 Simple PolyMCP Server")
    print("="*60)
    print()
    print("This server provides 3 tools:")
    print("  1. greet(name) - Greet someone")
    print("  2. add(a, b) - Add two numbers")
    print("  3. reverse(text) - Reverse text")
    print()
    print("Server will start on: http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("List tools: http://localhost:8000/mcp/list_tools")
    print()
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")
    
    try:
        import uvicorn
        app = create_simple_tool()
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped. Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure you've installed dependencies:")
        print("  pip install -r requirements.txt")
        sys.exit(1)


if __name__ == "__main__":
    main()