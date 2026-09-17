import os
import sys
import tempfile
from pathlib import Path

import pytest


TEST_SECRET = "pytest-only-secret"
_bootstrap_dir = Path(tempfile.mkdtemp(prefix="clinicflow-pytest-bootstrap-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = f"sqlite:///{_bootstrap_dir / 'bootstrap.sqlite3'}"
os.environ["JWT_SECRET_KEY"] = TEST_SECRET

from app import create_app  # noqa: E402
from clinicflow.models import Doctor, User  # noqa: E402


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'clinicflow-test.sqlite3'}",
        "JWT_SECRET_KEY": TEST_SECRET,
        "JWT_EXPIRATION_MINUTES": 30,
    })
    yield application
    application.extensions["db_engine"].dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def records(app):
    with app.extensions["db_session_factory"]() as session:
        doctors = [
            Doctor(name="Dr. Test One", specialty="General Medicine"),
            Doctor(name="Dr. Test Two", specialty="Pediatrics"),
        ]
        patients = [
            User(name="Asha Rao", email="asha.test@example.com", password_hash="fixture-hash"),
            User(name="Ben Shah", email="ben.test@example.com", password_hash="fixture-hash"),
            User(name="Casey Iyer", email="casey.test@example.com", password_hash="fixture-hash"),
        ]
        session.add_all([*doctors, *patients])
        session.commit()
        return {"doctors": doctors, "patients": patients}


@pytest.fixture
def auth_headers(client):
    registration = client.post(
        "/api/auth/register",
        json={"name": "Logged In Patient", "email": "logged.in@example.com", "password": "password123"},
    )
    assert registration.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"email": "logged.in@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.get_json()['token']}"}


@pytest.fixture
def book(client, auth_headers):
    def create(doctor_id, start_time, end_time):
        return client.post(
            "/api/appointments",
            headers=auth_headers,
            json={
                "doctor_id": doctor_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            },
        )

    return create