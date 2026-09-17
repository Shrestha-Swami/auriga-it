# ClinicFlow

ClinicFlow is a small clinic front-desk scheduling system built for a timed full-stack coding assessment. It prevents doctor double-booking, applies cancellation fees consistently, and gives staff a practical day view with patient search.

## Stack

- Python 3.11+
- Flask 3.1
- SQLAlchemy 2.0 ORM
- SQLite (persistent local database)
- PyJWT for bearer authentication
- HTML, CSS, and vanilla JavaScript served by Flask

## Setup and Run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. The SQLite database is created at `instance/clinicflow.sqlite3`, and three sample doctors are added on first run.

For development with the Flask reloader:

```bash
flask --app app run --debug
```

## Debugging and Checks

```bash
python3 -m py_compile app.py clinicflow/*.py
node --check static/app.js
curl http://127.0.0.1:5000/api/health
```

The app factory accepts a `DATABASE_URL` override, which makes isolated in-memory checks straightforward:

```python
from app import create_app
client = create_app({"DATABASE_URL": "sqlite:///:memory:"}).test_client()
```

## API

Protected endpoints use `Authorization: Bearer <token>` from the login response.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/` | Landing page and frontend workspace |
| GET | `/api/health` | Service health check |
| POST | `/api/auth/register` | Create an account; JSON: `name`, `email`, `password` (8+ chars) |
| POST | `/api/auth/login` | Authenticate; JSON: `email`, `password`; returns JWT |
| GET | `/api/doctors` | List doctors for the booking form |
| POST | `/api/appointments` | Book an appointment; JSON: `doctor_id`, `start_time`, `end_time` ISO-8601 |
| GET | `/api/appointments` | List appointments with filters and pagination |
| POST | `/api/appointments/<id>/cancel` | Cancel the authenticated patient’s appointment |

`GET /api/appointments` query parameters:

- `patient_name`: case-insensitive partial patient-name search
- `doctor_id`: filter by doctor
- `day`: ISO date, such as `2026-09-17`
- `page`: 1-based page number
- `per_page`: 1-50, default 10
- `sort`: `start_time` or `-start_time`

Appointment responses include the doctor, patient, start/end time, status, and cancellation fee. Cancellation fees are `0` at least 24 hours before the appointment and `200` within 24 hours. Cancellation after the start time is rejected.

## Project Structure

```text
app.py                    Flask app factory and REST routes
clinicflow/database.py    SQLAlchemy engine and declarative base
clinicflow/models.py      User, Doctor, and Appointment ORM models
clinicflow/services.py    Scheduling and cancellation business rules
static/index.html         Landing page and workspace markup
static/styles.css         Responsive ClinicFlow visual design
static/app.js             Auth, booking, filtering, and UI behavior
REASONING.md              Design decisions, tests, bugs, and fixes
```