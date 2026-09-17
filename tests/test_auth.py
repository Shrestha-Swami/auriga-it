from datetime import datetime, timedelta, timezone

import jwt

from tests.conftest import TEST_SECRET


def test_successful_registration(client):
    response = client.post(
        "/api/auth/register",
        json={"name": "Asha Rao", "email": "ASHA@example.com", "password": "password123"},
    )

    assert response.status_code == 201
    assert response.get_json()["email"] == "asha@example.com"


def test_duplicate_email_registration_is_rejected(client):
    payload = {"name": "Asha Rao", "email": "asha@example.com", "password": "password123"}
    assert client.post("/api/auth/register", json=payload).status_code == 201

    duplicate = client.post("/api/auth/register", json=payload)

    assert duplicate.status_code == 409


def test_successful_login_and_incorrect_password(client):
    payload = {"name": "Asha Rao", "email": "asha@example.com", "password": "password123"}
    client.post("/api/auth/register", json=payload)

    successful = client.post("/api/auth/login", json={"email": payload["email"], "password": payload["password"]})
    failed = client.post("/api/auth/login", json={"email": payload["email"], "password": "wrong-password"})

    assert successful.status_code == 200
    assert successful.get_json()["token"]
    assert failed.status_code == 401


def test_protected_endpoint_requires_jwt(client):
    response = client.get("/api/doctors")

    assert response.status_code == 401


def test_expired_jwt_is_rejected(client):
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        TEST_SECRET,
        algorithm="HS256",
    )

    response = client.get("/api/doctors", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401