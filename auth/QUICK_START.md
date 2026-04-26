# JWT Auth - Quick Start Guide

## ⚡ 5-Minute Setup

### Step 1: Generate JWT Secret

```bash
python -c "import secrets; print(secrets.token_hex(64))"
```

Copy the output.

### Step 2: Add to `.env`

```bash
# Create or update .env in project root
JWT_SECRET=paste_the_generated_secret_here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES_STAFF=20
ACCESS_TOKEN_EXPIRE_MINUTES_GUEST=10
REFRESH_TOKEN_EXPIRE_HOURS=24
```

### Step 3: Create MongoDB Indexes

```javascript
// In MongoDB Atlas or local MongoDB shell:

// For staff_accounts
db.staff_accounts.createIndex({ email: 1 }, { unique: true })
db.staff_accounts.createIndex({ is_active: 1 })

// For refresh_tokens
db.refresh_tokens.createIndex({ token: 1 }, { unique: true })
db.refresh_tokens.createIndex({ user_id: 1 })
db.refresh_tokens.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0 })

// For guests
db.guests.createIndex({ booking_id: 1 }, { unique: true })
db.guests.createIndex({ room_number: 1 })
```

### Step 4: Register Auth Router

**In `staff_backend/main.py`:**

```python
from auth.routes import router as auth_router

app = FastAPI()

# Add this before running:
app.include_router(auth_router)  # ← Adds all /auth endpoints
```

### Step 5: Create First Staff Account

```bash
curl -X POST http://localhost:8000/auth/staff/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Admin",
    "email": "admin@hotel.local",
    "password": "AdminPassword123!",
    "permissions": ["view_alerts", "evacuate", "analytics"]
  }'
```

### Step 6: Test Login

```bash
curl -X POST http://localhost:8000/auth/staff/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@hotel.local",
    "password": "AdminPassword123!"
  }'

# Response:
# {
#   "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
#   "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
#   "token_type": "bearer",
#   "role": "staff",
#   "expires_in_minutes": 20
# }
```

**Done!** Your JWT system is ready.

---

## 🔗 Protecting Your Routes

### Example: Protect an Existing Route

**Before:**
```python
@router.post("/emergency/trigger")
async def trigger_emergency(request: Request):
    # Anyone can access
    return {"status": "ok"}
```

**After:**
```python
from auth.dependencies import require_staff

@router.post("/emergency/trigger")
async def trigger_emergency(staff_user: dict = Depends(require_staff)):
    # Only staff can access; guest gets 403
    staff_id = staff_user["sub"]
    return {"status": "triggered", "by": staff_id}
```

### For Guest Routes:

```python
from auth.dependencies import require_guest

@router.get("/evacuation/instructions")
async def get_instructions(guest_user: dict = Depends(require_guest)):
    room = guest_user["room_number"]
    return {"route": f"Stairwell B from room {room}"}
```

---

## 🧪 Common Test Scenarios

### Scenario 1: Staff Workflow

```bash
# 1. Register
curl -X POST http://localhost:8000/auth/staff/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Manager Bob",
    "email": "bob@hotel.local",
    "password": "BobPassword123!",
    "permissions": ["evacuate"]
  }'

# 2. Login
TOKEN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/staff/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "bob@hotel.local",
    "password": "BobPassword123!"
  }')

ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')
REFRESH_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.refresh_token')

# 3. Use token
curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 4. Refresh
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}"

# 5. Logout
curl -X POST http://localhost:8000/auth/logout \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}"
```

### Scenario 2: Guest Workflow

```bash
# 1. Guest check-in (assume guest exists in DB with room 1205)
TOKEN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/guest/checkin \
  -H "Content-Type: application/json" \
  -d '{
    "room_number": "1205",
    "phone_last4": "5678"
  }')

ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

# 2. Access guest-only endpoint
curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

### Scenario 3: Rate Limiting

```bash
# Try 6 quick login attempts (limit is 5/min):
for i in {1..6}; do
  echo "Attempt $i:"
  curl -s -X POST http://localhost:8000/auth/staff/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@hotel.local","password":"wrong"}' \
    | jq '.detail'
done

# Last attempt returns: "Too many attempts. Try again in X second(s)."
```

---

## 📋 Environment Variables Checklist

```bash
# Required:
JWT_SECRET=<your-generated-secret>

# Optional (defaults provided):
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES_STAFF=20
ACCESS_TOKEN_EXPIRE_MINUTES_GUEST=10
REFRESH_TOKEN_EXPIRE_HOURS=24

# Database (should already exist):
MONGODB_URI=mongodb+srv://...
DB_NAME=hospitality_emergency
```

---

## 🐛 Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| `RuntimeError: JWT_SECRET not set` | Add JWT_SECRET to .env |
| `401 Unauthorized: Invalid token` | Token is tampered or from wrong secret |
| `401 Unauthorized: Expired` | Access token expired; use refresh token |
| `403 Forbidden: Staff access required` | Use a staff token, not guest |
| `429 Too Many Requests` | Wait 60 seconds, then retry |
| `404: Guest not found` | Guest room/phone must match DB exactly |

---

## ✅ Quick Integration Checklist

- [ ] JWT_SECRET in .env
- [ ] MongoDB indexes created
- [ ] First staff account registered
- [ ] Auth router mounted in main.py
- [ ] Test login endpoint works
- [ ] Test protected route blocks unauthorized access
- [ ] Test refresh token works
- [ ] Test logout revokes token

---

**Status**: Ready to use!
