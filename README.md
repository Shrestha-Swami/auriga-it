# ClinicFlow

## Overview

ClinicFlow is a Flask-served clinic front-desk scheduling application. It gives staff a clear view of appointments, prevents doctor double-booking, supports patient search and pagination, and applies cancellation fees consistently.

## Problem Statement

Clinic reception teams need to book appointments without overlapping a doctor's active schedule, find patient appointments quickly, handle cancellations fairly, and keep routine appointment automation predictable. ClinicFlow keeps those decisions in the backend while providing a simple browser workspace for daily use.

## Key Features

- Landing page for clinic teams, independent practices, and specialist clinics
- User registration and JWT-based login
- Persistent SQLite database
- Doctor selection with specialty information
- Appointment booking with backend conflict detection
- Adjacent appointments allowed; overlapping appointments rejected
- Doctor and date schedule filters
- Case-insensitive patient-name search
- Pagination and start-time sorting
- Cancellation fees of ₹0 or ₹200 based on notice period
- Appointment rescheduling with conflict re-checking
- Simulated clock for no-show automation and reminder generation
- Persistent notification outbox for assessment verification

## Tech Stack

- Python
- Flask 3.1.2
- SQLAlchemy 2.0.43
- SQLite
- PyJWT 2.10.1
- python-dotenv 1.1.1
- HTML, CSS, and vanilla JavaScript
- pytest 8.4.2

No frontend framework or external database service is required.

## Project Structure

```text
app.py                    Flask app factory and REST routes
clinicflow/database.py    SQLAlchemy engine, sessions, and SQLite pragmas
clinicflow/models.py      User, Doctor, Appointment, and OutboxEvent models
clinicflow/services.py    Booking, rescheduling, cancellation, clock, and outbox logic
clinicflow/seed.py        Explicit deterministic idempotent demo-data seed command
static/index.html         Landing page and workspace markup
static/styles.css         Responsive healthcare SaaS styling
static/app.js             Authentication and workspace interactions
tests/                    Focused pytest suite using temporary SQLite databases
REASONING.md              Design decisions and implementation notes
```

## Database Design

The application uses SQLite through SQLAlchemy ORM. The default database is `instance/clinicflow.sqlite3`. Tables are created automatically with `Base.metadata.create_all()` when the application starts.

Models:

- `User`: patient/account identity, email, password hash
- `Doctor`: doctor name and specialty
- `Appointment`: doctor, patient, start/end times, status, cancellation fee
- `OutboxEvent`: generated reminder events linked to an appointment and patient

SQLite foreign-key enforcement and a five-second busy timeout are enabled for connections. Existing data is preserved; startup initialization is safe to run repeatedly.

## Core Business Rules

The backend rejects an appointment when the same doctor's scheduled appointment overlaps the requested interval:

```text
existing.start_time < new.end_time
AND
existing.end_time > new.start_time
```

- Overlapping appointments for the same doctor are rejected with HTTP 409.
- Adjacent appointments are allowed.
- Different doctors can have appointments at the same time.
- Cancelled appointments do not block a slot.
- Appointment end time must be after start time.
- Cancellation at least 24 hours before the appointment costs ₹0.
- Cancellation less than 24 hours before the appointment costs ₹200.
- Cancellation after the appointment has started is rejected.
- Already cancelled appointments cannot be cancelled again.
- Cancellation fees are calculated by the backend.

Appointment creation, rescheduling, completion, and clock automation reuse the existing process-level appointment mutation lock. This protects concurrent mutations within the current single-process deployment.

## API Documentation

Protected endpoints require:

```http
Authorization: Bearer <JWT>
```

### Public endpoints

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/` | Serves the landing page and browser application. |
| `GET` | `/api/health` | Returns `{"status":"ok","service":"ClinicFlow"}`. |
| `POST` | `/api/auth/register` | Creates an account. Body: `name`, `email`, `password` with an 8-character minimum. Returns `201`; duplicate email returns `409`. |
| `POST` | `/api/auth/login` | Authenticates with `email` and `password`, returning a 30-minute JWT and user summary. Invalid credentials return `401`. |
| `POST` | `/clock` | Runs synchronous reminder and no-show jobs. Accepts optional JSON `{"now":"ISO-8601 datetime"}`. |
| `GET` | `/outbox` | Returns persisted notification events in creation order. |

### Protected endpoints

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/doctors` | Lists doctors with `id`, `name`, and `specialty`. |
| `POST` | `/api/appointments` | Books an appointment. Body: `doctor_id`, `start_time`, `end_time` as ISO-8601 datetimes. Returns `201`; conflicts return `409`. |
| `GET` | `/api/appointments` | Lists appointments with search, doctor/date filters, pagination, and sorting. |
| `PATCH` | `/api/appointments/<id>` | Reschedules the authenticated patient's appointment. Body: `start_time`, `end_time`. Returns the normal appointment response. |
| `POST` | `/api/appointments/<id>/complete` | Marks the authenticated patient's scheduled appointment as `completed`. |
| `POST` | `/api/appointments/<id>/cancel` | Cancels the authenticated patient's scheduled appointment and calculates its fee. |

Appointment responses include:

```json
{
  "id": 1,
  "doctor": {"id": 1, "name": "Dr. Anika Mehta", "specialty": "General Medicine"},
  "patient": {"id": 1, "name": "Asha Rao"},
  "start_time": "2026-09-18T09:00:00",
  "end_time": "2026-09-18T09:30:00",
  "status": "scheduled",
  "cancellation_fee": 0
}
```

`GET /api/appointments` query parameters:

- `patient_name`: case-insensitive partial patient-name search
- `doctor_id`: doctor filter
- `day`: ISO date filter
- `page`: 1-based page number, bounded to a minimum of 1
- `per_page`: page size, bounded from 1 through 50; default 10
- `sort`: `start_time` for ascending order or `-start_time` for descending order; other values safely use ascending order

The response contains `items` and `pagination` with `page`, `per_page`, `total`, and `pages`.

## Assessment Twist Implementations

### T6 — Rescheduling

`PATCH /api/appointments/<id>` changes only the start and end times. The existing doctor and patient remain unchanged. The new interval must be valid and conflict-free. The appointment being rescheduled is excluded from its own conflict query, while the original overlap predicate and scheduled-only filtering remain in force. Cancelled or already-started appointments cannot be rescheduled. The existing appointment mutation lock is reused.

### T1 — Appointment Reminder Outbox

`POST /clock` generates `appointment_reminder` events for scheduled appointments on the simulated clock date. Each event includes an event type, appointment ID, patient ID, message, and creation timestamp. Cancelled, completed, and no-show appointments are excluded. A unique event type/appointment constraint and an existence check prevent duplicates. Events persist in the SQLite `outbox_events` table; no email or SMS is sent.

### T2 — No-Show Automation

`POST /clock` also marks scheduled appointments as `no_show` when:

```text
clock_time >= start_time + 30 minutes
```

Appointments remain scheduled before the threshold. Completed and cancelled appointments are preserved. Already no-show appointments are not processed again. Clock processing is synchronous and idempotent.

The clock response is:

```json
{
  "clock": "2026-09-18T10:30:00",
  "notifications_created": 2,
  "no_shows_marked": 1
}
```

## Setup & Installation

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and replace the placeholder with a strong randomly generated secret. Do not commit the real `.env` file. `.env` is ignored by Git, and `.env.example` contains only the expected variable format.

## Environment Configuration

ClinicFlow requires `JWT_SECRET_KEY`. The application loads it from `.env` when that file is present, or from the process environment. The application fails clearly at startup if the value is missing.

Safe local format:

```env
JWT_SECRET_KEY=replace_with_a_secure_random_secret
```

Use a strong randomly generated value locally. Never put a real secret, token, password, or credential in this README or in `.env.example`. Never commit `.env`.

## Database Seeding

Seeding is explicit and idempotent:

```bash
python3 -m clinicflow.seed
```

The command creates or reuses five doctors, 22 patients, and 52 deterministic appointments, including scheduled and cancelled examples. It checks stable doctor and patient identifiers and does not automatically insert demo data whenever the application starts. Seed patient passwords are hashed and are not intended as demo login credentials.

## Running the Application

After configuring `.env`:

```bash
python app.py
```

Open `http://127.0.0.1:5000`. Flask serves both the REST API and the static frontend, so no separate frontend server or CORS configuration is required.

For the Flask development reloader:

```bash
flask --app app run --debug
```

## Testing

Run the automated suite:

```bash
pytest -q
```

The latest verified result is:

```text
35 passed
```

Tests use isolated temporary SQLite databases. They do not modify the persistent `instance/clinicflow.sqlite3` database.

Additional checks:

```bash
python3 -m py_compile app.py clinicflow/*.py
node --check static/app.js
```

## Example Workflow

1. Create and activate a virtual environment.
2. Install dependencies and copy `.env.example` to `.env`.
3. Set a private `JWT_SECRET_KEY` in `.env`.
4. Run `python3 -m clinicflow.seed` for deterministic demo data.
5. Start the app with `python app.py`.
6. Register or log in from the landing page.
7. Select a doctor and book an ISO-8601 start/end interval.
8. Use the schedule doctor/date filters, patient search, pagination, and sorting.
9. Try an overlapping booking to observe the backend HTTP 409 conflict response.
10. Use `PATCH /api/appointments/<id>` to reschedule a future appointment.
11. Use `POST /clock` with a simulated timestamp to generate reminders and mark overdue appointments as no-show.
12. Inspect generated reminder events with `GET /outbox`.

## Engineering Decisions

- Flask serves the API and frontend to keep the assessment setup small and avoid CORS/build complexity.
- SQLAlchemy ORM and SQLite provide persistent local storage with minimal dependencies.
- Business rules live in services rather than route handlers.
- The backend is authoritative for overlap detection and cancellation fees.
- Appointment mutations use a process-level lock for the current single-process deployment.
- Clock automation is synchronous and deterministic when an explicit ISO timestamp is supplied.
- The outbox records notification intent without integrating an external delivery provider.

## Known Limitations

- SQLite is suitable for this assessment but is not intended as a high-scale production database.
- The appointment mutation lock protects the current single-process deployment and is not a distributed locking mechanism.
- `/clock` and `/outbox` are assessment/demo-facing interfaces.
- Notification reminders are persisted as outbox events rather than sent through a real external provider.

## Future Enhancements

1. Real email/SMS notification delivery
2. Role-based access for front-desk staff, doctors, and patients
3. Production-grade database and distributed job processing