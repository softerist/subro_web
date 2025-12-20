import asyncio
import time

import httpx

# Configuration
API_URL = "http://localhost:8000/api/v1"
EMAIL = "test_verify_remove@example.com"
PASSWORD = "password123"  # Default credentials


async def run_verification():
    print("--- Starting Job Removal Verification ---")

    async with httpx.AsyncClient(base_url=API_URL) as client:
        # 0. Register Test User
        print(f"[0] Registering test user {EMAIL}...")
        reg_resp = await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
        if reg_resp.status_code == 201:
            print("    Registration successful.")
        elif reg_resp.status_code == 400 and "REGISTER_USER_ALREADY_EXISTS" in reg_resp.text:
            print("    User already exists. Proceeding to login.")
        else:
            print(
                f"    Registration failed (might exist): {reg_resp.status_code} - {reg_resp.text}"
            )

        # 1. Login
        print(f"[1] Logging in as {EMAIL}...")
        resp = await client.post("/auth/login", data={"username": EMAIL, "password": PASSWORD})
        if resp.status_code != 200:
            print(f"Login failed: {resp.text}")
            return
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("    Login successful.")

        # 2. Create a Job
        print("[2] Creating a new job (target: /tmp)...")
        job_payload = {"folder_path": "/tmp", "language": "eng"}
        resp = await client.post("/jobs/", json=job_payload, headers=headers)
        if resp.status_code != 201:
            print(f"Job creation failed: {resp.text}")
            return
        job = resp.json()
        job_id = job["id"]
        print(f"    Job created. ID: {job_id}")

        # 3. Wait for Job to be PENDING or RUNNING
        print("[3] Waiting for job to initialize...")
        attempts = 0
        while attempts < 10:
            resp = await client.get(f"/jobs/{job_id}", headers=headers)
            status = resp.json()["status"]
            print(f"    Current Status: {status}")
            if status in ["PENDING", "RUNNING"]:
                break
            await asyncio.sleep(1)
            attempts += 1

        # 4. Remove the Job (The Core Test)
        print(f"[4] executing REMOVE (DELETE /jobs/{job_id})...")
        print("    Expecting immediate deletion and task revocation signal.")
        start_time = time.time()
        resp = await client.delete(f"/jobs/{job_id}", headers=headers)
        duration = time.time() - start_time

        if resp.status_code == 200:
            print(f"    REMOVE Call Successful (Took {duration:.3f}s)")
            print(f"    Response Status: {resp.json().get('status', 'N/A')} (Last known state)")
        else:
            print(f"    REMOVE Call Failed: {resp.status_code} - {resp.text}")
            return

        # 5. Verify Deletion
        print(f"[5] Verifying Job is gone (GET /jobs/{job_id})...")
        resp = await client.get(f"/jobs/{job_id}", headers=headers)
        if resp.status_code == 404:
            print("    SUCCESS: Job returned 404 Not Found.")
            print("    The record was successfully removed from the database.")
        else:
            print(f"    FAILURE: Job still exists with status {resp.status_code}!")
            print(f"    Body: {resp.text}")

        print("\n--- Verification Complete ---")


if __name__ == "__main__":
    asyncio.run(run_verification())
