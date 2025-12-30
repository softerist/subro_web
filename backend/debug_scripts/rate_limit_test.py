import asyncio
import sys

import httpx

API_URL = "http://localhost:8000/api/v1/auth/login"


async def test_limit():
    async with httpx.AsyncClient() as client:
        print(f"Testing Login Rate Limit against {API_URL} (Limit: 5/min)")
        hit_limit = False
        for i in range(1, 10):
            try:
                # Login requires form data
                data = {"username": "admin@example.com", "password": "Pa44w0rd"}
                resp = await client.post(API_URL, data=data)
                print(f"   Request {i}: Status {resp.status_code}")
                if resp.status_code == 429:
                    print("   [SUCCESS] Rate limit 429 triggered.")
                    hit_limit = True
                    break
            except Exception as e:
                print(f"   Request {i}: Failed with error {e}")

        if not hit_limit:
            print("   [FAILURE] Rate limit was NOT triggered after 9 attempts.")
            sys.exit(1)
        else:
            print("   Test Passed.")


if __name__ == "__main__":
    try:
        asyncio.run(test_limit())
    except KeyboardInterrupt:
        pass
