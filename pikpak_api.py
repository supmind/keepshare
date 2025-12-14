#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import hashlib
import time
import random
import string
import json
import uuid
from typing import Optional, Dict, List, Any, Tuple, Union

# Constants
USER_SERVER = "https://user.mypikpak.com"
API_SERVER = "https://api-drive.mypikpak.com"
REFERRAL_SERVER = "https://api-referral.mypikpak.com"

CLIENT_ID = "YNxT9w7GMdWvEOKa"
WEB_CLIENT_ID = "YUMx5nI8ZU8Ap8pm"

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"


class PikPakException(Exception):
    def __init__(self, message, error_code=None, error_key=None):
        super().__init__(message)
        self.error_code = error_code
        self.error_key = error_key


class PikPakAPI:
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, device_id: Optional[str] = None, proxy: Optional[str] = None):
        """
        Initialize the PikPak API client.

        Args:
            username: Email address for login.
            password: Password for login.
            device_id: Optional custom device ID. If not provided, a random one is generated.
            proxy: Optional proxy URL (e.g., "http://127.0.0.1:7890").
        """
        self.username = username
        self.password = password
        self.device_id = device_id if device_id else self._generate_device_id()

        # Token storage
        self.access_token = None
        self.refresh_token = None
        self.expires_at = 0  # Timestamp
        self.user_id = None

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Content-Type": "application/json",
            "Accept-Language": "en,en-US;q=0.9",
            "X-Device-Id": self.device_id,
            "X-Client-Id": CLIENT_ID,
        })

        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    @staticmethod
    def _generate_device_id() -> str:
        """Generate a random 32-character hex device ID."""
        s = f"Device.{random.randint(0, 2**64)}.{time.time_ns()}"
        return hashlib.md5(s.encode()).hexdigest()

    @staticmethod
    def _random_password(length=12) -> str:
        """Generate a random password conforming to PikPak requirements."""
        chars = string.ascii_letters + string.digits + "~!@#$%^&_+-=."
        # Ensure at least one uppercase and one digit (simplified from Go logic)
        pwd = [
            random.choice(string.ascii_uppercase),
            random.choice(string.digits)
        ]
        pwd.extend(random.choice(chars) for _ in range(length - 2))
        random.shuffle(pwd)
        return "".join(pwd)

    def _get_api_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{API_SERVER}/{path.lstrip('/')}"

    def _get_user_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{USER_SERVER}/{path.lstrip('/')}"

    def _get_referral_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{REFERRAL_SERVER}/{path.lstrip('/')}"

    def _request(self, method: str, url: str, **kwargs) -> Dict:
        """Internal request wrapper with error handling."""
        # Auto-inject token if available and not a auth endpoint
        if self.access_token and "Authorization" not in self.session.headers and "/auth/" not in url and "/shield/" not in url:
             kwargs.setdefault("headers", {})["Authorization"] = f"Bearer {self.access_token}"
        elif self.access_token and "/auth/" not in url and "/shield/" not in url:
             # Ensure header is set in session or kwargs
             pass

        # For specific auth endpoints, we might need different client IDs
        if "/shield/captcha/init" in url or "/auth/verification" in url or "/auth/signup" in url:
             kwargs.setdefault("headers", {})["x-client-id"] = WEB_CLIENT_ID

        # Prepare headers for auth if provided in kwargs
        if "headers" in kwargs:
            # Merge with session headers but kwargs take precedence
            headers = self.session.headers.copy()
            headers.update(kwargs["headers"])
            kwargs["headers"] = headers

        response = self.session.request(method, url, **kwargs)

        try:
            data = response.json()
        except json.JSONDecodeError:
            # Fallback for non-JSON responses or empty bodies
            if response.status_code >= 400:
                raise PikPakException(f"HTTP Error {response.status_code}: {response.text}")
            return {}

        # Check for specific API errors
        if isinstance(data, dict):
            error_key = data.get("error")
            error_code = data.get("error_code", 0)
            error_desc = data.get("error_description", "")

            if error_key and (error_key.upper() != "OK") or error_code > 0:
                raise PikPakException(f"{error_code}|{error_key}|{error_desc}", error_code, error_key)

        return data

    def _ensure_token(self):
        """Ensure we have a valid access token."""
        if not self.access_token:
            if self.username and self.password:
                self.login()
            else:
                raise PikPakException("No access token and no credentials provided.")

        if time.time() > self.expires_at - 60: # Refresh if expiring in 1 minute
            if self.refresh_token:
                try:
                    self.refresh_access_token()
                except Exception:
                    # If refresh fails, try login again
                    if self.username and self.password:
                        self.login()
                    else:
                        raise
            elif self.username and self.password:
                self.login()

    # =========================================================================
    # User / Auth APIs
    # =========================================================================

    def captcha_init(self, action: str = "POST:/v1/auth/signin", email: Optional[str] = None) -> str:
        """
        Initialize captcha to get a token.

        Args:
            action: Action string, e.g., "POST:/v1/auth/signin" or "POST:/v1/auth/verification".
            email: User email.

        Returns:
            captcha_token string.
        """
        url = self._get_user_url("/v1/shield/captcha/init")
        meta = {"email": email} if email else {}

        payload = {
            "action": action,
            "client_id": WEB_CLIENT_ID,
            "device_id": self.device_id,
            "meta": meta
        }

        # Override header for this request
        headers = {
            "x-client-id": WEB_CLIENT_ID,
            "x-device-id": self.device_id
        }

        resp = self._request("POST", url, json=payload, headers=headers)
        return resp.get("captcha_token")

    def login(self):
        """Perform full login flow."""
        if not self.username or not self.password:
            raise ValueError("Username and password are required for login.")

        # 1. Get Captcha Token
        captcha_token = self.captcha_init(action="POST:/v1/auth/signin", email=self.username)

        # 2. Sign In
        url = self._get_user_url("/v1/auth/signin")
        payload = {
            "username": self.username,
            "password": self.password,
            "client_id": CLIENT_ID
        }
        headers = {
            "X-Captcha-Token": captcha_token
        }

        resp = self._request("POST", url, json=payload, headers=headers)

        self.access_token = resp.get("access_token")
        self.refresh_token = resp.get("refresh_token")
        expires_in = resp.get("expires_in", 3600)
        self.expires_at = time.time() + int(expires_in)
        self.user_id = resp.get("sub") # Usually 'sub' is the user ID in JWT/OIDC responses, though signin might not return it directly in body sometimes, PikPak usually returns it in token decode or refresh. Note: signin response might not have 'sub'.
        # Note: The 'sub' field is often in the token or user info. The `signin` response body in Go code struct `signInResponse` doesn't show `sub`.
        # However, `refresh_token` response DOES have `sub`. We can leave user_id update for later or if needed.

        # Update session header
        self.session.headers["Authorization"] = f"Bearer {self.access_token}"

        return resp

    def refresh_access_token(self):
        """Refresh access token using refresh token."""
        if not self.refresh_token:
            raise PikPakException("No refresh token available.")

        url = self._get_user_url("/v1/auth/token")
        payload = {
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }

        resp = self._request("POST", url, json=payload)

        self.access_token = resp.get("access_token")
        self.refresh_token = resp.get("refresh_token")
        self.user_id = resp.get("user_id") or resp.get("sub")
        expires_in = resp.get("expires_in", 3600)
        self.expires_at = time.time() + int(expires_in)

        self.session.headers["Authorization"] = f"Bearer {self.access_token}"
        return resp

    def send_verification_email(self, email: str, usage: str, captcha_token: str) -> str:
        """
        Send verification email.

        Args:
            email: Target email.
            usage: "REGISTER" or "PASSWORD_RESET".
            captcha_token: Token from captcha_init.

        Returns:
            verification_id
        """
        url = self._get_user_url("/v1/auth/verification")

        target = "ANY"
        if usage == "PASSWORD_RESET":
            target = "USER"

        payload = {
            "email": email,
            "target": target,
            "usage": usage,
            "locale": "en-US",
            "client_id": WEB_CLIENT_ID
        }
        if usage == "PASSWORD_RESET":
            payload["selected_channel"] = 2

        headers = {
            "x-captcha-token": captcha_token,
            "x-client-id": WEB_CLIENT_ID,
            "x-device-id": self.device_id
        }

        resp = self._request("POST", url, json=payload, headers=headers)
        return resp.get("verification_id")

    def verify_email_code(self, verification_id: str, code: str) -> str:
        """
        Verify the code sent to email.

        Returns:
            verification_token
        """
        url = self._get_user_url("/v1/auth/verification/verify")
        payload = {
            "verification_id": verification_id,
            "verification_code": code,
            "client_id": WEB_CLIENT_ID
        }
        headers = {
            "x-client-id": WEB_CLIENT_ID,
            "x-device-id": self.device_id
        }

        resp = self._request("POST", url, json=payload, headers=headers)
        return resp.get("verification_token")

    def signup(self, email: str, password: str, code: str, verification_token: str) -> Dict:
        """
        Register a new account.

        Args:
            email: User email.
            password: User password.
            code: Verification code received in email.
            verification_token: Token received from verify_email_code.
        """
        url = self._get_user_url("/v1/auth/signup")

        # Device sign logic
        device_sign = f"wdi10.{self.device_id}xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

        headers = {
            "x-device-sign": device_sign,
            "x-client-id": WEB_CLIENT_ID,
            "x-device-id": self.device_id,
            "x-provider-name": "NONE",
            "x-sdk-version": "6.0.0",
            "x-os-version": "Win32", # Mimicking PC
            "x-platform-version": "1",
            "x-protocol-version": "301",
            "Referer": "https://mypikpak.com/"
        }

        payload = {
            "email": email,
            "verification_code": code,
            "verification_token": verification_token,
            "password": password,
            "client_id": WEB_CLIENT_ID
        }

        resp = self._request("POST", url, json=payload, headers=headers)

        # Automatically set tokens if successful
        if "access_token" in resp:
            self.access_token = resp["access_token"]
            self.refresh_token = resp["refresh_token"]
            self.user_id = resp["sub"]
            self.expires_at = time.time() + int(resp.get("expires_in", 3600))
            self.session.headers["Authorization"] = f"Bearer {self.access_token}"

        return resp

    # =========================================================================
    # Drive / File APIs
    # =========================================================================

    def create_file_from_link(self, link: str, parent_id: Optional[str] = None) -> Dict:
        """
        Add an offline download task from a link.

        Args:
            link: The URL (magnet, http, etc).
            parent_id: Optional folder ID to save the file to.
        """
        self._ensure_token()

        url = self._get_api_url("/drive/v1/files")

        payload = {
            "kind": "drive#file",
            "folder_type": "DOWNLOAD",
            "upload_type": "UPLOAD_TYPE_URL",
            "url": {"url": link}
        }
        if parent_id:
            payload["parent_id"] = parent_id

        request_id = str(uuid.uuid4())
        headers = {"X-Request-Id": request_id}

        return self._request("POST", url, json=payload, headers=headers)

    def get_tasks(self, task_ids: List[str]) -> List[Dict]:
        """Query status of offline tasks."""
        self._ensure_token()

        url = self._get_api_url("/drive/v1/tasks")

        filters = {
            "id": {"in": ",".join(task_ids)}
        }
        params = {
            "type": "offline",
            "limit": "10000",
            "filters": json.dumps(filters)
        }

        resp = self._request("GET", url, params=params)
        return resp.get("tasks", [])

    def get_subtasks(self, task_id: str, limit: int = 100) -> List[Dict]:
        """Query sub-tasks (files inside a torrent task)."""
        self._ensure_token()

        url = self._get_api_url(f"/drive/v1/task/{task_id}/statuses")
        params = {"limit": str(limit)}

        resp = self._request("GET", url, params=params)
        return resp.get("statuses", [])

    def delete_files(self, file_ids: List[str]) -> str:
        """Batch delete files. Returns task_id."""
        self._ensure_token()

        if not file_ids:
            return ""

        url = self._get_api_url("/drive/v1/files:batchDelete")
        payload = {"ids": file_ids}

        resp = self._request("POST", url, json=payload)
        return resp.get("task_id", "")

    def get_quota(self) -> Dict:
        """Get storage quota usage and limit."""
        self._ensure_token()

        url = self._get_api_url("/drive/v1/about")
        resp = self._request("GET", url)
        return resp.get("quota", {})

    def get_vip_status(self) -> Dict:
        """Get VIP/Premium status."""
        self._ensure_token()

        url = self._get_api_url("/drive/v1/privilege/vip")
        resp = self._request("GET", url)
        return resp.get("data", {})

    def redeem_code(self, activation_code: str):
        """Redeem a VIP activation code."""
        self._ensure_token()

        url = self._get_api_url("/vip/v1/order/activation-code")
        payload = {"activation_code": activation_code}

        # API returns empty body on success usually, or error
        self._request("POST", url, json=payload)
        return True

    def check_link_status(self, link: str) -> str:
        """
        Check if a link is valid/supported. No auth required.
        """
        url = self._get_api_url("/drive/v1/resource/status")
        params = {"url": link}

        resp = self._request("GET", url, params=params)
        return resp.get("status", "UNKNOWN")

    # =========================================================================
    # Share APIs
    # =========================================================================

    def create_share(self, file_ids: List[str], expiration_days: int = -1, pass_code: str = None) -> str:
        """
        Create a public share link.

        Args:
            file_ids: List of file IDs to share.
            expiration_days: -1 for permanent.
            pass_code: Optional password.

        Returns:
            share_url
        """
        self._ensure_token()

        url = self._get_api_url("/drive/v1/share")

        payload = {
            "file_ids": file_ids,
            "share_to": "publiclink",
            "expiration_days": expiration_days,
            "pass_code_option": "NOT_REQUIRED"
        }
        if pass_code:
            payload["pass_code_option"] = "REQUIRED"
            payload["pass_code"] = pass_code

        resp = self._request("POST", url, json=payload)
        return resp.get("share_url")

    def get_share_status(self, share_id: str) -> Dict:
        """Get status of a share. No auth required."""
        url = self._get_api_url("/drive/v1/share")
        params = {"share_id": share_id}

        return self._request("GET", url, params=params)

    def delete_share(self, share_ids: List[str]):
        """Delete/Cancel shares."""
        self._ensure_token()

        if not share_ids:
            return

        url = self._get_api_url("/drive/v1/share:batchDelete")
        payload = {"ids": share_ids}

        self._request("POST", url, json=payload)

    # =========================================================================
    # Referral APIs
    # =========================================================================

    def get_commissions(self) -> Dict:
        """Get referral commission summary."""
        self._ensure_token()

        url = self._get_referral_url("/promoting/v1/commissions/summary")
        return self._request("GET", url)

    def join_referral(self) -> str:
        """Join the referral program."""
        self._ensure_token()

        url = self._get_referral_url("/promoting/v1/join")
        resp = self._request("POST", url, json={})
        return resp.get("id")

    def invite_sub_account(self, email: str):
        """Invite a sub-account via email."""
        self._ensure_token()

        url = self._get_referral_url("/promoting/v1/sub-account")
        payload = {"email": email}

        self._request("POST", url, json=payload)

    def get_invite_token(self) -> str:
        """Get the invite link/token."""
        self._ensure_token()

        url = self._get_referral_url("/promoting/v1/sub-account/invite-link")
        params = {"allow_login": "true", "action": "get"}

        resp = self._request("GET", url, params=params)
        return resp.get("invite_token")


if __name__ == "__main__":
    # Example Usage
    print("PikPak API Client Demo")

    # 1. Initialize
    # client = PikPakAPI(username="your_email@example.com", password="your_password")

    # 2. Login
    # try:
    #     print("Logging in...")
    #     client.login()
    #     print(f"Logged in! User ID: {client.user_id}")
    #
    #     # 3. Check Quota
    #     quota = client.get_quota()
    #     print(f"Quota: {quota}")
    #
    #     # 4. Add Task
    #     # task = client.create_file_from_link("magnet:?xt=urn:btih:...")
    #     # print(f"Task created: {task}")
    #
    # except Exception as e:
    #     print(f"Error: {e}")

    # Generate helper data
    print(f"Random Device ID: {PikPakAPI._generate_device_id()}")
    print(f"Random Password: {PikPakAPI._random_password()}")
