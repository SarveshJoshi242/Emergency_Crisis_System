# JWT Authentication - Testing Guide

Complete testing scenarios for the JWT auth system.

---

## Prerequisites

- Backend running on `http://localhost:8000`
- MongoDB running and seeded with initial data
- JWT_SECRET set in .env
- `httpx` or `curl` available

---

## Testing Tools

### Option 1: cURL (command line)

```bash
curl -X POST http://localhost:8000/auth/staff/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@hotel.local","password":"password"}'
```

### Option 2: Python with httpx

```python
import httpx

client = httpx.Client()
resp = client.post(
    "http://localhost:8000/auth/staff/login",
    json={"email": "admin@hotel.local", "password": "password"}
)
print(resp.json())
```

### Option 3: Postman / Thunder Client

Import the examples below into your REST client.

---

## Test Suite 1: Staff Authentication

### 1.1 Register Staff Account

**Request:**
```http
POST /auth/staff/register
Content-Type: application/json

{
  "name": "Manager Alice",
  "email": "alice@hotel.local",
  "password": "SecurePassword123!",
  "permissions": ["view_alerts", "evacuate", "analytics"]
}
```

**Expected Response (201):**
```json
{
  "id": "507f1f77bcf86cd799439011",
  "name": "Manager Alice",
  "email": "alice@hotel.local",
  "permissions": ["view_alerts", "evacuate", "analytics"],
  "created_at": "2026-04-25T12:00:00Z"
}
```

**Error Cases:**
- Duplicate email → 409 Conflict: "Staff account already exists"
- Missing field → 422 Unprocessable Entity
- Invalid email → 422 Unprocessable Entity

---

### 1.2 Staff Login - Success

**Request:**
```http
POST /auth/staff/login
Content-Type: application/json

{
  "email": "alice@hotel.local",
  "password": "SecurePassword123!"
}
```

**Expected Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "staff",
  "expires_in_minutes": 20
}
```

**Validation:**
- Access token is valid JWT
- Token contains role="staff"
- Token contains permissions array
- expires_in_minutes = 20

---

### 1.3 Staff Login - Wrong Password

**Request:**
```http
POST /auth/staff/login
Content-Type: application/json

{
  "email": "alice@hotel.local",
  "password": "WrongPassword"
}
```

**Expected Response (401):**
```json
{
  "detail": "Invalid credentials."
}
```

**Important:** Error message is intentionally vague to prevent account enumeration.

---

### 1.4 Staff Login - Non-existent Email

**Request:**
```http
POST /auth/staff/login
Content-Type: application/json

{
  "email": "nonexistent@hotel.local",
  "password": "AnyPassword"
}
```

**Expected Response (401):**
```json
{
  "detail": "Invalid credentials."
}
```

**Security Note:** Same error as wrong password to avoid email enumeration.

---

### 1.5 Staff Login - Rate Limiting

**Test:** Make 6 login attempts quickly from same IP

```bash
for i in {1..6}; do
  curl -X POST http://localhost:8000/auth/staff/login \
    -H "Content-Type: application/json" \
    -d '{"email":"alice@hotel.local","password":"wrong"}' \
    -w "\nAttempt $i - Status: %{http_code}\n"
  sleep 0.1
done
```

**Expected:** Attempts 1-5 return 401, attempt 6 returns 429

**Response (429):**
```json
{
  "detail": "Too many attempts. Try again in X second(s)."
}
```

**Header:** `Retry-After: 58`

---

## Test Suite 2: Guest Authentication

### 2.1 Guest Check-in - By Booking ID

**Setup:** Ensure guest exists in DB with:
```javascript
{
  booking_id: "BOOKING_12345",
  room_number: "1205",
  status: "checked_in"
}
```

**Request:**
```http
POST /auth/guest/checkin
Content-Type: application/json

{
  "booking_id": "BOOKING_12345"
}
```

**Expected Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "guest",
  "expires_in_minutes": 10
}
```

**Validation:**
- expires_in_minutes = 10 (less than staff)
- role = "guest"

---

### 2.2 Guest Check-in - By Room + Phone

**Request:**
```http
POST /auth/guest/checkin
Content-Type: application/json

{
  "room_number": "1205",
  "phone_last4": "5678"
}
```

**Expected Response (200):** Same as above

---

### 2.3 Guest Check-in - Invalid Credentials

**Request:**
```http
POST /auth/guest/checkin
Content-Type: application/json

{
  "room_number": "9999",
  "phone_last4": "0000"
}
```

**Expected Response (401):**
```json
{
  "detail": "Guest not found or not currently checked in."
}
```

---

### 2.4 Guest Check-in - Not Checked In

**Setup:** Guest exists but status != "checked_in"

**Expected Response (401):**
```json
{
  "detail": "Guest not found or not currently checked in."
}
```

---

### 2.5 Guest Check-in - Missing Parameters

**Request:**
```http
POST /auth/guest/checkin
Content-Type: application/json

{
  "room_number": "1205"
}
```

**Expected Response (422):**
```json
{
  "detail": "Provide booking_id OR (room_number + phone_last4)."
}
```

---

## Test Suite 3: Token Management

### 3.1 Get Current User

**Setup:** Have valid access token from login

**Request:**
```http
GET /auth/me
Authorization: Bearer <access_token_here>
```

**Expected Response (200):**
```json
{
  "sub": "507f1f77bcf86cd799439011",
  "role": "staff",
  "email": "alice@hotel.local",
  "name": "Manager Alice",
  "permissions": ["view_alerts", "evacuate", "analytics"],
  "iat": 1698789600,
  "exp": 1698790800,
  "jti": "f47ac10b-58cc-4372-a567-0e02b2c3d456",
  "type": "access"
}
```

---

### 3.2 Get Current User - Missing Token

**Request:**
```http
GET /auth/me
```

**Expected Response (401):**
```json
{
  "detail": "Authorization header missing. Use: Authorization: Bearer <token>"
}
```

**Header:** `WWW-Authenticate: Bearer`

---

### 3.3 Get Current User - Invalid Token

**Request:**
```http
GET /auth/me
Authorization: Bearer invalid_token_here
```

**Expected Response (401):**
```json
{
  "detail": "Invalid or tampered token."
}
```

---

### 3.4 Refresh Token - Success

**Setup:** Have valid refresh token from login

**Request:**
```http
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "<refresh_token_from_login>"
}
```

**Expected Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...(new)",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...(new)",
  "token_type": "bearer",
  "role": "staff",
  "expires_in_minutes": 20
}
```

**Important:** Both tokens are NEW (token rotation)

---

### 3.5 Refresh Token - Already Used

**Test:** Use the OLD refresh token twice

**Request (2nd attempt):**
```http
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "<old_token_already_used>"
}
```

**Expected Response (401):**
```json
{
  "detail": "Refresh token already used or revoked. Please log in again."
}
```

**Security:** This detects token replay attacks.

---

### 3.6 Refresh Token - Expired

**Test:** Wait 24+ hours or manipulate token expiry

**Expected Response (401):**
```json
{
  "detail": "Refresh token has expired. Please log in again."
}
```

---

### 3.7 Logout

**Setup:** Have valid access token and refresh token

**Request:**
```http
POST /auth/logout
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "refresh_token": "<refresh_token>"
}
```

**Expected Response (200):**
```json
{
  "message": "Logged out successfully. Please discard your access token."
}
```

**Verification:**
- Refresh token is deleted from DB
- Next POST /refresh with same token returns 401
- Access token still works (until natural expiry)

---

### 3.8 Logout - Token Not Found

**Test:** Use a non-existent or already-revoked refresh token

**Expected Response (404):**
```json
{
  "detail": "Refresh token not found or already revoked."
}
```

---

## Test Suite 4: Role-Based Access Control

### 4.1 Staff Route - With Staff Token

**Request:**
```http
POST /examples/emergency/trigger
Authorization: Bearer <staff_access_token>
```

**Expected Response (200):**
```json
{
  "triggered_by": "507f1f77bcf86cd799439011",
  "name": "Manager Alice",
  "message": "Emergency triggered successfully."
}
```

---

### 4.2 Staff Route - With Guest Token

**Request:**
```http
POST /examples/emergency/trigger
Authorization: Bearer <guest_access_token>
```

**Expected Response (403):**
```json
{
  "detail": "Staff access required for this endpoint."
}
```

---

### 4.3 Guest Route - With Guest Token

**Request:**
```http
GET /examples/evacuation/instructions
Authorization: Bearer <guest_access_token>
```

**Expected Response (200):**
```json
{
  "room_number": "1205",
  "route": "Exit via stairwell B from room 1205.",
  "assembly_point": "Parking lot A"
}
```

---

### 4.4 Guest Route - With Staff Token

**Request:**
```http
GET /examples/evacuation/instructions
Authorization: Bearer <staff_access_token>
```

**Expected Response (403):**
```json
{
  "detail": "This endpoint is for guests only."
}
```

---

### 4.5 Permission Check - Has Permission

**Request:**
```http
POST /examples/evacuation/control
Authorization: Bearer <staff_token_with_evacuate_permission>
```

**Expected Response (200):**
```json
{
  "initiated_by": "507f1f77bcf86cd799439011",
  "message": "Evacuation sequence initiated."
}
```

---

### 4.6 Permission Check - Missing Permission

**Setup:** Staff token without "evacuate" permission

**Request:**
```http
POST /examples/evacuation/control
Authorization: Bearer <staff_token_without_evacuate>
```

**Expected Response (403):**
```json
{
  "detail": "Permission 'evacuate' is required for this action."
}
```

---

## Test Suite 5: Security Edge Cases

### 5.1 Tampered Token Signature

**Request:**
```http
GET /auth/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.TAMPERED_SIGNATURE
```

**Expected Response (401):**
```json
{
  "detail": "Invalid or tampered token."
}
```

---

### 5.2 Token Expired

**Test:** Let access token expire (20 minutes) or set exp to past

**Request:**
```http
GET /auth/me
Authorization: Bearer <expired_token>
```

**Expected Response (401):**
```json
{
  "detail": "Access token has expired. Please refresh your session."
}
```

---

### 5.3 Logout with Wrong User's Token

**Test:** Staff member A's token trying to revoke Staff member B's refresh token

**Request:**
```http
POST /auth/logout
Authorization: Bearer <user_a_token>
Content-Type: application/json

{
  "refresh_token": "<user_b_refresh_token>"
}
```

**Expected Response (404):**
```json
{
  "detail": "Refresh token not found or already revoked."
}
```

**Security Note:** Users can only revoke their own tokens due to user_id check.

---

## Test Suite 6: Integration Flow

### Complete User Journey

```bash
#!/bin/bash

BASE_URL="http://localhost:8000"
EMAIL="test@hotel.local"
PASSWORD="TestPassword123!"

# 1. Register
echo "1. Registering..."
REGISTER_RESP=$(curl -s -X POST $BASE_URL/auth/staff/register \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Test User\",
    \"email\": \"$EMAIL\",
    \"password\": \"$PASSWORD\",
    \"permissions\": [\"view_alerts\"]
  }")
echo $REGISTER_RESP | jq .
USER_ID=$(echo $REGISTER_RESP | jq -r '.id')

# 2. Login
echo -e "\n2. Logging in..."
LOGIN_RESP=$(curl -s -X POST $BASE_URL/auth/staff/login \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"password\": \"$PASSWORD\"
  }")
echo $LOGIN_RESP | jq .
ACCESS_TOKEN=$(echo $LOGIN_RESP | jq -r '.access_token')
REFRESH_TOKEN=$(echo $LOGIN_RESP | jq -r '.refresh_token')

# 3. Get current user
echo -e "\n3. Getting current user..."
curl -s -X GET $BASE_URL/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq .

# 4. Refresh token
echo -e "\n4. Refreshing token..."
REFRESH_RESP=$(curl -s -X POST $BASE_URL/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}")
echo $REFRESH_RESP | jq .
NEW_ACCESS=$(echo $REFRESH_RESP | jq -r '.access_token')
NEW_REFRESH=$(echo $REFRESH_RESP | jq -r '.refresh_token')

# 5. Verify old token is no longer valid for refresh
echo -e "\n5. Testing old token (should fail)..."
curl -s -X POST $BASE_URL/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}" | jq .

# 6. Logout
echo -e "\n6. Logging out..."
curl -s -X POST $BASE_URL/auth/logout \
  -H "Authorization: Bearer $NEW_ACCESS" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$NEW_REFRESH\"}" | jq .

# 7. Verify logout worked
echo -e "\n7. Testing new refresh token (should fail)..."
curl -s -X POST $BASE_URL/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$NEW_REFRESH\"}" | jq .
```

---

## Success Criteria Checklist

- [ ] All status codes match expected (200, 201, 401, 403, 404, 409, 422, 429)
- [ ] Token rotation works (old token becomes invalid)
- [ ] Rate limiting blocks after limit
- [ ] Token expiry is honored
- [ ] Role guards work correctly
- [ ] Permission checks work correctly
- [ ] Generic error messages for auth failures
- [ ] Refresh tokens stored in DB correctly
- [ ] Logout revokes tokens
- [ ] Token signatures are validated
- [ ] User cannot revoke other users' tokens
- [ ] Tampered tokens are rejected

---

## Performance Benchmarks

Test these on your hardware:

```python
import time
import httpx

client = httpx.Client()

# Password hashing (bcrypt cost=12)
times = []
for i in range(5):
    start = time.time()
    resp = client.post("http://localhost:8000/auth/staff/login", 
                      json={"email": "test@hotel.local", "password": "wrong"})
    times.append(time.time() - start)

avg_time = sum(times) / len(times)
print(f"Avg login attempt time: {avg_time:.2f}s")
# Expected: ~0.25-0.35s (bcrypt + db query)

# Token validation (decode only)
start = time.time()
for i in range(100):
    client.get("http://localhost:8000/auth/me", 
              headers={"Authorization": f"Bearer {token}"})
elapsed = time.time() - start
print(f"100 token validations: {elapsed:.2f}s")
# Expected: < 0.5s (stateless JWT decode is very fast)
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `RuntimeError: JWT_SECRET not set` | Missing env var | Add JWT_SECRET to .env |
| All login attempts return 401 | Staff account doesn't exist | Register account first |
| Refresh always returns 401 | Token already used (rotated) | Use new refresh token |
| Always rate limited | Hitting limit for real | Wait 60 seconds |
| Token doesn't decode | Wrong JWT_SECRET | Check env var matches |

---

**Test Environment**: April 25, 2026  
**Status**: Ready for comprehensive testing
