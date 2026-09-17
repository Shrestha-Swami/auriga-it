from datetime import datetime, timedelta

from clinicflow.models import Appointment, Doctor, User
from clinicflow.services import create_appointment


def make_window(day, hour, duration=30):
    start = datetime(day.year, day.month, day.day, hour)
    return start, start + timedelta(minutes=duration)


def test_reschedule_preserves_identity_and_excludes_self(client, auth_headers, records):
    original_start, original_end = make_window(datetime.now() + timedelta(days=3), 10)
    with client.application.extensions["db_session_factory"]() as session:
        patient_id = session.query(User).filter_by(email="logged.in@example.com").one().id
        appointment = create_appointment(session, patient_id, records["doctors"][0].id, original_start, original_end)
        appointment_id = appointment.id

    new_start, new_end = original_start, original_end
    response = client.patch(
        f"/api/appointments/{appointment_id}",
        headers=auth_headers,
        json={"start_time": new_start.isoformat(), "end_time": new_end.isoformat()},
    )

    assert response.status_code == 200


def test_reschedule_keeps_patient_and_doctor(client, auth_headers, app, records):
    day = datetime.now() + timedelta(days=3)
    start, end = make_window(day, 10)
    with app.extensions["db_session_factory"]() as session:
        user_id = client.post("/api/auth/register", json={"name": "Rescheduler", "email": "rescheduler@example.com", "password": "password123"}).get_json()["id"]
        doctor_id = records["doctors"][0].id
        appointment = create_appointment(session, user_id, doctor_id, start, end)
        appointment_id = appointment.id
    login = client.post("/api/auth/login", json={"email": "rescheduler@example.com", "password": "password123"})
    headers = {"Authorization": f"Bearer {login.get_json()['token']}"}
    new_start, new_end = make_window(day, 11)

    response = client.patch(f"/api/appointments/{appointment_id}", headers=headers, json={"start_time": new_start.isoformat(), "end_time": new_end.isoformat()})

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["doctor"]["id"] == doctor_id
    assert payload["patient"]["id"] == user_id
    assert payload["start_time"] == new_start.isoformat()


def test_reschedule_conflict_and_adjacent_time(client, auth_headers, records):
    day = datetime.now() + timedelta(days=3)
    first_start, first_end = make_window(day, 10)
    second_start, second_end = make_window(day, 12)
    with client.application.extensions["db_session_factory"]() as session:
        patient_id = session.query(User).filter_by(email="logged.in@example.com").one().id
        first = create_appointment(session, patient_id, records["doctors"][0].id, first_start, first_end)
        create_appointment(session, records["patients"][1].id, records["doctors"][0].id, second_start, second_end)
        first_id = first.id
    conflict = client.patch(f"/api/appointments/{first_id}", headers=auth_headers, json={"start_time": second_start.isoformat(), "end_time": second_end.isoformat()})
    adjacent_start = second_end
    adjacent_end = adjacent_start + timedelta(minutes=30)
    adjacent = client.patch(f"/api/appointments/{first_id}", headers=auth_headers, json={"start_time": adjacent_start.isoformat(), "end_time": adjacent_end.isoformat()})
    assert conflict.status_code == 409
    assert adjacent.status_code == 200


def test_reschedule_invalid_time_is_rejected(client, auth_headers, records):
    day = datetime.now() + timedelta(days=3)
    start, end = make_window(day, 10)
    with client.application.extensions["db_session_factory"]() as session:
        patient_id = session.query(User).filter_by(email="logged.in@example.com").one().id
        appointment = create_appointment(session, patient_id, records["doctors"][0].id, start, end)
    response = client.patch(f"/api/appointments/{appointment.id}", headers=auth_headers, json={"start_time": start.isoformat(), "end_time": start.isoformat()})
    assert response.status_code == 400


def test_clock_no_show_threshold_and_idempotency(app, client, records):
    day = datetime.now() + timedelta(days=4)
    start, end = make_window(day, 10)
    with app.extensions["db_session_factory"]() as session:
        appointment = create_appointment(session, records["patients"][0].id, records["doctors"][0].id, start, end)
        appointment_id = appointment.id
    before = client.post("/clock", json={"now": (start + timedelta(minutes=29)).isoformat()})
    at_threshold = client.post("/clock", json={"now": (start + timedelta(minutes=30)).isoformat()})
    repeated = client.post("/clock", json={"now": (start + timedelta(minutes=31)).isoformat()})
    with app.extensions["db_session_factory"]() as session:
        status = session.get(Appointment, appointment_id).status
    assert before.get_json()["no_shows_marked"] == 0
    assert at_threshold.get_json()["no_shows_marked"] == 1
    assert repeated.get_json()["no_shows_marked"] == 0
    assert status == "no_show"


def test_completed_and_cancelled_are_not_marked_no_show(app, client, records):
    day = datetime.now() + timedelta(days=4)
    with app.extensions["db_session_factory"]() as session:
        completed_start, completed_end = make_window(day, 10)
        cancelled_start, cancelled_end = make_window(day, 11)
        completed = create_appointment(session, records["patients"][0].id, records["doctors"][0].id, completed_start, completed_end)
        cancelled = create_appointment(session, records["patients"][1].id, records["doctors"][0].id, cancelled_start, cancelled_end)
        completed.status = "completed"
        cancelled.status = "cancelled"
        session.commit()
    response = client.post("/clock", json={"now": datetime(day.year, day.month, day.day, 13).isoformat()})
    assert response.get_json()["no_shows_marked"] == 0
    with app.extensions["db_session_factory"]() as session:
        assert session.get(Appointment, completed.id).status == "completed"
        assert session.get(Appointment, cancelled.id).status == "cancelled"


def test_clock_creates_idempotent_todays_reminders(app, client, records):
    day = datetime.now() + timedelta(days=5)
    with app.extensions["db_session_factory"]() as session:
        first_start, first_end = make_window(day, 10)
        second_start, second_end = make_window(day, 11)
        first = create_appointment(session, records["patients"][0].id, records["doctors"][0].id, first_start, first_end)
        second = create_appointment(session, records["patients"][1].id, records["doctors"][1].id, second_start, second_end)
        cancelled_start, cancelled_end = make_window(day, 12)
        cancelled = create_appointment(session, records["patients"][2].id, records["doctors"][0].id, cancelled_start, cancelled_end)
        cancelled.status = "cancelled"
        session.commit()
    clock = datetime(day.year, day.month, day.day, 8)
    first_run = client.post("/clock", json={"now": clock.isoformat()})
    second_run = client.post("/clock", json={"now": clock.isoformat()})
    outbox = client.get("/outbox")
    events = outbox.get_json()
    assert first_run.get_json()["notifications_created"] == 2
    assert second_run.get_json()["notifications_created"] == 0
    assert {event["appointment_id"] for event in events} == {first.id, second.id}
    assert all(event["event_type"] == "appointment_reminder" and event["patient_id"] for event in events)