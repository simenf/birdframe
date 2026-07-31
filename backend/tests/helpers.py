"""Shared test helpers."""
from fastapi.testclient import TestClient


ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "test-password-123"


def authed(client: TestClient) -> str:
    """Bootstrap (or log in as) the admin and attach a valid API key to the client.

    Returns the API key used, so tests can revoke it or assert on it.
    """
    response = client.post("/api/v1/auth/bootstrap", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    if response.status_code != 200:
        response = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    key = response.json()["api_key"]
    client.headers.update({"Authorization": f"Bearer {key}"})
    return key
