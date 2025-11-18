#!/usr/bin/env python3
"""
Test MCP Server with Production Authentication
"""

import os
import sys
from pathlib import Path

# IMPORTANTE: Carica .env PRIMA di qualsiasi import che usa le variabili!
from dotenv import load_dotenv
load_dotenv()

# Verifica che sia stato caricato
if not os.getenv("MCP_SECRET_KEY"):
    print("❌ ERROR: MCP_SECRET_KEY not found in .env file!")
    print("📍 Current directory:", os.getcwd())
    print("📁 Looking for .env in:", Path(".env").absolute())
    sys.exit(1)

# Verifica Redis (opzionale per sviluppo)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
try:
    import redis
    r = redis.from_url(REDIS_URL)
    r.ping()
    print("✅ Redis connection OK")
except Exception as e:
    print(f"⚠️  Redis not available: {e}")
    print("   Using in-memory storage (NOT for production!)")
    
    # Mock redis for development
    class MockRedis:
        def __init__(self):
            self.data = {}
        def get(self, key):
            return self.data.get(key)
        def setex(self, key, ttl, value):
            self.data[key] = value
    
    # Replace redis in the module
    import polymcp_toolkit.mcp_auth as auth_module
    auth_module.redis_client = MockRedis()

# Importa dopo aver configurato tutto
import uvicorn
from fastapi import FastAPI, Depends, Request, HTTPException
from typing import Dict, Any
from polymcp_toolkit import expose_tools_http
from polymcp_toolkit.mcp_auth import (
    ProductionAuthenticator, 
    get_db, 
    User, 
    create_user,
    setup_auth_middleware,
    LoginRequest,
    RefreshRequest
)

# Your tools
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

def multiply_numbers(x: float, y: float) -> float:
    """Multiply two numbers."""
    return x * y

def get_system_info() -> dict:
    """Get system information."""
    import platform
    from datetime import datetime
    return {
        "system": platform.system(),
        "python_version": platform.python_version(),
        "timestamp": datetime.now().isoformat()
    }

# Create base server WITHOUT authentication first
base_app = expose_tools_http(
    tools=[add_numbers, multiply_numbers, get_system_info],
    title="Production MCP Server",
    description="MCP server with production authentication",
    verbose=os.getenv("MCP_VERBOSE", "false").lower() == "true"
)

# Create a new FastAPI app that wraps the base app
app = FastAPI(
    title="Authenticated MCP Server",
    description="MCP Server with Production Authentication",
    version="1.0.0"
)

# Setup authentication if enabled
if os.getenv("MCP_AUTH_ENABLED", "true").lower() == "true":
    # For development, disable HTTPS requirement
    enforce_https = os.getenv("MCP_REQUIRE_HTTPS", "true").lower() == "true"
    
    # Create authenticator
    authenticator = ProductionAuthenticator(enforce_https=enforce_https)
    
    # Setup security middleware
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
    app = setup_auth_middleware(app, allowed_origins)
    
    # Add auth endpoints
    @app.post("/auth/login")
    async def login(
        request: LoginRequest,
        req: Request,
        db = Depends(get_db)
    ):
        """Login to get JWT tokens"""
        return authenticator.login(request, req, db)
    
    @app.post("/auth/refresh")
    async def refresh_token(
        request: RefreshRequest,
        req: Request,
        db = Depends(get_db)
    ):
        """Refresh access token"""
        return authenticator.refresh(request, req, db)
    
    @app.post("/auth/logout")
    async def logout(
        req: Request,
        auth_data = Depends(authenticator.authenticate)
    ):
        """Logout and revoke token"""
        username, user = auth_data
        auth_header = req.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            db = next(get_db())
            return authenticator.logout(req, token, db)
        return {"message": "No token to revoke"}
    
    # Get original endpoints from base app
    original_list_tools = None
    original_invoke_tool = None
    
    for route in base_app.router.routes:
        if hasattr(route, 'path'):
            if route.path == "/mcp/list_tools":
                original_list_tools = route.endpoint
            elif route.path == "/mcp/invoke/{tool_name}":
                original_invoke_tool = route.endpoint
    
    # Add authenticated MCP endpoints
    @app.get("/mcp/list_tools")
    async def list_tools_auth(
        req: Request,
        auth_data = Depends(authenticator.authenticate)
    ):
        """List tools with authentication"""
        username, user = auth_data
        if original_list_tools:
            result = await original_list_tools()
        else:
            result = {"tools": []}
        result["authenticated_user"] = username
        return result
    
    @app.post("/mcp/invoke/{tool_name}")
    async def invoke_tool_auth(
        tool_name: str,
        req: Request,
        payload: Dict[str, Any] = None,
        auth_data = Depends(authenticator.authenticate)
    ):
        """Invoke tool with authentication"""
        username, user = auth_data
        if original_invoke_tool:
            result = await original_invoke_tool(tool_name, payload)
        else:
            raise HTTPException(status_code=404, detail="Tool endpoint not found")
        result["authenticated_user"] = username
        result["is_admin"] = user.is_admin
        return result
    
    # Add info endpoints
    @app.get("/")
    async def root():
        """Root endpoint"""
        return {
            "name": "Authenticated MCP Server",
            "auth_enabled": True,
            "endpoints": {
                "auth_info": "/auth/info",
                "login": "/auth/login",
                "list_tools": "/mcp/list_tools",
                "invoke_tool": "/mcp/invoke/{tool_name}"
            }
        }
    
    @app.get("/auth/info")
    async def auth_info():
        """Get authentication info"""
        return {
            "auth_enabled": True,
            "methods": ["api_key", "jwt"],
            "endpoints": {
                "login": "/auth/login",
                "refresh": "/auth/refresh", 
                "logout": "/auth/logout"
            },
            "https_required": enforce_https,
            "test_hint": "Use X-API-Key header or login to get Bearer token"
        }
    
    # Mount the original app's routes (for non-authenticated endpoints like /docs)
    for route in base_app.router.routes:
        if hasattr(route, 'path') and route.path not in ["/mcp/list_tools", "/mcp/invoke/{tool_name}"]:
            app.router.routes.append(route)
    
    print("🔐 Production Authentication ENABLED")
    print(f"   - API Key: Via X-API-Key header")
    print(f"   - JWT: Via Authorization: Bearer <token>")
    print(f"   - HTTPS Required: {enforce_https}")
    
    # Create default users from environment
    from polymcp_toolkit.mcp_auth import SessionLocal, User, hash_password
    db = SessionLocal()
    
    # Create users from API keys in environment
    created_users = []
    for key, value in os.environ.items():
        if key.startswith("MCP_API_KEY_"):
            username = key.replace("MCP_API_KEY_", "").lower()
            
            # Check if user exists
            existing = db.query(User).filter(User.username == username).first()
            if not existing:
                # Create user with API key
                user = User(
                    username=username,
                    hashed_password=hash_password(f"{username}123"),  # Default password
                    api_key=value,
                    is_active=True
                )
                db.add(user)
                created_users.append((username, f"{username}123", value))
                print(f"   ✅ Created user: {username}")
            else:
                # Update API key if different
                if existing.api_key != value:
                    existing.api_key = value
                    print(f"   ✅ Updated API key for: {username}")
    
    db.commit()
    db.close()
    
    if created_users:
        print("\n📋 Created Users (for JWT login):")
        for username, password, api_key in created_users:
            print(f"   - Username: {username}")
            print(f"     Password: {password}")
            print(f"     API Key: {api_key[:20]}...")
else:
    app = base_app
    print("🔓 Authentication DISABLED")

if __name__ == "__main__":
    # Get settings from .env
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_SERVER_PORT", "8000"))
    debug = os.getenv("MCP_DEBUG", "false").lower() == "true"
    
    print("\n" + "="*60)
    print("🚀 MCP Production Server")
    print("="*60)
    print(f"📍 URL: http://{host}:{port}")
    print(f"📚 API Docs: http://{host}:{port}/docs")
    print(f"🔧 Debug Mode: {debug}")
    print(f"🔐 Auth Info: http://{host}:{port}/auth/info")
    
    print("\n📋 Quick Test Commands:")
    print("\n1️⃣ Test without auth (should fail):")
    print("   curl http://localhost:8000/mcp/list_tools")
    
    print("\n2️⃣ Test with API key:")
    print("   curl http://localhost:8000/mcp/list_tools \\")
    print('     -H "X-API-Key: dev-polymcp-key-789"')
    
    print("\n3️⃣ Test JWT login:")
    print("   curl -X POST http://localhost:8000/auth/login \\")
    print('     -H "Content-Type: application/json" \\')
    print('     -d \'{"username": "polymcp", "password": "polymcp123"}\'')
    
    print("\n" + "="*60 + "\n")
    
    uvicorn.run(app, host=host, port=port)