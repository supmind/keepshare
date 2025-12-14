#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pikpak_api import PikPakAPI, PikPakException

# Credentials provided by user
TEST_EMAIL = "ALIBABA_001@GW.LU"
TEST_PASSWORD = "!RsPaKbGqz3Js84"

def test_login():
    print(f"=== Starting PikPak Login Test ===")
    print(f"User: {TEST_EMAIL}")

    client = PikPakAPI(username=TEST_EMAIL, password=TEST_PASSWORD)

    try:
        # 1. Login
        print("\n[Step 1] Attempting Login...")
        client.login()
        print("         Login Successful!")
        print(f"         User ID      : {client.user_id}")
        print(f"         Access Token : {client.access_token[:20]}...")

        # 2. Get Quota
        print("\n[Step 2] Checking Account Quota...")
        quota = client.get_quota()
        limit = int(quota.get('limit', 0))
        usage = int(quota.get('usage', 0))
        print(f"         Limit: {limit / 1024 / 1024 / 1024:.2f} GB")
        print(f"         Usage: {usage / 1024 / 1024 / 1024:.2f} GB")

        # 3. Get VIP Status
        print("\n[Step 3] Checking VIP Status...")
        vip = client.get_vip_status()
        print(f"         Status: {vip.get('status')}")
        print(f"         Type  : {vip.get('type')}")
        print(f"         Expire: {vip.get('expire')}")

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
    test_login()
