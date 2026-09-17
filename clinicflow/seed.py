import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

from .database import Base, create_database
from .models import Appointment, Doctor, User
from .services import cancel_appointment, create_appointment


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = f"sqlite:///{BASE_DIR / 'instance' / 'clinicflow.sqlite3'}"

DOCTORS = [
    ("Dr. Anika Mehta", "General Medicine"),
    ("Dr. Rohan Shah", "Pediatrics"),
    ("Dr. Leena Iyer", "Dermatology"),
    ("Dr. Vikram Menon", "Cardiology"),
    ("Dr. Kavya Rao", "Gynecology"),
]

PATIENTS = [
    ("Asha Rao", "asha.rao@clinicflow.demo"),
    ("Arjun Kapoor", "arjun.kapoor@clinicflow.demo"),
    ("Priya Nair", "priya.nair@clinicflow.demo"),
    ("Kabir Malhotra", "kabir.malhotra@clinicflow.demo"),
    ("Meera Joshi", "meera.joshi@clinicflow.demo"),
    ("Ravi Menon", "ravi.menon@clinicflow.demo"),
    ("Nisha Patel", "nisha.patel@clinicflow.demo"),
    ("Aditya Shah", "aditya.shah@clinicflow.demo"),
    ("Sneha Iyer", "sneha.iyer@clinicflow.demo"),
    ("Vikram Das", "vikram.das@clinicflow.demo"),
    ("Ananya Gupta", "ananya.gupta@clinicflow.demo"),
    ("Karan Bhatia", "karan.bhatia@clinicflow.demo"),
    ("Rhea Sood", "rhea.sood@clinicflow.demo"),
    ("Manav Khanna", "manav.khanna@clinicflow.demo"),
    ("Ishita Sen", "ishita.sen@clinicflow.demo"),
    ("Neel Verma", "neel.verma@clinicflow.demo"),
    ("Tara Kulkarni", "tara.kulkarni@clinicflow.demo"),
    ("Dev Mehra", "dev.mehra@clinicflow.demo"),
    ("Sana Ali", "sana.ali@clinicflow.demo"),
    ("Rahul Jain", "rahul.jain@clinicflow.demo"),
    ("Maya Fernandes", "maya.fernandes@clinicflow.demo"),
    ("Omar Sheikh", "omar.sheikh@clinicflow.demo"),
]


def appointment_key(doctor_id, patient_id, start_time, end_time):
    return {
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        "start_time": start_time,
        "end_time": end_time,
    }


def find_existing_appointment(session, key):
    return session.query(Appointment).filter_by(**key).first()


def add_seed_appointment(session, key, status="scheduled", cancellation_fee=0):
    appointment = find_existing_appointment(session, key)
    if appointment:
        return appointment, False

    appointment = create_appointment(
        session,
        key["patient_id"],
        key["doctor_id"],
        key["start_time"],
        key["end_time"],
    )
    if status == "cancelled":
        cancelled = cancel_appointment(session, appointment.id, key["patient_id"])
        if cancelled.cancellation_fee != cancellation_fee:
            raise RuntimeError("Seed cancellation fee did not match the expected demo window")
    return appointment, True


def seed_database(database_url=DEFAULT_DATABASE_URL):
    if database_url.startswith("sqlite:///"):
        Path(database_url.removeprefix("sqlite:///" )).parent.mkdir(parents=True, exist_ok=True)

    engine, session_factory = create_database(database_url)
    Base.metadata.create_all(engine)
    created = {"doctors": 0, "patients": 0, "appointments": 0}

    with session_factory() as session:
        doctors = []
        for name, specialty in DOCTORS:
            doctor = session.query(Doctor).filter_by(name=name, specialty=specialty).first()
            if not doctor:
                doctor = Doctor(name=name, specialty=specialty)
                session.add(doctor)
                session.flush()
                created["doctors"] += 1
            doctors.append(doctor)

        patients = []
        for name, email in PATIENTS:
            patient = session.query(User).filter_by(email=email).first()
            if not patient:
                patient = User(
                    name=name,
                    email=email,
                    password_hash=generate_password_hash(f"clinicflow-seed:{email}"),
                )
                session.add(patient)
                session.flush()
                created["patients"] += 1
            patients.append(patient)
        session.commit()

        reference_date = date.today()
        scheduled_keys = []
        for doctor_index, doctor in enumerate(doctors):
            for day_offset in range(1, 6):
                for slot_index, hour in enumerate((9, 9.5)):
                    start_time = datetime.combine(reference_date + timedelta(days=day_offset), time(int(hour), 30 if hour % 1 else 0))
                    end_time = start_time + timedelta(minutes=30)
                    patient = patients[(doctor_index * 5 + day_offset + slot_index) % len(patients)]
                    scheduled_keys.append(appointment_key(doctor.id, patient.id, start_time, end_time))

        free_cancel_start = datetime.combine(reference_date + timedelta(days=3), time(9))
        free_cancel_key = appointment_key(doctors[0].id, patients[-1].id, free_cancel_start, free_cancel_start + timedelta(minutes=30))
        _, was_created = add_seed_appointment(session, free_cancel_key, "cancelled", 0)
        created["appointments"] += was_created

        late_day = reference_date if datetime.now().hour < 7 else reference_date + timedelta(days=1)
        late_hour = 7 if late_day == reference_date else 6
        late_cancel_start = datetime.combine(late_day, time(late_hour))
        late_cancel_key = appointment_key(doctors[1].id, patients[-2].id, late_cancel_start, late_cancel_start + timedelta(minutes=30))
        _, was_created = add_seed_appointment(session, late_cancel_key, "cancelled", 200)
        created["appointments"] += was_created

        for key in scheduled_keys:
            _, was_created = add_seed_appointment(session, key)
            created["appointments"] += was_created

    engine.dispose()
    return created


if __name__ == "__main__":
    counts = seed_database(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    print(f"Seed complete: {counts}")