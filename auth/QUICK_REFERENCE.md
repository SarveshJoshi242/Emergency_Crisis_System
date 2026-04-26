# JWT Auth - Quick Reference Card

Print this or bookmark it for quick access while coding.

---

## 🔐 Setup (One-Time)

```bash
# 1. Generate secret
python -c "import secrets; print(secrets.token_hex(64))"

# 2. Add to .env
JWT_SECRET=<paste_generated_secret>

# 3. Create DB indexes
# See AUTH_SYSTEM_OVERVIEW.md → Database Collections

# 4. Register auth router
# In main.py: app.include_router(auth_router)

# 5. Create first account via API
curl -X POST http://localhost:8000/auth/staff/register \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Admin",
    "email":"admin@hotel.local",
    "password":"Password123!",
    "permissions":["view_alerts","evacuate"]
  }'
```

---

## 📝 Common Code Patterns

### Protect Staff-Only Route
```python
from auth.dependencies import require_staff

@router.post("/action")
async def action(staff = Depends(require_staff)):
    staff_id = staff["sub"]
    return {"done": True}
```

### Protect Guest-Only Route
```python
from auth.dependencies import require_guest

@router.get("/instructions")
async def get_instructions(guest = Depends(require_guest)):
    room = guest["room_number"]
    return {"room": room}
```

### Check Specific Permission
```python
from auth.dependencies import require_permission

@router.post("/evacuate")
async def evacuate(user = Depends(require_permission("evacuate"))):
    return {"status": "evacuating"}
```

### Allow Both Roles
```python
from auth.dependencies import require_staff_or_guest

@router.get("/alerts")
async def alerts(user = Depends(require_staff_or_guest)):
    return {"alerts": [...]}
```

---

## 🔑 API Endpoints

| Method | Endpoint | Auth? | Purpose |
|--------|----------|-------|---------|
| POST | `/auth/staff/register` | ✗ | Register staff (admin use) |
| POST | `/auth/staff/login` | ✗ | Login with email+password |
| POST | `/auth/guest/checkin` | ✗ | Guest check-in |
| POST | `/auth/refresh` | ✗ | Get new token pair |
| POST | `/auth/logout` | ✓ | Revoke refresh token |
| GET | `/auth/me` | ✓ | Get current user |

---

## 📊 JWT Token Payload

### What's Inside (Decoded)
```json
{
  "sub": "507f1f77bcf86cd799439011",    // user_id
  "role": "staff",                      // staff or guest
  "email": "alice@hotel.local",         // staff only
  "name": "Manager Alice",              // staff only
  "permissions": ["evacuate"],          // staff only
  "room_number": "1205",                // guest only
  "iat": 1698789600,                    // issued-at
  "exp": 1698790800,                    // expiry
  "jti": "unique-id",                   // token id
  "type": "access"                      // access or refresh
}
```

### How to Use It
```python
# In your route handler:
staff_id = user["sub"]
has_evacuate = "evacuate" in user.get("permissions", [])
guest_room = user.get("room_number")
```

---

## 🧪 Quick Test Commands

### Login
```bash
curl -X POST http://localhost:8000/auth/staff/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@hotel.local","password":"password"}'
```

### Use Token
```bash
TOKEN=<from_login_response>
curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

### Refresh
```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

### Logout
```bash
curl -X POST http://localhost:8000/auth/logout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

---

## ⏱️ Token Lifetimes

| Token | Lifetime | Storage | Revocable |
|-------|----------|---------|-----------|
| Staff Access | 20 minutes | JWT only | No (stateless) |
| Guest Access | 10 minutes | JWT only | No (stateless) |
| Refresh | 24 hours | MongoDB + JWT | Yes (delete from DB) |

---

## 🚫 Status Codes

| Code | Meaning | When |
|------|---------|------|
| 200 | Success | Login, refresh, logout OK |
| 201 | Created | Staff registration OK |
| 401 | Unauthorized | Missing/invalid/expired token |
| 403 | Forbidden | Valid token, but wrong role/permission |
| 404 | Not Found | Token/account not found |
| 409 | Conflict | Email already registered |
| 422 | Invalid | Bad request body |
| 429 | Rate Limited | Too many attempts |

---

## 🐛 Troubleshooting

| Error | Fix |
|-------|-----|
| `401: Invalid credentials` | Email or password wrong |
| `401: Authorization header missing` | Add `Authorization: Bearer <token>` |
| `401: Access token has expired` | Refresh token or login again |
| `403: Staff access required` | Use staff token, not guest |
| `429: Too many attempts` | Wait 60 seconds |
| `RuntimeError: JWT_SECRET not set` | Add JWT_SECRET to .env |

---

## 📚 Files Quick Guide

| File | Contains |
|------|----------|
| `README.md` | Overview & status |
| `QUICK_START.md` | 5-minute setup |
| `AUTH_SYSTEM_OVERVIEW.md` | Complete reference (bookmark this!) |
| `INTEGRATION_EXAMPLES.md` | Copy-paste code patterns |
| `TESTING_GUIDE.md` | Full test suite |
| `DEPLOYMENT_BEST_PRACTICES.md` | Production checklist |
| `client_examples.py` | Python client library |

---

## 🔄 Typical User Journey

```
┌─────────────┐
│   REGISTER  │  POST /auth/staff/register
└──────┬──────┘
       ↓
┌─────────────┐
│   LOGIN     │  POST /auth/staff/login → access_token
└──────┬──────┘
       ↓
┌─────────────┐
│ USE TOKEN   │  GET /auth/me with Bearer token
└──────┬──────┘
       ↓
    20 min
       ↓
┌─────────────┐
│   REFRESH   │  POST /auth/refresh → new tokens
└──────┬──────┘
       ↓
┌─────────────┐
│   LOGOUT    │  POST /auth/logout (optional)
└─────────────┘
```

---

## 💡 Pro Tips

1. **Never hardcode JWT_SECRET** — use environment variables
2. **Always use HTTPS in production** — tokens in URLs/headers need protection
3. **Keep tokens short-lived** — 20 min is a good default
4. **Use refresh tokens for long sessions** — don't extend access tokens
5. **Check permissions early** — fail fast on authorization
6. **Log auth failures** — track suspicious activity
7. **Test rate limiting** — make sure it works
8. **Rotate secrets regularly** — minimum once per year

---

## 🎯 Integration Checklist

- [ ] JWT_SECRET generated and in .env
- [ ] MongoDB indexes created
- [ ] Auth router mounted in main.py
- [ ] First staff account registered
- [ ] Test login endpoint works
- [ ] Test protected route works
- [ ] Test refresh endpoint works
- [ ] Test logout works
- [ ] HTTPS configured
- [ ] CORS configured
- [ ] Monitoring/logging enabled

---

## 🆘 Emergency Commands

```bash
# Reset rate limiter (clear memory)
# → Restart server (in-memory only)

# Test auth system
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer test"

# Check if server is running
curl http://localhost:8000/health

# View auth logs
tail -f logs/app.log | grep -i auth
```

---

**Keep this handy!** → Bookmark or print for quick reference while coding.

---

**Last Updated**: April 25, 2026
