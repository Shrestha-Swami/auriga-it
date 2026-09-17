import os
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps
from pathlib import Path

import jwt
from dotenv import load_dotenv
from flask import Flask, jsonify, request, g, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

from clinicflow.database import Base, create_database
from clinicflow.models import Appointment, Doctor, OutboxEvent, User
from clinicflow.services import (
    DomainError,
    cancel_appointment,
    complete_appointment,
    create_appointment,
    find_appointments,
    reschedule_appointment,
    run_clock_jobs,
)


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE_URL=f"sqlite:///{BASE_DIR / 'instance' / 'clinicflow.sqlite3'}",
        JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY"),
        JWT_EXPIRATION_MINUTES=30,
    )

    if test_config:
        app.config.update(test_config)

    if not app.config.get("JWT_SECRET_KEY"):
        raise RuntimeError("JWT_SECRET_KEY environment variable is required")

    database_url = app.config["DATABASE_URL"]
    if database_url.startswith("sqlite:///"):
        database_path = Path(database_url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)

    engine, session_factory = create_database(database_url)
    Base.metadata.create_all(engine)
    app.extensions["db_engine"] = engine
    app.extensions["db_session_factory"] = session_factory

    def require_auth(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            try:
                claims = jwt.decode(token, app.config["JWT_SECRET_KEY"], algorithms=["HS256"])
                g.user_id = int(claims["sub"])
            except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
                return jsonify({"error": "A valid bearer token is required"}), 401
            return handler(*args, **kwargs)
        return wrapped

    def parse_datetime(value):
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    def appointment_json(appointment):
        return {
            "id": appointment.id,
            "doctor": {"id": appointment.doctor.id, "name": appointment.doctor.name, "specialty": appointment.doctor.specialty},
            "patient": {"id": appointment.patient.id, "name": appointment.patient.name},
            "start_time": appointment.start_time.isoformat(),
            "end_time": appointment.end_time.isoformat(),
            "status": appointment.status,
            "cancellation_fee": appointment.cancellation_fee,
        }

    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "ok", "service": "ClinicFlow"})

    @app.get("/")
    def landing_page():
        return send_from_directory(BASE_DIR / "static", "index.html")

    @app.post("/api/auth/register")
    def register():
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        if not name or not email or len(password) < 8:
            return jsonify({"error": "Name, email and an 8-character password are required"}), 400

        with session_factory() as session:
            if session.query(User).filter_by(email=email).first():
                return jsonify({"error": "An account with that email already exists"}), 409
            user = User(name=name, email=email, password_hash=generate_password_hash(password))
            session.add(user)
            session.commit()
            return jsonify({"id": user.id, "name": user.name, "email": user.email}), 201

    @app.post("/api/auth/login")
    def login():
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        with session_factory() as session:
            user = session.query(User).filter_by(email=email).first()
            if not user or not check_password_hash(user.password_hash, password):
                return jsonify({"error": "Invalid email or password"}), 401
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=app.config["JWT_EXPIRATION_MINUTES"])
            token = jwt.encode(
                {"sub": str(user.id), "name": user.name, "exp": expires_at},
                app.config["JWT_SECRET_KEY"],
                algorithm="HS256",
            )
            return jsonify({"token": token, "user": {"id": user.id, "name": user.name, "email": user.email}})

    @app.get("/api/doctors")
    @require_auth
    def doctors():
        with session_factory() as session:
            records = session.query(Doctor).order_by(Doctor.name.asc()).all()
            return jsonify([{"id": doctor.id, "name": doctor.name, "specialty": doctor.specialty} for doctor in records])

    @app.post("/api/appointments")
    @require_auth
    def book_appointment():
        payload = request.get_json(silent=True) or {}
        try:
            start_time = parse_datetime(payload.get("start_time"))
            end_time = parse_datetime(payload.get("end_time"))
            doctor_id = int(payload.get("doctor_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "doctor_id, start_time and end_time are required"}), 400
        with session_factory() as session:
            try:
                appointment = create_appointment(session, g.user_id, doctor_id, start_time, end_time)
                session.refresh(appointment)
                return jsonify(appointment_json(appointment)), 201
            except DomainError as error:
                session.rollback()
                return jsonify({"error": str(error)}), error.status_code

    @app.get("/api/appointments")
    @require_auth
    def list_appointments():
        try:
            page = max(1, int(request.args.get("page", 1)))
            per_page = min(50, max(1, int(request.args.get("per_page", 10))))
            doctor_id = request.args.get("doctor_id", type=int)
            day_value = request.args.get("day")
            day = datetime.combine(date.fromisoformat(day_value), time.min) if day_value else None
        except ValueError:
            return jsonify({"error": "page, per_page and day must be valid values"}), 400
        with session_factory() as session:
            appointments, total = find_appointments(
                session,
                patient_name=request.args.get("patient_name"),
                doctor_id=doctor_id,
                day=day,
                page=page,
                per_page=per_page,
                sort=request.args.get("sort", "start_time"),
            )
            pages = (total + per_page - 1) // per_page if total else 0
            return jsonify({
                "items": [appointment_json(appointment) for appointment in appointments],
                "pagination": {"page": page, "per_page": per_page, "total": total, "pages": pages},
            })

    @app.patch("/api/appointments/<int:appointment_id>")
    @require_auth
    def reschedule(appointment_id):
        payload = request.get_json(silent=True) or {}
        try:
            start_time = parse_datetime(payload.get("start_time"))
            end_time = parse_datetime(payload.get("end_time"))
        except (TypeError, ValueError):
            return jsonify({"error": "start_time and end_time are required"}), 400
        with session_factory() as session:
            try:
                appointment = reschedule_appointment(session, appointment_id, g.user_id, start_time, end_time)
                session.refresh(appointment)
                return jsonify(appointment_json(appointment))
            except DomainError as error:
                session.rollback()
                return jsonify({"error": str(error)}), error.status_code

    @app.post("/api/appointments/<int:appointment_id>/complete")
    @require_auth
    def complete(appointment_id):
        with session_factory() as session:
            try:
                appointment = complete_appointment(session, appointment_id, g.user_id)
                session.refresh(appointment)
                return jsonify(appointment_json(appointment))
            except DomainError as error:
                session.rollback()
                return jsonify({"error": str(error)}), error.status_code

    @app.post("/api/appointments/<int:appointment_id>/cancel")
    @require_auth
    def cancel(appointment_id):
        with session_factory() as session:
            try:
                appointment = cancel_appointment(session, appointment_id, g.user_id)
                session.refresh(appointment)
                return jsonify(appointment_json(appointment))
            except DomainError as error:
                session.rollback()
                return jsonify({"error": str(error)}), error.status_code

    @app.post("/clock")
    def clock():
        payload = request.get_json(silent=True) or {}
        try:
            clock_time = parse_datetime(payload.get("now")) if payload.get("now") else datetime.utcnow()
        except (TypeError, ValueError):
            return jsonify({"error": "now must be a valid ISO-8601 datetime"}), 400
        with session_factory() as session:
            notifications_created, no_shows_marked = run_clock_jobs(session, clock_time)
        return jsonify({
            "clock": clock_time.isoformat(),
            "notifications_created": notifications_created,
            "no_shows_marked": no_shows_marked,
        })

    @app.get("/outbox")
    def outbox():
        with session_factory() as session:
            events = session.query(OutboxEvent).order_by(OutboxEvent.created_at.asc(), OutboxEvent.id.asc()).all()
            return jsonify([{
                "id": event.id,
                "event_type": event.event_type,
                "appointment_id": event.appointment_id,
                "patient_id": event.patient_id,
                "message": event.message,
                "created_at": event.created_at.isoformat(),
            } for event in events])

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)