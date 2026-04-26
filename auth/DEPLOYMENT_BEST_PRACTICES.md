# JWT Authentication - Deployment & Best Practices

## Pre-Production Checklist

### Security

- [ ] **JWT Secret**: Generated using `secrets.token_hex(64)` (256 bits entropy)
- [ ] **Secret Storage**: Stored in secrets manager (AWS Secrets, HashiCorp Vault, Azure Key Vault), NOT in git
- [ ] **.env file**: Added to `.gitignore`, never committed
- [ ] **HTTPS**: All endpoints require TLS/SSL
- [ ] **CORS**: Properly configured for your frontend domains only
- [ ] **Password Requirements**: Enforce during staff registration (optional but recommended)
- [ ] **Rate Limiting**: For production, upgrade from in-memory to Redis
- [ ] **Logging**: Auth failures logged but no sensitive data (no passwords, no full tokens)
- [ ] **Database**: All relevant indexes created
- [ ] **Refresh Token Cleanup**: Job scheduled to delete expired tokens weekly

### Configuration

- [ ] **Environment Variables**: All set correctly for production environment
- [ ] **Token Expiry Times**: Reviewed and appropriate for use case
  - Staff access: 15-30 min ✓
  - Guest access: 5-15 min ✓
  - Refresh: 24-72 hours ✓
- [ ] **Database Connection**: Uses SSL/TLS, connection pooling enabled
- [ ] **Logging Level**: Set to WARNING or ERROR in production
- [ ] **Error Messages**: Generic, no stack traces exposed to clients

### Operational

- [ ] **Monitoring**: Auth endpoint metrics tracked (success/failure rates, latencies)
- [ ] **Alerting**: Alert on unusual auth failure rates (possible brute force)
- [ ] **Backup**: Database refresh_tokens backed up
- [ ] **Load Testing**: Verified system handles expected concurrent users
- [ ] **Deployment**: Tested JWT rotation works across multiple backend instances
- [ ] **Admin Procedures**: Documented how to reset staff passwords, revoke tokens

---

## Deployment Steps

### 1. Generate Production JWT Secret

```bash
# Generate once, store securely
python -c "import secrets; print(secrets.token_hex(64))"

# Example output (store this securely):
# a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6...
```

### 2. Set Environment Variables

**Option A: Environment File (Kubernetes, Docker)**
```yaml
env:
  - name: JWT_SECRET
    valueFrom:
      secretKeyRef:
        name: app-secrets
        key: jwt-secret
  - name: JWT_ALGORITHM
    value: "HS256"
  - name: ACCESS_TOKEN_EXPIRE_MINUTES_STAFF
    value: "20"
  - name: ACCESS_TOKEN_EXPIRE_MINUTES_GUEST
    value: "10"
  - name: REFRESH_TOKEN_EXPIRE_HOURS
    value: "24"
  - name: MONGODB_URI
    valueFrom:
      secretKeyRef:
        name: app-secrets
        key: mongodb-uri
```

**Option B: .env File (Single Server)**
```bash
# Ensure .env is:
# - Owned by app user only (chmod 600)
# - Excluded from git (in .gitignore)
# - Not in public cloud storage
```

### 3. Create MongoDB Indexes

```javascript
// Run once at deployment:

// staff_accounts
db.staff_accounts.createIndex({ email: 1 }, { unique: true })
db.staff_accounts.createIndex({ is_active: 1 })

// refresh_tokens
db.refresh_tokens.createIndex({ token: 1 }, { unique: true })
db.refresh_tokens.createIndex({ user_id: 1 })
db.refresh_tokens.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0 })

// guests
db.guests.createIndex({ booking_id: 1 }, { unique: true })
db.guests.createIndex({ room_number: 1 })
```

### 4. Seed Initial Admin Account

```bash
# Via API during deployment:
curl -X POST https://api.yourdomain.com/auth/staff/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Admin",
    "email": "admin@yourdomain.com",
    "password": "GeneratedSecurePassword123!",
    "permissions": ["view_alerts", "evacuate", "analytics"]
  }'

# Store returned admin ID for reference
```

### 5. Update CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.yourdomain.com",      # Production frontend
        "https://admin.yourdomain.com",     # Admin panel
        # DO NOT use ["*"] in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 6. Configure Rate Limiting for Production

**Replace in-memory limiter with Redis:**

```bash
# Install:
pip install slowapi redis
```

```python
# auth/rate_limiter_redis.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://:password@redis-host:6379/0",
    strategy="moving-window",
)

# Usage in routes:
@router.post("/staff/login")
@limiter.limit("5/minute")
async def staff_login(request: Request, ...):
    ...
```

### 7. Setup Refresh Token Cleanup Job

```python
# In background tasks or cron:
async def cleanup_expired_tokens():
    """Delete expired refresh tokens (run weekly)."""
    db = get_db()
    now = datetime.now(tz=timezone.utc)
    
    result = await db["refresh_tokens"].delete_many({
        "expires_at": {"$lt": now}
    })
    
    logger.info(f"Cleaned up {result.deleted_count} expired tokens")

# Schedule with APScheduler or Celery:
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_expired_tokens, 'cron', day_of_week='sun', hour=2)
scheduler.start()
```

### 8. Enable HTTPS

```python
# In production, FastAPI is behind reverse proxy (nginx, AWS ALB)
# Ensure:
# - Certificate is valid and from trusted CA
# - HSTS header is set
# - TLS 1.2+ only

# Example nginx config:
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    add_header Strict-Transport-Security "max-age=31536000" always;
}
```

### 9. Setup Monitoring & Alerting

```python
# Track these metrics:
# - Login success rate (target: >95%)
# - Login failure rate (alert if >10 failures/min from single IP)
# - Token refresh rate (should be smooth, no spikes)
# - Auth endpoint latency (should be <100ms)
# - Database query times for auth

# Example Prometheus metrics:
from prometheus_client import Counter, Histogram

auth_login_attempts = Counter(
    'auth_login_attempts_total',
    'Total login attempts',
    ['status']  # success, failure_wrong_creds, rate_limited
)

auth_latency = Histogram(
    'auth_latency_seconds',
    'Auth endpoint latency',
    ['endpoint']
)
```

### 10. Test Full Deployment

```bash
# 1. Health check
curl https://api.yourdomain.com/health

# 2. Staff login
curl -X POST https://api.yourdomain.com/auth/staff/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@yourdomain.com","password":"..."}'

# 3. Protected endpoint
TOKEN=<from_login_response>
curl -X GET https://api.yourdomain.com/auth/me \
  -H "Authorization: Bearer $TOKEN"

# 4. Token refresh
curl -X POST https://api.yourdomain.com/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"..."}'

# 5. Logout
curl -X POST https://api.yourdomain.com/auth/logout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"..."}'
```

---

## Best Practices

### Token Expiry Strategy

**Short-lived Access Tokens** = Better Security
- Limits damage if token leaked
- Requires more refresh requests (minor performance cost)

**Long-lived Refresh Tokens** = Better UX
- User stays logged in longer
- Mitigated by server-side storage + revocation

**Recommended:**
- Staff: 20 min access, 24 hr refresh
- Guests: 10 min access, 8 hr refresh

---

### Password Security

**For Staff Registration:**

```python
import re

def validate_password_strength(password: str) -> bool:
    """Enforce strong password requirements."""
    if len(password) < 12:
        return False
    if not re.search(r"[A-Z]", password):  # uppercase
        return False
    if not re.search(r"[a-z]", password):  # lowercase
        return False
    if not re.search(r"\d", password):     # digit
        return False
    if not re.search(r"[!@#$%^&*]", password):  # special char
        return False
    return True
```

---

### Logging & Monitoring

**DO Log:**
- Auth endpoint latencies
- Failed login attempts (without password)
- Token refresh success/failure rates
- Logout events
- Rate limit violations

**DO NOT Log:**
- Passwords (ever)
- Full tokens
- Sensitive user data beyond user_id
- Exact reasons for auth failures (on server logs only)

```python
logger.info("Staff login successful | user_id=%s ip=%s", user_id, client_ip)
logger.warning("Failed login attempt | ip=%s email_domain=%s", ip, email.split("@")[1])
logger.error("Rate limit exceeded | key=%s requests=%d", key, requests)
```

---

### Multi-Region Deployments

**Challenge:** Different servers have different JWT_SECRETs

**Solution:**

```python
# Use shared JWT_SECRET across all regions
# Store in centralized secrets manager (AWS Secrets Manager, Vault)

import boto3

def get_jwt_secret():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId='app/jwt-secret')
    return response['SecretString']
```

---

### Handling Token Revocation

Sometimes you need to revoke a token before expiry:

```python
# Example: User password changed, revoke all existing refresh tokens

async def revoke_all_user_tokens(user_id: str, db):
    """Invalidate all refresh tokens for a user."""
    await db["refresh_tokens"].delete_many({"user_id": user_id})
    logger.info("Revoked all tokens for user | user_id=%s", user_id)

# In password change endpoint:
@router.post("/auth/staff/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user = Depends(require_staff),
    db = Depends(get_db),
):
    # ... verify old password, hash new one ...
    await db["staff_accounts"].update_one(
        {"_id": ObjectId(current_user["sub"])},
        {"$set": {"password_hash": hash_password(body.new_password)}}
    )
    
    # Revoke all existing sessions (user must re-login on all devices)
    await revoke_all_user_tokens(current_user["sub"], db)
    
    return {"message": "Password changed. Please log in again on all devices."}
```

---

### Session Management (Advanced)

Track active sessions:

```python
# In refresh_tokens collection:
{
  "_id": ObjectId,
  "token": String,
  "user_id": ObjectId,
  "device_id": String,       # ← Track device
  "ip_address": String,       # ← Track IP
  "user_agent": String,       # ← Track browser
  "created_at": DateTime,
  "last_used_at": DateTime,
  "expires_at": DateTime,
}

# Endpoint to list active sessions
@router.get("/auth/sessions")
async def list_sessions(current_user = Depends(get_current_user), db = Depends(get_db)):
    sessions = await db["refresh_tokens"].find(
        {"user_id": current_user["sub"]}
    ).to_list(100)
    
    return {
        "sessions": [
            {
                "device_id": s.get("device_id"),
                "ip_address": s["ip_address"],
                "user_agent": s["user_agent"],
                "last_used": s.get("last_used_at"),
            }
            for s in sessions
        ]
    }

# Endpoint to revoke a specific session
@router.post("/auth/sessions/{session_id}/revoke")
async def revoke_session(
    session_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db),
):
    result = await db["refresh_tokens"].delete_one({
        "_id": ObjectId(session_id),
        "user_id": current_user["sub"],
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"message": "Session revoked"}
```

---

### Performance Optimization

**Caching JWT Validation (optional, for very high traffic):**

```python
from functools import lru_cache
import json

@lru_cache(maxsize=1000)
def cache_token_validation(token: str) -> dict:
    """Cache decoded tokens for 1 second."""
    try:
        return decode_access_token(token)
    except:
        return None

# Use in dependencies:
async def get_current_user_cached(credentials):
    cached = cache_token_validation(credentials.credentials)
    if cached:
        return cached
    else:
        return decode_access_token(credentials.credentials)
```

**Note:** Caching adds complexity; only use if you have concrete performance metrics showing need.

---

### Upgrading to RS256 (Optional)

For public-key verification (third-party services validating your tokens):

```python
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Generate keys once:
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

public_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

# Store private_pem in secrets manager, expose public_pem at /.well-known/jwks.json

# Usage:
token = jwt.encode(payload, private_pem, algorithm="RS256")
payload = jwt.decode(token, public_pem, algorithms=["RS256"])
```

---

### Troubleshooting Production Issues

| Issue | Diagnosis | Solution |
|-------|-----------|----------|
| Token validation slow | Check logging, may be DB query | Ensure indexes created |
| Rate limiting not working | Check Redis connection | Verify Redis is running |
| Expired tokens not rejected | Check JWT_ALGORITHM match | Ensure same secret all servers |
| Session leaks across regions | Different secrets per region | Use centralized secret manager |
| Password hashing CPU spike | Bcrypt cost factor too high | Check config, default 12 is fine |

---

## Compliance & Auditing

### GDPR / Privacy

- [ ] User consent for token storage documented
- [ ] Data retention policy: refresh tokens deleted after expiry
- [ ] User right to access: implement `/auth/sessions` endpoint
- [ ] User right to be forgotten: implement `/auth/deactivate` endpoint

### Security Auditing

- [ ] Auth logs retained for 90 days minimum
- [ ] Suspicious activity flagged (10+ failed logins, etc.)
- [ ] Admin audit trail: who created/modified staff accounts
- [ ] Regular penetration testing of auth endpoints

---

**Last Updated**: April 25, 2026  
**Version**: 1.0
