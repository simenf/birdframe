from pathlib import Path

from fastapi.testclient import TestClient

from birdframe.main import create_app
from tests.helpers import ADMIN_PASSWORD, ADMIN_USERNAME, authed


def test_first_user_is_admin_and_second_bootstrap_is_rejected(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json()["needs_admin"] is True
        response = client.post("/api/v1/auth/bootstrap", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
        assert response.status_code == 200
        assert response.json()["is_admin"] is True
        assert response.json()["api_key"].startswith("bf_")
        assert client.get("/api/v1/health").json()["needs_admin"] is False
        second = client.post("/api/v1/auth/bootstrap", json={"username": "other", "password": ADMIN_PASSWORD})
        assert second.status_code == 403


def test_management_api_requires_a_valid_api_key(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/settings").status_code == 401
        assert client.post("/api/v1/detections", json={"common_name": "Bird", "source_event_id": "x"}).status_code == 401
        assert client.get("/api/v1/settings", headers={"Authorization": "Bearer nope"}).status_code == 401
        key = authed(client)
        assert client.get("/api/v1/settings").status_code == 200
        assert client.get("/api/v1/auth/me").json()["username"] == ADMIN_USERNAME
        assert client.get("/api/v1/auth/me").json()["is_admin"] is True
        assert key.startswith("bf_")


def test_login_and_wrong_password(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        bad = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": "wrong-password"})
        assert bad.status_code == 401
        good = client.post("/api/v1/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
        assert good.status_code == 200
        assert good.json()["username"] == ADMIN_USERNAME
        assert good.json()["api_key"].startswith("bf_")


def test_api_key_lifecycle_and_logout(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        created = client.post("/api/v1/auth/api-keys", json={"name": "wall display"}).json()
        assert created["name"] == "wall display"
        assert created["key"].startswith("bf_")
        created_row = next(key for key in client.get("/api/v1/auth/api-keys").json() if key["name"] == "wall display")
        assert created_row["last_used_at"] is None

        # The generated key works and records usage.
        second = TestClient(create_app(tmp_path))
        with second:
            second.headers.update({"Authorization": f"Bearer {created['key']}"})
            assert second.get("/api/v1/settings").status_code == 200
        created_row = next(key for key in client.get("/api/v1/auth/api-keys").json() if key["name"] == "wall display")
        assert created_row["last_used_at"] is not None

        # Revoking kills the key immediately.
        key_id = created_row["id"]
        assert client.delete(f"/api/v1/auth/api-keys/{key_id}").status_code == 204
        revoked = TestClient(create_app(tmp_path))
        with revoked:
            revoked.headers.update({"Authorization": f"Bearer {created['key']}"})
            assert revoked.get("/api/v1/settings").status_code == 401

        # Logout revokes the presented key.
        session_key = authed(client)
        assert client.post("/api/v1/auth/logout").status_code == 200
        logged_out = TestClient(create_app(tmp_path))
        with logged_out:
            logged_out.headers.update({"Authorization": f"Bearer {session_key}"})
            assert logged_out.get("/api/v1/settings").status_code == 401


def test_admin_can_manage_users_but_regular_users_cannot(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        authed(client)
        created = client.post("/api/v1/users", json={"username": "birder", "password": ADMIN_PASSWORD, "is_admin": False})
        assert created.status_code == 201
        assert created.json()["is_admin"] is False
        usernames = [user["username"] for user in client.get("/api/v1/users").json()]
        assert usernames == [ADMIN_USERNAME, "birder"]
        duplicate = client.post("/api/v1/users", json={"username": "birder", "password": ADMIN_PASSWORD})
        assert duplicate.status_code == 409

        login = client.post("/api/v1/auth/login", json={"username": "birder", "password": ADMIN_PASSWORD})
        assert login.status_code == 200
        with TestClient(create_app(tmp_path)) as regular:
            regular.headers.update({"Authorization": f"Bearer {login.json()['api_key']}"})
            assert regular.get("/api/v1/users").status_code == 403
            assert regular.post("/api/v1/users", json={"username": "sneaky", "password": ADMIN_PASSWORD}).status_code == 403
            assert regular.get("/api/v1/auth/api-keys").status_code == 200
