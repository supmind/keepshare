#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
from pikpak_api import PikPakAPI, PikPakException

# Configuration
TEST_EMAIL = "aalkdfaljdf@gw.lu"

def test_full_registration_flow():
    print(f"=== Starting PikPak Registration Test for {TEST_EMAIL} ===")

    # 1. Initialize API Client
    client = PikPakAPI()

    # 2. Generate Random Password
    password = client._random_password()
    print(f"[Step 1] Generated Password: {password}")

    try:
        # 3. Initialize Captcha (Get Token)
        print("[Step 2] Initializing Captcha...")
        captcha_token = client.captcha_init(action="POST:/v1/auth/verification", email=TEST_EMAIL)
        print(f"         Captcha Token: {captcha_token[:20]}...")

        # 4. Send Verification Email
        print(f"[Step 3] Sending Verification Email to {TEST_EMAIL}...")
        verification_id = client.send_verification_email(
            email=TEST_EMAIL,
            usage="REGISTER",
            captcha_token=captcha_token
        )
        print(f"         Verification ID: {verification_id}")

        # 5. Manual Input: Verification Code
        print("\n" + "="*50)
        print(f"ACTION REQUIRED: Please check the inbox for {TEST_EMAIL}")
        print("Enter the 6-digit verification code below.")
        print("="*50 + "\n")

        while True:
            code = input("Verification Code > ").strip()
            if len(code) == 6 and code.isdigit():
                break
            print("Invalid code. Please enter a 6-digit number.")

        # 6. Verify Email Code
        print(f"\n[Step 4] Verifying Code {code}...")
        verification_token = client.verify_email_code(
            verification_id=verification_id,
            code=code
        )
        print(f"         Verification Token: {verification_token[:20]}...")

        # 7. Final Signup
        print("[Step 5] Completing Registration (Signup)...")
        signup_resp = client.signup(
            email=TEST_EMAIL,
            password=password,
            code=code,
            verification_token=verification_token
        )

        print("\n=== Registration SUCCESS ===")
        print(f"User ID      : {client.user_id}")
        print(f"Access Token : {client.access_token[:20]}...")
        print(f"Refresh Token: {client.refresh_token[:20]}...")

        # 8. Test Login with New Credentials
        print("\n[Step 6] Verifying Login with New Credentials...")
        # Create a new client instance to ensure clean state
        new_client = PikPakAPI(username=TEST_EMAIL, password=password)
        new_client.login()

        print("         Login Successful!")
        print(f"         User ID verified: {new_client.user_id}")

        # 9. Get Quota to prove it works
        print("\n[Step 7] Checking Account Quota...")
        quota = new_client.get_quota()
        print(f"         Limit: {int(quota.get('limit', 0)) / 1024 / 1024 / 1024:.2f} GB")
        print(f"         Usage: {int(quota.get('usage', 0)) / 1024 / 1024 / 1024:.2f} GB")

    except PikPakException as e:
        print(f"\n[!] PikPak API Error: {e}")
        if e.error_code:
            print(f"    Code: {e.error_code}")
            print(f"    Key : {e.error_key}")
    except Exception as e:
        print(f"\n[!] Unexpected Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_full_registration_flow()
