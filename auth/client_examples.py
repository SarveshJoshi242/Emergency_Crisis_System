"""
Client integration examples for JWT auth.

Copy/adapt these patterns into your frontend or client code.
"""

import httpx
import json
from typing import Optional
from datetime import datetime, timedelta


# ============================================================
#  Synchronous Client (requests-like usage)
# ============================================================

class HospitalityAuthClient:
    """
    Synchronous HTTP client for JWT authentication.
    
    Usage:
        client = HospitalityAuthClient("http://localhost:8000")
        
        # Staff login
        tokens = client.staff_login("alice@hotel.local", "password")
        
        # Use token
        user = client.get_current_user(tokens["access_token"])
        
        # Refresh
        new_tokens = client.refresh(tokens["refresh_token"])
        
        # Logout
        client.logout(tokens["access_token"], tokens["refresh_token"])
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.auth_url = f"{base_url}/auth"
        self.client = httpx.Client()
    
    # ────────────────────────────────────────────────────────────────
    #  Staff Authentication
    # ────────────────────────────────────────────────────────────────
    
    def staff_register(
        self,
        name: str,
        email: str,
        password: str,
        permissions: Optional[list[str]] = None,
    ) -> dict:
        """Register a new staff account (admin use only)."""
        resp = self.client.post(
            f"{self.auth_url}/staff/register",
            json={
                "name": name,
                "email": email,
                "password": password,
                "permissions": permissions or ["view_alerts"],
            },
        )
        resp.raise_for_status()
        return resp.json()
    
    def staff_login(self, email: str, password: str) -> dict:
        """
        Staff login via email + password.
        
        Returns:
            {
                "access_token": "...",
                "refresh_token": "...",
                "token_type": "bearer",
                "role": "staff",
                "expires_in_minutes": 20
            }
        """
        resp = self.client.post(
            f"{self.auth_url}/staff/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        return resp.json()
    
    # ────────────────────────────────────────────────────────────────
    #  Guest Authentication
    # ────────────────────────────────────────────────────────────────
    
    def guest_checkin_booking(self, booking_id: str) -> dict:
        """Guest check-in via booking ID."""
        resp = self.client.post(
            f"{self.auth_url}/guest/checkin",
            json={"booking_id": booking_id},
        )
        resp.raise_for_status()
        return resp.json()
    
    def guest_checkin_room(self, room_number: str, phone_last4: str) -> dict:
        """Guest check-in via room number + last 4 of phone."""
        resp = self.client.post(
            f"{self.auth_url}/guest/checkin",
            json={"room_number": room_number, "phone_last4": phone_last4},
        )
        resp.raise_for_status()
        return resp.json()
    
    # ────────────────────────────────────────────────────────────────
    #  Token Management
    # ────────────────────────────────────────────────────────────────
    
    def get_current_user(self, access_token: str) -> dict:
        """Get current authenticated user's info from JWT."""
        resp = self.client.get(
            f"{self.auth_url}/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
    
    def refresh(self, refresh_token: str) -> dict:
        """
        Refresh access token using a valid refresh token.
        
        Returns new access + refresh token pair.
        """
        resp = self.client.post(
            f"{self.auth_url}/refresh",
            json={"refresh_token": refresh_token},
        )
        resp.raise_for_status()
        return resp.json()
    
    def logout(self, access_token: str, refresh_token: str) -> dict:
        """Logout and revoke refresh token."""
        resp = self.client.post(
            f"{self.auth_url}/logout",
            json={"refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
    
    # ────────────────────────────────────────────────────────────────
    #  Protected Route Examples
    # ────────────────────────────────────────────────────────────────
    
    def get_evacuation_instructions(self, access_token: str) -> dict:
        """[Guest only] Get evacuation route."""
        resp = self.client.get(
            f"{self.base_url}/examples/evacuation/instructions",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
    
    def trigger_emergency(self, access_token: str) -> dict:
        """[Staff only] Trigger emergency."""
        resp = self.client.post(
            f"{self.base_url}/examples/emergency/trigger",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
    
    def close(self):
        self.client.close()


# ============================================================
#  Async Client (for async apps)
# ============================================================

class HospitalityAuthClientAsync:
    """Async version for use in async applications."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.auth_url = f"{base_url}/auth"
    
    async def staff_login(self, email: str, password: str) -> dict:
        """Async staff login."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.auth_url}/staff/login",
                json={"email": email, "password": password},
            )
            resp.raise_for_status()
            return resp.json()
    
    async def guest_checkin_booking(self, booking_id: str) -> dict:
        """Async guest check-in via booking ID."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.auth_url}/guest/checkin",
                json={"booking_id": booking_id},
            )
            resp.raise_for_status()
            return resp.json()
    
    async def get_current_user(self, access_token: str) -> dict:
        """Async get current user."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.auth_url}/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()
    
    async def refresh(self, refresh_token: str) -> dict:
        """Async refresh token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.auth_url}/refresh",
                json={"refresh_token": refresh_token},
            )
            resp.raise_for_status()
            return resp.json()
    
    async def logout(self, access_token: str, refresh_token: str) -> dict:
        """Async logout."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.auth_url}/logout",
                json={"refresh_token": refresh_token},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()


# ============================================================
#  Token Management Utility
# ============================================================

class TokenManager:
    """
    Manages token lifecycle (store, check expiry, auto-refresh).
    
    Usage:
        manager = TokenManager()
        
        # Store tokens from login
        manager.set_tokens(access_token, refresh_token, expires_in_minutes=20)
        
        # Check if token needs refresh
        if manager.should_refresh():
            new_tokens = client.refresh(manager.refresh_token)
            manager.set_tokens(...)
        
        # Get current token
        token = manager.access_token
    """
    
    def __init__(self):
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: Optional[datetime] = None
    
    def set_tokens(
        self,
        access_token: str,
        refresh_token: str,
        expires_in_minutes: int = 20,
    ):
        """Store tokens and calculate expiry."""
        self.access_token = access_token
        self.refresh_token = refresh_token
        # Refresh 2 minutes before actual expiry
        self.expires_at = datetime.utcnow() + timedelta(
            minutes=expires_in_minutes - 2
        )
    
    def should_refresh(self) -> bool:
        """Check if token should be refreshed."""
        if not self.expires_at:
            return False
        return datetime.utcnow() >= self.expires_at
    
    def clear(self):
        """Clear all stored tokens."""
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
    
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        return self.access_token is not None and not self.should_refresh()


# ============================================================
#  Usage Examples
# ============================================================

if __name__ == "__main__":
    # Example 1: Staff Login Flow
    print("=" * 60)
    print("Example 1: Staff Login")
    print("=" * 60)
    
    client = HospitalityAuthClient("http://localhost:8000")
    
    try:
        # Register
        print("\n1. Registering staff...")
        result = client.staff_register(
            name="Test Manager",
            email="test@hotel.local",
            password="TestPassword123!",
            permissions=["view_alerts", "evacuate"],
        )
        print(f"   ✓ Registered: {result['email']}")
        
        # Login
        print("\n2. Logging in...")
        tokens = client.staff_login("test@hotel.local", "TestPassword123!")
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        print(f"   ✓ Access token (first 50 chars): {access_token[:50]}...")
        print(f"   ✓ Expires in: {tokens['expires_in_minutes']} minutes")
        
        # Get current user
        print("\n3. Getting current user...")
        user = client.get_current_user(access_token)
        print(f"   ✓ User: {user['name']} ({user['email']})")
        print(f"   ✓ Role: {user['role']}")
        print(f"   ✓ Permissions: {user['permissions']}")
        
        # Refresh
        print("\n4. Refreshing token...")
        new_tokens = client.refresh(refresh_token)
        print(f"   ✓ New access token received")
        print(f"   ✓ Expires in: {new_tokens['expires_in_minutes']} minutes")
        
        # Logout
        print("\n5. Logging out...")
        result = client.logout(
            new_tokens["access_token"],
            new_tokens["refresh_token"],
        )
        print(f"   ✓ {result['message']}")
        
    except httpx.HTTPStatusError as e:
        print(f"\n✗ Error: {e.response.json()}")
    finally:
        client.close()
    
    # Example 2: Token Manager
    print("\n" + "=" * 60)
    print("Example 2: Token Manager")
    print("=" * 60)
    
    manager = TokenManager()
    
    # Simulate token storage
    print("\n1. Storing tokens...")
    manager.set_tokens(
        access_token="dummy_access_token",
        refresh_token="dummy_refresh_token",
        expires_in_minutes=20,
    )
    print(f"   ✓ Tokens stored")
    print(f"   ✓ Is authenticated: {manager.is_authenticated()}")
    print(f"   ✓ Should refresh: {manager.should_refresh()}")
    
    # Check expiry (simulate time passing)
    print("\n2. Simulating token expiry...")
    manager.expires_at = datetime.utcnow() - timedelta(seconds=1)
    print(f"   ✓ Should refresh: {manager.should_refresh()}")
    
    # Clear
    print("\n3. Clearing tokens...")
    manager.clear()
    print(f"   ✓ Tokens cleared")
    print(f"   ✓ Is authenticated: {manager.is_authenticated()}")
