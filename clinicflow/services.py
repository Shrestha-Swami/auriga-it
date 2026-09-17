from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy import func, select

from .models import Appointment, Doctor, OutboxEvent, User


appointment_creation_lock = Lock()


class DomainError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def create_appointment(session, patient_id, doctor_id, start_time, end_time):
    with appointment_creation_lock:
        if end_time <= start_time:
            raise DomainError("Appointment end time must be after start time")
        if not session.get(User, patient_id):
            raise DomainError("Patient account was not found", 404)
        if not session.get(Doctor, doctor_id):
            raise DomainError("Doctor was not found", 404)

        conflict = session.scalar(
            select(Appointment.id).where(
                Appointment.doctor_id == doctor_id,
                Appointment.status == "scheduled",
                Appointment.start_time < end_time,
                Appointment.end_time > start_time,
            ).limit(1)
        )
        if conflict:
            raise DomainError("Doctor already has an overlapping appointment", 409)

        appointment = Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            start_time=start_time,
            end_time=end_time,
        )
        session.add(appointment)
        session.commit()
        return appointment


def reschedule_appointment(session, appointment_id, patient_id, start_time, end_time):
    with appointment_creation_lock:
        appointment = session.get(Appointment, appointment_id)
        if not appointment:
            raise DomainError("Appointment was not found", 404)
        if appointment.patient_id != patient_id:
            raise DomainError("You can only reschedule your own appointments", 403)
        if appointment.status != "scheduled":
            raise DomainError("Only scheduled appointments can be rescheduled")
        if datetime.utcnow() >= appointment.start_time:
            raise DomainError("Appointments cannot be rescheduled after they have started")
        if end_time <= start_time:
            raise DomainError("Appointment end time must be after start time")

        conflict = session.scalar(
            select(Appointment.id).where(
                Appointment.id != appointment_id,
                Appointment.doctor_id == appointment.doctor_id,
                Appointment.status == "scheduled",
                Appointment.start_time < end_time,
                Appointment.end_time > start_time,
            ).limit(1)
        )
        if conflict:
            raise DomainError("Doctor already has an overlapping appointment", 409)

        appointment.start_time = start_time
        appointment.end_time = end_time
        session.commit()
        return appointment


def complete_appointment(session, appointment_id, patient_id):
    with appointment_creation_lock:
        appointment = session.get(Appointment, appointment_id)
        if not appointment:
            raise DomainError("Appointment was not found", 404)
        if appointment.patient_id != patient_id:
            raise DomainError("You can only complete your own appointments", 403)
        if appointment.status != "scheduled":
            raise DomainError("Only scheduled appointments can be completed")
        appointment.status = "completed"
        session.commit()
        return appointment


def run_clock_jobs(session, clock_time):
    with appointment_creation_lock:
        today_start = datetime.combine(clock_time.date(), datetime.min.time())
        tomorrow_start = today_start + timedelta(days=1)
        todays_appointments = session.scalars(
            select(Appointment).where(
                Appointment.start_time >= today_start,
                Appointment.start_time < tomorrow_start,
                Appointment.status == "scheduled",
            ).order_by(Appointment.start_time.asc())
        ).all()
        scheduled_appointments = session.scalars(
            select(Appointment).where(Appointment.status == "scheduled")
        ).all()

        notifications_created = 0
        no_shows_marked = 0
        for appointment in scheduled_appointments:
            if clock_time >= appointment.start_time + timedelta(minutes=30):
                appointment.status = "no_show"
                no_shows_marked += 1

        for appointment in todays_appointments:
            if appointment.status != "scheduled":
                continue
            existing_event = session.scalar(
                select(OutboxEvent.id).where(
                    OutboxEvent.event_type == "appointment_reminder",
                    OutboxEvent.appointment_id == appointment.id,
                ).limit(1)
            )
            if existing_event:
                continue
            session.add(OutboxEvent(
                event_type="appointment_reminder",
                appointment_id=appointment.id,
                patient_id=appointment.patient_id,
                message=f"Reminder: appointment with {appointment.doctor.name} at {appointment.start_time.isoformat()}",
            ))
            notifications_created += 1

        session.commit()
        return notifications_created, no_shows_marked


def cancel_appointment(session, appointment_id, patient_id):
    appointment = session.get(Appointment, appointment_id)
    if not appointment:
        raise DomainError("Appointment was not found", 404)
    if appointment.patient_id != patient_id:
        raise DomainError("You can only cancel your own appointments", 403)
    if appointment.status != "scheduled":
        raise DomainError("Only scheduled appointments can be cancelled")

    now = datetime.utcnow()
    if now >= appointment.start_time:
        raise DomainError("Appointments cannot be cancelled after they have started")
    appointment.status = "cancelled"
    appointment.cancellation_fee = 0 if appointment.start_time - now >= timedelta(hours=24) else 200
    session.commit()
    return appointment


def find_appointments(session, *, patient_name=None, doctor_id=None, day=None, page=1, per_page=10, sort="start_time"):
    filters = []
    if patient_name:
        filters.append(func.lower(User.name).like(f"%{patient_name.lower()}%"))
    if doctor_id:
        filters.append(Appointment.doctor_id == doctor_id)
    if day:
        filters.extend([Appointment.start_time >= day, Appointment.start_time < day + timedelta(days=1)])

    query = select(Appointment).join(Appointment.patient).join(Appointment.doctor).where(*filters)
    query = query.order_by(Appointment.start_time.desc() if sort == "-start_time" else Appointment.start_time.asc())
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    appointments = session.scalars(query.offset((page - 1) * per_page).limit(per_page)).all()
    return appointments, total