# ClinicFlow Reasoning

## Design Decisions

The repository started as an empty Python workspace, so the implementation stays intentionally small: Flask serves both the REST API and the static browser experience, avoiding a frontend build step and CORS configuration. SQLAlchemy is used directly with SQLite rather than adding a larger framework integration layer. The app factory accepts configuration overrides so behavior can be checked with an isolated in-memory database.

Authentication uses hashed passwords from Werkzeug and signed JWT claims handled by PyJWT. Protected routes derive the patient identity from the token; the client cannot select a different patient when booking or cancelling.

Business decisions live in `clinicflow/services.py`. Route handlers parse HTTP input, call a service, and translate `DomainError` into HTTP responses. This keeps the overlap and cancellation rules testable without Flask.

## Scheduling Rules

Appointment creation rejects an end time that is not after its start. Conflict detection only considers `scheduled` appointments and uses the required predicate:

```text
new_start < existing_end AND new_end > existing_start
```

Because both comparisons are strict, adjacent appointments are valid. Cancelled appointments are excluded from later conflict checks and therefore release their slot. The database work happens inside a SQLAlchemy session transaction; the backend check remains authoritative even if the frontend displayed an apparently open slot.

Cancellation compares the current UTC time with the appointment start. A cancellation at least 24 hours early has a zero fee, one inside 24 hours has a fee of ₹200, and a cancellation at or after the start is rejected.

## Testing and Validation

Focused checks were run during implementation for registration, duplicate email protection, password login, JWT issuance, adjacent appointment acceptance, overlap rejection, cancellation releasing a slot, authenticated REST booking, search, pagination, sorting, cancellation, landing page serving, static asset serving, JavaScript syntax, and Python diagnostics. The checks use Flask’s test client and in-memory SQLite, so they do not alter the persistent development database.

## Bugs Found and Fixed

The first protected API integration check returned 401 for every valid login. PyJWT validates the `sub` claim as a string, while the initial token encoded the integer user ID. The login route now serializes the subject and the auth decorator converts it back to an integer for database access.

An early service test incorrectly expected a new 15:15–15:45 appointment to work after cancelling 15:00–15:30 while a separate 15:30–16:00 appointment remained active. That test was corrected: the service was behaving correctly because the new interval still overlapped the adjacent active appointment.

## Future Features

The landing page calls out three deliberately deferred features: SMS reminders, multi-location calendars, and integrated payments/receipts. They were excluded from the assessment implementation to keep the core scheduling workflow focused.