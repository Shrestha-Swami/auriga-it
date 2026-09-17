from datetime import datetime, timedelta

import pytest

from clinicflow.services import DomainError, create_appointment


def window(base, start_minutes=0, duration=30):
    start = base + timedelta(minutes=start_minutes)
    return start, start + timedelta(minutes=duration)


def test_valid_creation_and_response_data(book, records):
    start, end = window(datetime.now() + timedelta(days=2))

    response = book(records["doctors"][0].id, start, end)

    assert response.status_code == 201
    assert response.get_json()["doctor"]["id"] == records["doctors"][0].id


@pytest.mark.parametrize(
    "new_start_minutes,new_duration",
    [(0, 30), (-15, 30), (15, 30), (-15, 60), (15, 10)],
    ids=["exact", "partial-left", "partial-right", "new-contains-existing", "existing-contains-new"],
)
def test_overlapping_same_doctor_is_rejected(book, records, new_start_minutes, new_duration):
    base = datetime.now() + timedelta(days=2)
    existing_start, existing_end = window(base, 0, 30)
    assert book(records["doctors"][0].id, existing_start, existing_end).status_code == 201

    response = book(records["doctors"][0].id, *window(base, new_start_minutes, new_duration))

    assert response.status_code == 409


def test_adjacent_appointments_are_allowed(book, records):
    base = datetime.now() + timedelta(days=2)
    assert book(records["doctors"][0].id, *window(base, 0, 30)).status_code == 201

    response = book(records["doctors"][0].id, *window(base, 30, 30))

    assert response.status_code == 201


def test_same_time_for_different_doctor_is_allowed(book, records):
    base = datetime.now() + timedelta(days=2)
    start, end = window(base)
    assert book(records["doctors"][0].id, start, end).status_code == 201

    response = book(records["doctors"][1].id, start, end)

    assert response.status_code == 201


def test_cancelled_appointment_releases_slot(client, book, auth_headers, records):
    base = datetime.now() + timedelta(days=2)
    first = book(records["doctors"][0].id, *window(base))
    appointment_id = first.get_json()["id"]
    assert client.post(f"/api/appointments/{appointment_id}/cancel", headers=auth_headers).status_code == 200

    response = book(records["doctors"][0].id, *window(base))

    assert response.status_code == 201


def test_end_time_must_be_after_start(book, records):
    start = datetime.now() + timedelta(days=2)

    response = book(records["doctors"][0].id, start, start)

    assert response.status_code == 400


def test_missing_doctor_and_patient_are_rejected(app, records):
    start, end = window(datetime.now() + timedelta(days=2))
    with app.extensions["db_session_factory"]() as session:
        with pytest.raises(DomainError) as missing_doctor:
            create_appointment(session, records["patients"][0].id, 99999, start, end)
        with pytest.raises(DomainError) as missing_patient:
            create_appointment(session, 99999, records["doctors"][0].id, start, end)

    assert missing_doctor.value.status_code == 404
    assert missing_patient.value.status_code == 404