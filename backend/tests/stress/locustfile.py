from locust import HttpUser, between, task


class AuditLoadUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def login_traffic(self):
        # Simulate login attempts to generate audit logs
        # We use a mix of success and failures if possible, or just successes

        # 1. Login Failure (Auth Audit)
        self.client.post(
            "/api/v1/auth/login",
            data={"username": "admin@example.com", "password": "wrongpassword"},
        )

        # 2. Login Success (Auth Audit)
        self.client.post(
            "/api/v1/auth/login",
            data={"username": "admin@example.com", "password": "adminpassword"},
        )
