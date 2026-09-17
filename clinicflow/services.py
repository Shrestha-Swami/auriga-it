from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy import func, select

from .models import Appointment, Doctor, User


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