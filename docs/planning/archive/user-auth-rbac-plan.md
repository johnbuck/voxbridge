# User Authentication & RBAC Implementation Plan

**Date**: December 5, 2025
**Branch**: `feature/user-auth`
**Status**: ✅ Complete
**Priority**: High

---

## Executive Summary

Implement user authentication with JWT tokens and simple Admin/User RBAC for VoxBridge. Users will have isolated memories (replacing the current `web_user_default` singleton).

### Requirements (User-Selected)
- **Auth Method**: Username/Password + JWT tokens
- **RBAC**: Simple two-role system (Admin, User)
- **Memory Isolation**: Per-user (each user has private facts)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                         │
├─────────────────────────────────────────────────────────────────┤
│  AuthContext → JWT Token Storage → Protected Routes             │
│  Login Page │ Register Page │ User Settings                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (Authorization: Bearer <JWT>)
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                            │
├─────────────────────────────────────────────────────────────────┤
│  JWT Middleware → Route Protection → RBAC Checks                │
│                                                                 │
│  /api/auth/register   (public)                                  │
│  /api/auth/login      (public)                                  │
│  /api/auth/refresh    (authenticated)                           │
│  /api/auth/me         (authenticated)                           │
│                                                                 │
│  /api/agents/*        (admin: write, user: read)                │
│  /api/memory/*        (user: own data only)                     │
│  /api/settings/*      (admin only)                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       PostgreSQL                                │
├─────────────────────────────────────────────────────────────────┤
│  users (id, email, username, password_hash, role, created_at)   │
│  user_facts (user_id FK → users.id)                             │
│  sessions (user_id references users.user_id)                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Database Schema Updates

### 1.1 Update User Model

**File**: `src/database/models.py`

```python
from enum import Enum as PyEnum

class UserRole(str, PyEnum):
    ADMIN = "admin"
    USER = "user"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Keep legacy user_id for backward compatibility (Discord integration)
    user_id = Column(String(255), unique=True, nullable=True, index=True)
    display_name = Column(String(255), nullable=True)
    allow_agent_specific_memory = Column(Boolean, default=True)

    # Relationships
    facts = relationship("UserFact", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
```

### 1.2 Migration Script

**File**: `alembic/versions/20251205_0001_028_add_auth_fields.py`

```python
def upgrade():
    # Add new columns to users table
    op.add_column('users', sa.Column('email', sa.String(255), unique=True, nullable=True))
    op.add_column('users', sa.Column('username', sa.String(100), unique=True, nullable=True))
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('role', sa.Enum('admin', 'user', name='userrole'), default='user'))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), default=True))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))

    # Create indexes
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_username', 'users', ['username'])
```

---

## Phase 2: Authentication Service

### 2.1 Dependencies

**Add to `requirements-bot.txt`**:
```
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
python-multipart==0.0.6
```

### 2.2 Auth Configuration

**File**: `src/config/auth.py`

```python
from pydantic_settings import BaseSettings

class AuthSettings(BaseSettings):
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    class Config:
        env_prefix = "AUTH_"
```

### 2.3 Auth Service

**File**: `src/services/auth_service.py`

```python
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta

class AuthService:
    def __init__(self, settings: AuthSettings):
        self.settings = settings
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        return self.pwd_context.hash(password)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return self.pwd_context.verify(plain, hashed)

    def create_access_token(self, user_id: str, role: str) -> str:
        expire = datetime.utcnow() + timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {"sub": user_id, "role": role, "exp": expire, "type": "access"}
        return jwt.encode(payload, self.settings.SECRET_KEY, algorithm=self.settings.ALGORITHM)

    def create_refresh_token(self, user_id: str) -> str:
        expire = datetime.utcnow() + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {"sub": user_id, "exp": expire, "type": "refresh"}
        return jwt.encode(payload, self.settings.SECRET_KEY, algorithm=self.settings.ALGORITHM)

    def decode_token(self, token: str) -> dict | None:
        try:
            return jwt.decode(token, self.settings.SECRET_KEY, algorithms=[self.settings.ALGORITHM])
        except JWTError:
            return None
```

---

## Phase 3: Auth Routes

### 3.1 Auth Endpoints

**File**: `src/routes/auth_routes.py`

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/auth/register` | POST | Public | Create new user account |
| `/api/auth/login` | POST | Public | Login, returns JWT tokens |
| `/api/auth/refresh` | POST | Refresh Token | Get new access token |
| `/api/auth/me` | GET | Access Token | Get current user info |
| `/api/auth/logout` | POST | Access Token | Invalidate refresh token |

### 3.2 Request/Response Models

```python
class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8)

class LoginRequest(BaseModel):
    username: str  # Can be email or username
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str
    created_at: datetime
```

---

## Phase 4: JWT Middleware & Dependencies

### 4.1 FastAPI Dependencies

**File**: `src/dependencies/auth.py`

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Dependency to get current authenticated user."""
    token = credentials.credentials
    payload = auth_service.decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await db.execute(select(User).where(User.id == payload["sub"]))
    user = user.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user

async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin role."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# Optional auth - returns None if no token provided
async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> User | None:
    if not credentials:
        return None
    # ... same validation logic
```

### 4.2 Route Protection

```python
# Public endpoint
@router.get("/api/agents")
async def list_agents():
    ...

# User-only endpoint
@router.get("/api/memory/facts")
async def list_facts(user: User = Depends(get_current_user)):
    # user.id is automatically the filter
    ...

# Admin-only endpoint
@router.post("/api/agents")
async def create_agent(user: User = Depends(require_admin)):
    ...
```

---

## Phase 5: Memory Isolation

### 5.1 Update Memory Service

Replace all occurrences of `web_user_default` with actual `user.id`:

**Files to update**:
- `src/services/memory_service.py`
- `src/routes/memory_routes.py`
- `src/plugins/discord_plugin.py`
- `src/discord_bot.py`
- `src/voice/webrtc_handler.py`

### 5.2 Migration Strategy

**Option A: Clean Slate** (Recommended for beta)
- Drop all facts for `web_user_default`
- Users start fresh with their own memories

**Option B: Migration Script**
- Create admin user, assign all existing facts to admin
- Other users start fresh

---

## Phase 6: Frontend Authentication

### 6.1 Auth Context

**File**: `frontend/src/contexts/AuthContext.tsx`

```typescript
interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  logout: () => void;
}
```

### 6.2 New Pages

- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/pages/RegisterPage.tsx`
- `frontend/src/pages/ProfilePage.tsx` (optional)

### 6.3 Protected Routes

```typescript
// App.tsx
<Routes>
  <Route path="/login" element={<LoginPage />} />
  <Route path="/register" element={<RegisterPage />} />

  {/* Protected routes */}
  <Route element={<ProtectedRoute />}>
    <Route path="/" element={<VoxbridgePage />} />
    <Route path="/memory" element={<MemoryPage />} />
    <Route path="/settings" element={<SettingsPage />} />
  </Route>

  {/* Admin-only routes */}
  <Route element={<AdminRoute />}>
    <Route path="/agents" element={<AgentsPage />} />
  </Route>
</Routes>
```

### 6.4 Token Storage

- **Access Token**: Memory (React state) - short-lived
- **Refresh Token**: httpOnly cookie (secure) - long-lived

---

## Phase 7: First Admin User

### 7.1 Seed Script Update

**File**: `src/database/seed.py`

```python
async def create_admin_user():
    """Create initial admin user if none exists."""
    admin = await db.execute(select(User).where(User.role == UserRole.ADMIN))
    if not admin.scalar_one_or_none():
        admin_password = os.getenv("ADMIN_PASSWORD", "changeme123")
        admin_user = User(
            email="admin@voxbridge.local",
            username="admin",
            password_hash=auth_service.hash_password(admin_password),
            role=UserRole.ADMIN,
            display_name="Administrator"
        )
        db.add(admin_user)
        await db.commit()
        logger.info("Created initial admin user")
```

---

## Implementation Order

| Phase | Description | Effort | Dependencies |
|-------|-------------|--------|--------------|
| 1 | Database schema updates | 1 hour | None |
| 2 | Auth service (password hashing, JWT) | 2 hours | Phase 1 |
| 3 | Auth routes (register, login, refresh) | 2 hours | Phase 2 |
| 4 | JWT middleware & dependencies | 1 hour | Phase 3 |
| 5 | Memory isolation (replace web_user_default) | 2 hours | Phase 4 |
| 6 | Frontend auth (context, pages, protected routes) | 4 hours | Phase 4 |
| 7 | Admin seeding & testing | 1 hour | Phase 6 |

**Total Estimated Effort**: ~13 hours

---

## Environment Variables

```bash
# Auth Configuration
AUTH_SECRET_KEY=your-256-bit-secret-key-here
AUTH_ALGORITHM=HS256
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7

# Initial Admin (used by seed script)
ADMIN_PASSWORD=secure-admin-password
```

---

## Security Considerations

1. **Password Requirements**: Minimum 8 characters (can add complexity rules)
2. **Rate Limiting**: Add rate limiting to login endpoint (5 attempts/minute)
3. **Token Security**: Access tokens short-lived (30 min), refresh in httpOnly cookie
4. **HTTPS**: Required in production for token transmission
5. **CORS**: Configure allowed origins for API

---

## Testing Plan

1. **Unit Tests**: Auth service (hashing, JWT encode/decode)
2. **Integration Tests**: Auth routes (register, login, refresh flow)
3. **E2E Tests**: Full auth flow in frontend
4. **Security Tests**: Invalid tokens, expired tokens, role enforcement

---

## Files to Create/Modify

### New Files
- `src/config/auth.py`
- `src/services/auth_service.py`
- `src/routes/auth_routes.py`
- `src/dependencies/auth.py`
- `alembic/versions/20251205_0001_028_add_auth_fields.py`
- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/pages/RegisterPage.tsx`
- `frontend/src/components/ProtectedRoute.tsx`

### Modified Files
- `src/database/models.py` (User model updates)
- `src/api/server.py` (register auth routes)
- `src/services/memory_service.py` (user isolation)
- `src/routes/memory_routes.py` (add auth dependencies)
- `src/routes/agent_routes.py` (admin-only write)
- `src/plugins/discord_plugin.py` (real user IDs)
- `src/database/seed.py` (admin user creation)
- `frontend/src/App.tsx` (protected routes)
- `frontend/src/services/api.ts` (add auth header)
- `requirements-bot.txt` (add passlib, python-jose)
