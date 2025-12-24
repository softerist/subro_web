import asyncio

import httpx

API_URL = "http://localhost:8000/api/v1/auth/login"


async def check_cookies():
    async with httpx.AsyncClient() as client:
        print(f"Checking Cookies from {API_URL}...")
        try:
            data = {"username": "admin@example.com", "password": "securepassword123"}
            resp = await client.post(API_URL, data=data)

            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}")
            cookies = resp.headers.get_list("set-cookie")

            if not cookies:
                print("No Set-Cookie headers found!")
                exit(1)

            for cookie in cookies:
                print(f"Cookie: {cookie}")
                if "refresh_token" in cookie:
                    print("   -> Found refresh_token")
                    if "HttpOnly" in cookie:
                        print("   -> [PASS] HttpOnly is present")
                    else:
                        print("   -> [FAIL] HttpOnly is MISSING")

                    if "SameSite=strict" in cookie or "SameSite=Strict" in cookie:
                        print("   -> [PASS] SameSite=Strict is present")
                    else:
                        print(f"   -> [FAIL] SameSite is not Strict (Got: {cookie})")

                    if "Secure" in cookie:
                        print("   -> [PASS] Secure is present")
                    else:
                        print(
                            "   -> [INFO] Secure is MISSING (Expected if COOKIE_SECURE=False in .env)"
                        )
        except Exception as e:
            print(f"Failed: {e}")


if __name__ == "__main__":
    asyncio.run(check_cookies())
