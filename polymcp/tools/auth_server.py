#!/usr/bin/env python3
"""
Complete MCP Server with Production Authentication
Using add_production_auth_to_mcp helper
"""

import os
import sys
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Check required environment
if not os.getenv("MCP_SECRET_KEY"):
    print("❌ ERROR: MCP_SECRET_KEY not found!")
    print("Creating .env file with defaults...")
    with open(".env", "w") as f:
        f.write("""# MCP Authentication Configuration
MCP_SECRET_KEY=development-secret-key-minimum-32-characters-long
MCP_AUTH_ENABLED=true
MCP_REQUIRE_HTTPS=false
MCP_API_KEY_ADMIN=admin-api-key-123
MCP_API_KEY_USER=user-api-key-456
MCP_API_KEY_POLYMCP=dev-polymcp-key-789
DATABASE_URL=sqlite:///./mcp_auth.db
REDIS_URL=redis://localhost:6379
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8000
MCP_DEBUG=true
MCP_VERBOSE=true
""")
    print("✅ Created .env file. Please restart the server.")
    sys.exit(0)

# Mock Redis if not available
try:
    import redis
    redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379")).ping()
    print("✅ Redis connected")
except:
    print("⚠️  Redis not available, using mock")
    class MockRedis:
        def __init__(self):
            self.data = {}
        def get(self, key):
            return self.data.get(key)
        def setex(self, key, ttl, value):
            self.data[key] = value
    
    import polymcp_toolkit.mcp_auth as auth_module
    auth_module.redis_client = MockRedis()

# Now import everything
import uvicorn
from polymcp_toolkit import expose_tools_http
from polymcp_toolkit.mcp_auth import (
    ProductionAuthenticator,
    add_production_auth_to_mcp,
    SessionLocal,
    User,
    hash_password,
    Base,
    engine
)

# === DEFINE YOUR TOOLS ===
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
        "timestamp": datetime.now().isoformat(),
        "message": "Hello from authenticated MCP server!"
    }

# === CREATE AUTHENTICATED SERVER ===
print("\n🔧 Creating authenticated MCP server...")

# Step 1: Create base app with your tools
base_app = expose_tools_http(
    tools=[add_numbers, multiply_numbers, get_system_info],
    title="Production MCP Server",
    description="MCP server with production authentication",
    verbose=os.getenv("MCP_VERBOSE", "false").lower() == "true"
)

# Step 2: Create authenticator
enforce_https = os.getenv("MCP_REQUIRE_HTTPS", "false").lower() == "true"
authenticator = ProductionAuthenticator(enforce_https=enforce_https)

# Step 3: Apply authentication with the helper function
app = add_production_auth_to_mcp(
    base_app,
    authenticator,
    allowed_origins=os.getenv("ALLOWED_ORIGINS", "*").split(",")
)

print("✅ Authentication added successfully!")

# === CREATE USERS FROM ENVIRONMENT ===
print("\n📋 Setting up users...")

# Ensure database tables exist
Base.metadata.create_all(bind=engine)

db = SessionLocal()
created_count = 0

# Create users from environment variables
for key, value in os.environ.items():
    if key.startswith("MCP_API_KEY_"):
        username = key.replace("MCP_API_KEY_", "").lower()
        
        # Check if user exists
        existing = db.query(User).filter(User.username == username).first()
        if not existing:
            # Create new user
            user = User(
                username=username,
                hashed_password=hash_password(f"{username}123"),  # Default password
                api_key=value,
                is_active=True,
                is_admin=(username == "admin")
            )
            db.add(user)
            created_count += 1
            print(f"   ✅ Created user: {username}")
            print(f"      Password: {username}123")
            print(f"      API Key: {value[:20]}...")
        else:
            # Update API key if different
            if existing.api_key != value:
                existing.api_key = value
                print(f"   ✅ Updated API key for: {username}")
            else:
                print(f"   ✓ User {username} already exists")

db.commit()
db.close()

if created_count > 0:
    print(f"\n✅ Created {created_count} new users")

# === MAIN ===
if __name__ == "__main__":
    # Get settings from environment
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_SERVER_PORT", "8000"))
    debug = os.getenv("MCP_DEBUG", "false").lower() == "true"
    
    print("\n" + "="*60)
    print("🚀 MCP Production Server (with add_production_auth_to_mcp)")
    print("="*60)
    print(f"📍 URL: http://{host}:{port}")
    print(f"📚 API Docs: http://{host}:{port}/docs")
    print(f"🔐 Auth Info: http://{host}:{port}/auth/info")
    print(f"🔧 Debug Mode: {debug}")
    print(f"🔒 HTTPS Required: {enforce_https}")
    
    print("\n📋 Available Endpoints:")
    print("   - GET  /                      (Server info)")
    print("   - GET  /auth/info             (Auth configuration)")
    print("   - POST /auth/login            (Get JWT token)")
    print("   - POST /auth/refresh          (Refresh token)")
    print("   - POST /auth/logout           (Logout)")
    print("   - GET  /mcp/list_tools        (List tools - requires auth)")
    print("   - POST /mcp/invoke/{tool}     (Invoke tool - requires auth)")
    
    print("\n🧪 Quick Test Commands:")
    
    print("\n1️⃣ Test without auth (should fail with 401):")
    print("   curl http://localhost:8000/mcp/list_tools")
    
    print("\n2️⃣ Test with API key:")
    print("   curl http://localhost:8000/mcp/list_tools \\")
    print('     -H "X-API-Key: dev-polymcp-key-789"')
    
    print("\n3️⃣ Test JWT login:")
    print("   curl -X POST http://localhost:8000/auth/login \\")
    print('     -H "Content-Type: application/json" \\')
    print('     -d \'{"username": "polymcp", "password": "polymcp123"}\'')
    
    print("\n4️⃣ Use JWT token:")
    print("   curl http://localhost:8000/mcp/list_tools \\")
    print('     -H "Authorization: Bearer <token-from-login>"')
    
    print("\n" + "="*60)
    print("✨ Server starting...\n")
    
    # Run the server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info" if debug else "warning"
    )
