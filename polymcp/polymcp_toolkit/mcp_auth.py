"""
Production-Ready MCP Authentication
Complete implementation with all security features
"""

import os
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Literal, List
from collections import defaultdict
import time

from fastapi import HTTPException, Header, Depends, Request, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, validator
import redis
from sqlalchemy import Column, String, DateTime, Boolean, Integer, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security configuration from environment
SECRET_KEY = os.getenv("MCP_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("MCP_SECRET_KEY must be set in production!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("MCP_ACCESS_TOKEN_EXPIRE", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("MCP_REFRESH_TOKEN_EXPIRE", "7"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mcp_auth.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REQUIRE_HTTPS = os.getenv("MCP_REQUIRE_HTTPS", "true").lower() == "true"

# Database setup
Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Redis for token blacklist and rate limiting
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer scheme
bearer_scheme = HTTPBearer(auto_error=False)

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


# Database Models
class User(Base):
    __tablename__ = "users"
    
    username = Column(String, primary_key=True, index=True)
    hashed_password = Column(String)
    api_key = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    failed_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    username = Column(String, index=True)
    action = Column(String)
    tool_name = Column(String, nullable=True)
    ip_address = Column(String)
    user_agent = Column(String)
    status = Column(String)
    details = Column(String, nullable=True)


# Create tables
Base.metadata.create_all(bind=engine)


# Request/Response Models
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    
    @validator('username')
    def validate_username(cls, v):
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username must be alphanumeric (with _ or -)')
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


# Security Functions
def get_db():
    """Database dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_token(data: dict, expires_delta: timedelta, token_type: str = "access") -> str:
    """Create JWT token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": token_type,
        "jti": secrets.token_urlsafe(16)  # JWT ID for revocation
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_tokens(username: str) -> TokenResponse:
    """Create both access and refresh tokens"""
    access_token = create_token(
        {"sub": username},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "access"
    )
    refresh_token = create_token(
        {"sub": username},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "refresh"
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


def verify_token(token: str, expected_type: str = "access") -> dict:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Check token type
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        # Check if token is blacklisted
        jti = payload.get("jti")
        if jti and redis_client.get(f"blacklist:{jti}"):
            raise HTTPException(status_code=401, detail="Token has been revoked")
        
        return payload
        
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def revoke_token(token: str):
    """Add token to blacklist"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        exp = payload.get("exp")
        
        if jti and exp:
            # Store in Redis with expiration
            ttl = exp - int(datetime.utcnow().timestamp())
            if ttl > 0:
                redis_client.setex(f"blacklist:{jti}", ttl, "1")
                
    except JWTError:
        pass  # Token already invalid


def log_audit(
    db: Session,
    username: str,
    action: str,
    status: str,
    request: Request,
    tool_name: Optional[str] = None,
    details: Optional[str] = None
):
    """Log audit trail"""
    audit = AuditLog(
        username=username,
        action=action,
        tool_name=tool_name,
        ip_address=request.client.host,
        user_agent=request.headers.get("User-Agent", ""),
        status=status,
        details=details
    )
    db.add(audit)
    db.commit()


# Main Authenticator Class
class ProductionAuthenticator:
    """
    Production-ready authenticator with all security features
    """
    
    def __init__(self, enforce_https: bool = REQUIRE_HTTPS):
        self.enforce_https = enforce_https
        self._request_counts = defaultdict(int)
        self._last_cleanup = time.time()
    
    async def authenticate(
        self,
        request: Request,
        db: Session = Depends(get_db),
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
    ) -> tuple[str, User]:
        """
        Authenticate request using API Key or JWT.
        
        Returns:
            Tuple of (username, user_object)
        """
        
        # Enforce HTTPS in production
        if self.enforce_https and not request.url.scheme == "https":
            if request.headers.get("X-Forwarded-Proto") != "https":
                raise HTTPException(
                    status_code=400,
                    detail="HTTPS required for authentication"
                )
        
        # Try API Key authentication
        if x_api_key:
            user = db.query(User).filter(User.api_key == x_api_key).first()
            if user and user.is_active:
                # Update last login
                user.last_login = datetime.utcnow()
                db.commit()
                
                log_audit(db, user.username, "api_key_auth", "success", request)
                return user.username, user
            
            log_audit(db, "unknown", "api_key_auth", "failed", request)
            raise HTTPException(status_code=401, detail="Invalid API Key")
        
        # Try JWT authentication
        if bearer:
            try:
                payload = verify_token(bearer.credentials, "access")
                username = payload.get("sub")
                
                user = db.query(User).filter(User.username == username).first()
                if not user or not user.is_active:
                    raise HTTPException(status_code=401, detail="User not found or inactive")
                
                return username, user
                
            except HTTPException:
                raise
        
        # No authentication provided
        raise HTTPException(
            status_code=401,
            detail="Authentication required (API Key or Bearer token)",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    def login(
        self,
        request: LoginRequest,
        req: Request,
        db: Session
    ) -> TokenResponse:
        """
        Login with username/password to get tokens.
        Includes brute force protection.
        """
        user = db.query(User).filter(User.username == request.username).first()
        
        # Check if user exists
        if not user:
            # Log failed attempt (don't reveal user doesn't exist)
            log_audit(db, request.username, "login", "failed", req, 
                     details="User not found")
            time.sleep(1)  # Slow down brute force
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Check if account is locked
        if user.locked_until and user.locked_until > datetime.utcnow():
            remaining = (user.locked_until - datetime.utcnow()).seconds
            log_audit(db, user.username, "login", "locked", req)
            raise HTTPException(
                status_code=429,
                detail=f"Account locked. Try again in {remaining} seconds"
            )
        
        # Verify password
        if not verify_password(request.password, user.hashed_password):
            user.failed_attempts += 1
            
            # Lock account after 5 failed attempts
            if user.failed_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                db.commit()
                log_audit(db, user.username, "login", "locked", req, 
                         details="Too many failed attempts")
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed attempts. Account locked for 15 minutes"
                )
            
            db.commit()
            log_audit(db, user.username, "login", "failed", req)
            time.sleep(1)  # Slow down brute force
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Successful login
        user.failed_attempts = 0
        user.locked_until = None
        user.last_login = datetime.utcnow()
        db.commit()
        
        tokens = create_tokens(user.username)
        log_audit(db, user.username, "login", "success", req)
        
        return tokens
    
    def refresh(
        self,
        request: RefreshRequest,
        req: Request,
        db: Session
    ) -> TokenResponse:
        """Refresh access token using refresh token"""
        try:
            payload = verify_token(request.refresh_token, "refresh")
            username = payload.get("sub")
            
            user = db.query(User).filter(User.username == username).first()
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="Invalid user")
            
            # Revoke old refresh token
            revoke_token(request.refresh_token)
            
            # Create new tokens
            tokens = create_tokens(username)
            log_audit(db, username, "token_refresh", "success", req)
            
            return tokens
            
        except HTTPException as e:
            log_audit(db, "unknown", "token_refresh", "failed", req)
            raise e
    
    def logout(
        self,
        request: Request,
        token: str,
        db: Session
    ):
        """Logout and revoke token"""
        try:
            payload = verify_token(token, "access")
            username = payload.get("sub")
            
            # Revoke token
            revoke_token(token)
            
            log_audit(db, username, "logout", "success", request)
            return {"message": "Logged out successfully"}
            
        except HTTPException:
            return {"message": "Token already invalid"}


def setup_auth_middleware(app, allowed_origins: List[str] = None):
    """Setup security middleware for production"""
    
    # CORS
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    # Trusted Host (prevent host header injection)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]  # Configure your domains
    )
    
    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    return app

def add_production_auth_to_mcp(
    base_app,
    authenticator: ProductionAuthenticator,
    allowed_origins: List[str] = ["*"]
):
    """
    Helper to add production authentication to MCP server.
    Wraps the base app with auth endpoints and middleware.
    """
    from fastapi import FastAPI, Depends, Request, HTTPException
    
    app = FastAPI(
        title="Authenticated MCP Server",
        description="MCP Server with Production Authentication",
        version="1.0.0"
    )
    
    # Setup middleware
    app = setup_auth_middleware(app, allowed_origins)
    
    # Auth endpoints
    @app.post("/auth/login")
    async def login(request: LoginRequest, req: Request, db = Depends(get_db)):
        return authenticator.login(request, req, db)
    
    @app.post("/auth/refresh")
    async def refresh_token(request: RefreshRequest, req: Request, db = Depends(get_db)):
        return authenticator.refresh(request, req, db)
    
    @app.post("/auth/logout")
    async def logout(req: Request, auth_data = Depends(authenticator.authenticate)):
        username, user = auth_data
        auth_header = req.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            db = next(get_db())
            return authenticator.logout(req, token, db)
        return {"message": "No token to revoke"}
    
    # Get original endpoints
    original_list_tools = None
    original_invoke_tool = None
    for route in base_app.router.routes:
        if hasattr(route, 'path'):
            if route.path == "/mcp/list_tools":
                original_list_tools = route.endpoint
            elif route.path == "/mcp/invoke/{tool_name}":
                original_invoke_tool = route.endpoint
    
    # Authenticated endpoints
    @app.get("/mcp/list_tools")
    async def list_tools_auth(req: Request, auth_data = Depends(authenticator.authenticate)):
        username, user = auth_data
        result = await original_list_tools() if original_list_tools else {"tools": []}
        result["authenticated_user"] = username
        return result
    
    @app.post("/mcp/invoke/{tool_name}")
    async def invoke_tool_auth(
        tool_name: str,
        req: Request,
        payload: dict = None,
        auth_data = Depends(authenticator.authenticate)
    ):
        username, user = auth_data
        if not original_invoke_tool:
            raise HTTPException(status_code=404, detail="Tool endpoint not found")
        result = await original_invoke_tool(tool_name, payload)
        result["authenticated_user"] = username
        return result
    
    # Info endpoints
    @app.get("/")
    async def root():
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
        return {
            "auth_enabled": True,
            "methods": ["api_key", "jwt"],
            "endpoints": {"login": "/auth/login", "refresh": "/auth/refresh", "logout": "/auth/logout"}
        }
    
    # Mount other routes
    for route in base_app.router.routes:
        if hasattr(route, 'path') and route.path not in ["/mcp/list_tools", "/mcp/invoke/{tool_name}"]:
            app.router.routes.append(route)
    
    return app

# CLI for user management
def create_user(username: str, password: str, is_admin: bool = False):
    """Create a new user (CLI helper)"""
    db = SessionLocal()
    try:
        # Check if user exists
        if db.query(User).filter(User.username == username).first():
            print(f"User {username} already exists")
            return
        
        # Create user
        user = User(
            username=username,
            hashed_password=hash_password(password),
            api_key=f"sk-{secrets.token_urlsafe(32)}",
            is_admin=is_admin,
            is_active=True
        )
        db.add(user)
        db.commit()
        
        print(f"User created successfully!")
        print(f"Username: {username}")
        print(f"API Key: {user.api_key}")
        
    finally:
        db.close()


if __name__ == "__main__":
    # CLI for creating users
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "create_user":
            username = input("Username: ")
            password = input("Password: ")
            is_admin = input("Admin? (y/n): ").lower() == 'y'

            create_user(username, password, is_admin)
