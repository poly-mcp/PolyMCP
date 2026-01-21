#!/usr/bin/env python3
"""
ONE-FILE: MCP Server + Full Auth Test Suite (API Key / JWT / OAuth2) + Agents (PolyAgent + Unified wrapper)

Run:
  python test_all_auth_onefile.py

Deps:
  pip install fastapi uvicorn pyjwt httpx

Optional (if you use env vars):
  pip install python-dotenv
"""

import os
import time
import json
import asyncio
import threading
from typing import Any, Dict, Optional

import httpx

# ----------------------------
# MCP Server (FastAPI)
# ----------------------------
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

import jwt  # PyJWT


# ----------------------------
# Your package imports
# ----------------------------
# These must exist in your installed/editable package after you copied the files.
from polymcp.polyagent import (
    PolyAgent,
    UnifiedPolyAgentWithAuth,
    OllamaProvider,
    StaticHeadersAuth,
    JWTAuthProvider,
    OAuth2Provider,
)

# ----------------------------
# Server Config (dev)
# ----------------------------
HOST = "127.0.0.1"
PORT = 8000
BASE_URL = f"http://{HOST}:{PORT}"

# API KEY settings
MCP_API_KEY = os.getenv("MCP_API_KEY_POLYMCP", "dev-polymcp-key")

# JWT settings (custom auth endpoints)
JWT_SECRET = os.getenv("MCP_JWT_SECRET", "dev-secret-change-me")
JWT_ISSUER = "polymcp-auth-server"
JWT_AUDIENCE = "polymcp-mcp"
JWT_EXPIRES_IN = 60  # seconds (short on purpose to test refresh)

# OAuth2 settings (toy IdP inside this same server)
OAUTH2_TOKEN_URL = f"{BASE_URL}/oauth/token"
OAUTH2_CLIENT_ID = os.getenv("OAUTH2_CLIENT_ID", "polymcp-client")
OAUTH2_CLIENT_SECRET = os.getenv("OAUTH2_CLIENT_SECRET", "polymcp-secret")
OAUTH2_EXPIRES_IN = 60  # seconds
OAUTH2_SCOPE_DEFAULT = "mcp.tools"

# Demo users (JWT login)
USERS = {
    "polymcp": "polymcp123",
    "admin": "admin123",
}

# In-memory stores for refresh tokens (DEV ONLY)
JWT_REFRESH_STORE: Dict[str, Dict[str, Any]] = {}
OAUTH_REFRESH_STORE: Dict[str, Dict[str, Any]] = {}


def _now() -> int:
    return int(time.time())


def _make_jwt(sub: str, expires_in: int = JWT_EXPIRES_IN) -> str:
    payload = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": sub,
        "iat": _now(),
        "exp": _now() + int(expires_in),
        "scope": OAUTH2_SCOPE_DEFAULT,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _verify_jwt_token(token: str) -> Dict[str, Any]:
    try:
        decoded = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
        return decoded
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token_expired")
    except Exception:
        raise HTTPException(status_code=401, detail="token_invalid")


def _require_api_key(req: Request) -> None:
    key = req.headers.get("X-API-Key")
    if not key or key != MCP_API_KEY:
        raise HTTPException(status_code=401, detail="invalid_api_key")


def _require_bearer(req: Request) -> Dict[str, Any]:
    auth = req.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer")
    token = auth.split(" ", 1)[1].strip()
    return _verify_jwt_token(token)


def _auth_guard(req: Request) -> Dict[str, Any]:
    """
    Auth strategy:
      - if X-API-Key present => validate API key
      - else if Authorization Bearer present => validate JWT
      - else => 401

    This lets you test all auth methods against same MCP routes.
    """
    if req.headers.get("X-API-Key"):
        _require_api_key(req)
        return {"auth": "api_key"}
    if req.headers.get("Authorization"):
        claims = _require_bearer(req)
        claims["auth"] = "bearer"
        return claims
    raise HTTPException(status_code=401, detail="missing_auth")


# ----------------------------
# MCP Tools
# ----------------------------
def tool_add(a: float, b: float) -> Dict[str, Any]:
    return {"result": a + b}

def tool_multiply(a: float, b: float) -> Dict[str, Any]:
    return {"result": a * b}

def tool_system_info() -> Dict[str, Any]:
    import platform
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }

TOOLS = [
    {
        "name": "add",
        "description": "Add two numbers",
        "input_schema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
    {
        "name": "multiply",
        "description": "Multiply two numbers",
        "input_schema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
    {
        "name": "system_info",
        "description": "Get system information",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

TOOL_FUNCS = {
    "add": tool_add,
    "multiply": tool_multiply,
    "system_info": tool_system_info,
}


# ----------------------------
# FastAPI app
# ----------------------------
app = FastAPI(title="PolyMCP Auth Test Server", version="1.0.0")


@app.get("/")
async def root():
    return {"status": "ok", "server": "polymcp-auth-test"}


@app.get("/auth/info")
async def auth_info():
    return {
        "api_key": {"header": "X-API-Key", "enabled": True},
        "jwt": {"enabled": True, "login": "/auth/login", "refresh": "/auth/refresh"},
        "oauth2": {"enabled": True, "token_endpoint": "/oauth/token", "supported_grants": ["client_credentials", "refresh_token"]},
        "mcp": {"base": "/mcp"},
    }


@app.post("/auth/login")
async def auth_login(payload: Dict[str, Any]):
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="missing_credentials")
    if USERS.get(username) != password:
        raise HTTPException(status_code=401, detail="invalid_credentials")

    access_token = _make_jwt(username, expires_in=JWT_EXPIRES_IN)
    refresh_token = f"jwt-rt-{username}-{_now()}"

    # DEV: store refresh token mapping
    JWT_REFRESH_STORE[refresh_token] = {"username": username, "issued_at": _now()}

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": JWT_EXPIRES_IN,
    }


@app.post("/auth/refresh")
async def auth_refresh(payload: Dict[str, Any]):
    rt = payload.get("refresh_token")
    if not rt or rt not in JWT_REFRESH_STORE:
        raise HTTPException(status_code=401, detail="invalid_refresh_token")

    username = JWT_REFRESH_STORE[rt]["username"]
    access_token = _make_jwt(username, expires_in=JWT_EXPIRES_IN)

    # rotate refresh token (optional)
    new_rt = f"jwt-rt-{username}-{_now()}"
    del JWT_REFRESH_STORE[rt]
    JWT_REFRESH_STORE[new_rt] = {"username": username, "issued_at": _now()}

    return {
        "access_token": access_token,
        "refresh_token": new_rt,
        "token_type": "Bearer",
        "expires_in": JWT_EXPIRES_IN,
    }


@app.post("/oauth/token")
async def oauth_token(req: Request):
    """
    OAuth2 token endpoint (DEV):

    - client_credentials:
        grant_type=client_credentials
        client_id, client_secret (either Basic Auth or form body)
        scope (optional)
      -> returns access_token + refresh_token

    - refresh_token:
        grant_type=refresh_token
        refresh_token=...
        client_id/client_secret (optional, but we accept)
    """
    form = await req.form()
    grant_type = form.get("grant_type")

    # client auth: allow Basic Auth OR form fields
    client_id = form.get("client_id")
    client_secret = form.get("client_secret")

    # basic auth
    basic = req.headers.get("Authorization", "")
    if basic.lower().startswith("basic "):
        import base64
        try:
            decoded = base64.b64decode(basic.split(" ", 1)[1]).decode("utf-8")
            client_id_b, client_secret_b = decoded.split(":", 1)
            client_id = client_id or client_id_b
            client_secret = client_secret or client_secret_b
        except Exception:
            raise HTTPException(status_code=401, detail="invalid_basic_auth")

    if client_id != OAUTH2_CLIENT_ID or client_secret != OAUTH2_CLIENT_SECRET:
        raise HTTPException(status_code=401, detail="invalid_client")

    scope = form.get("scope") or OAUTH2_SCOPE_DEFAULT

    if grant_type == "client_credentials":
        # mint token (JWT for simplicity)
        access_token = _make_jwt(sub=f"client:{client_id}", expires_in=OAUTH2_EXPIRES_IN)
        refresh_token = f"oauth-rt-{client_id}-{_now()}"
        OAUTH_REFRESH_STORE[refresh_token] = {"client_id": client_id, "scope": scope, "issued_at": _now()}

        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": OAUTH2_EXPIRES_IN,
                "refresh_token": refresh_token,
                "scope": scope,
            }
        )

    if grant_type == "refresh_token":
        rt = form.get("refresh_token")
        if not rt or rt not in OAUTH_REFRESH_STORE:
            raise HTTPException(status_code=401, detail="invalid_refresh_token")

        # rotate RT
        new_rt = f"oauth-rt-{client_id}-{_now()}"
        del OAUTH_REFRESH_STORE[rt]
        OAUTH_REFRESH_STORE[new_rt] = {"client_id": client_id, "scope": scope, "issued_at": _now()}

        access_token = _make_jwt(sub=f"client:{client_id}", expires_in=OAUTH2_EXPIRES_IN)
        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": OAUTH2_EXPIRES_IN,
                "refresh_token": new_rt,
                "scope": scope,
            }
        )

    raise HTTPException(status_code=400, detail="unsupported_grant_type")


@app.get("/mcp/list_tools")
async def mcp_list_tools(req: Request):
    _auth_guard(req)
    return {"tools": TOOLS}


@app.post("/mcp/invoke/{tool_name}")
async def mcp_invoke(tool_name: str, req: Request):
    _auth_guard(req)

    tool = TOOL_FUNCS.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="tool_not_found")

    payload = await req.json() if (req.headers.get("content-type") or "").startswith("application/json") else {}
    try:
        if tool_name in ("add", "multiply"):
            a = float(payload.get("a"))
            b = float(payload.get("b"))
            return tool(a, b)
        return tool()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad_input: {e}")


# ----------------------------
# Run server in background thread
# ----------------------------
def start_server_in_thread():
    import uvicorn
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)

    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # wait until server is ready
    for _ in range(50):
        try:
            r = httpx.get(f"{BASE_URL}/", timeout=0.5)
            if r.status_code == 200:
                return server, t
        except Exception:
            pass
        time.sleep(0.1)

    raise RuntimeError("Server did not start")


# ----------------------------
# TESTS
# ----------------------------
async def test_auth_info():
    print("\n" + "=" * 70)
    print("ℹ️  AUTH INFO")
    print("=" * 70)
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/auth/info")
        print("Status:", r.status_code)
        print(json.dumps(r.json(), indent=2))


async def test_api_key_with_agents():
    print("\n" + "=" * 70)
    print("🔑 TEST: API KEY (PolyAgent)")
    print("=" * 70)

    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)

    auth = StaticHeadersAuth({"X-API-Key": MCP_API_KEY})
    agent = PolyAgent(
        llm_provider=llm,
        mcp_servers=[BASE_URL],  # PolyAgent normalizes to /mcp
        auth_provider=auth,
        verbose=False,
    )

    q1 = "Add 42 and 58"
    q2 = "Multiply 3.14 by 2"

    print("Query:", q1)
    print("Result:", agent.run(q1))

    print("Query:", q2)
    print("Result:", agent.run(q2))


async def test_jwt_with_agents():
    print("\n" + "=" * 70)
    print("🎫 TEST: JWT (PolyAgent + JWTAuthProvider)")
    print("=" * 70)

    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)
    auth = JWTAuthProvider(
        base_url=BASE_URL,
        username="polymcp",
        password="polymcp123",
        login_path="/auth/login",
        refresh_path="/auth/refresh",
    )

    agent = PolyAgent(
        llm_provider=llm,
        mcp_servers=[BASE_URL],
        auth_provider=auth,
        verbose=False,
    )

    q = "Get system information"
    print("Query:", q)
    print("Result:", agent.run(q))

    print("⏳ Waiting for token to expire (to force refresh)...")
    await asyncio.sleep(JWT_EXPIRES_IN + 2)

    q2 = "Add 10 and 20"
    print("Query:", q2)
    print("Result:", agent.run(q2))


async def test_oauth2_with_agents():
    print("\n" + "=" * 70)
    print("🧾 TEST: OAuth2 (PolyAgent + OAuth2Provider client_credentials)")
    print("=" * 70)

    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)

    oauth = OAuth2Provider(
        token_url=OAUTH2_TOKEN_URL,
        client_id=OAUTH2_CLIENT_ID,
        client_secret=OAUTH2_CLIENT_SECRET,
        grant_type="client_credentials",
        scope="mcp.tools",
        use_basic_auth=True,  # test basic auth mode
    )

    agent = PolyAgent(
        llm_provider=llm,
        mcp_servers=[BASE_URL],
        auth_provider=oauth,
        verbose=False,
    )

    q = "Add 100 and 200"
    print("Query:", q)
    print("Result:", agent.run(q))

    print("⏳ Waiting for token to expire (to force refresh_token grant)...")
    await asyncio.sleep(OAUTH2_EXPIRES_IN + 2)

    q2 = "Multiply 12 by 3"
    print("Query:", q2)
    print("Result:", agent.run(q2))


async def test_unified_with_oauth2():
    print("\n" + "=" * 70)
    print("🚀 TEST: UnifiedPolyAgentWithAuth + OAuth2")
    print("=" * 70)

    llm = OllamaProvider(model="gpt-oss:120b-cloud", temperature=0)

    oauth = OAuth2Provider(
        token_url=OAUTH2_TOKEN_URL,
        client_id=OAUTH2_CLIENT_ID,
        client_secret=OAUTH2_CLIENT_SECRET,
        grant_type="client_credentials",
        scope="mcp.tools",
        use_basic_auth=False,  # test BODY mode (important)
        send_client_secret_in_body=True,  # ensure works in IdPs that require it
    )

    agent = UnifiedPolyAgentWithAuth(
        llm_provider=llm,
        mcp_servers=[f"{BASE_URL}/mcp"],  # Unified expects explicit /mcp normally
        auth_provider=oauth,
        verbose=False,
    )

    await agent.start()
    try:
        q = "First add 10 and 20. Then multiply the result by 3."
        print("Query:", q)
        res = await agent.run_async(q, max_steps=5)
        print("Result:", res)
    finally:
        await agent.stop()


async def test_invalid_auth():
    print("\n" + "=" * 70)
    print("🚫 TEST: Invalid Auth (should be rejected)")
    print("=" * 70)

    async with httpx.AsyncClient() as client:
        r1 = await client.get(f"{BASE_URL}/mcp/list_tools", headers={"X-API-Key": "wrong"})
        print("Wrong API Key status:", r1.status_code, "(expected 401)")

        r2 = await client.get(f"{BASE_URL}/mcp/list_tools", headers={"Authorization": "Bearer wrongtoken"})
        print("Wrong Bearer status:", r2.status_code, "(expected 401)")


async def main():
    print("\n" + "🔐 " * 20)
    print("POLYMCP ONE-FILE AUTH + SERVER TEST SUITE")
    print("🔐 " * 20)

    # Start server
    server, thread = start_server_in_thread()
    print(f"✅ Server running at {BASE_URL} (thread={thread.name})")

    # Run tests
    await test_auth_info()
    await test_api_key_with_agents()
    await test_jwt_with_agents()
    await test_oauth2_with_agents()
    await test_unified_with_oauth2()
    await test_invalid_auth()

    print("\n" + "=" * 70)
    print("✅ ALL TESTS COMPLETED")
    print("=" * 70)

    # uvicorn server will stop when process exits (daemon thread)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Interrupted by user")
