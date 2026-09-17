from datetime import datetime, timedelta

from clinicflow.services import create_appointment


def add_appointments(app, records, count=12):
    base = datetime.now() + timedelta(days=2)
    with app.extensions["db_session_factory"]() as session:
        for index in range(count):
            doctor = records["doctors"][index % len(records["doctors"])]
            patient = records["patients"][index % len(records["patients"])]
            start = base + timedelta(days=index // len(records["doctors"]), hours=10)
            create_appointment(session, patient.id, doctor.id, start, start + timedelta(minutes=30))


def test_health_and_landing_are_public(client):
    health = client.get("/api/health")
    landing = client.get("/")

    assert health.status_code == 200
    assert health.get_json() == {"status": "ok", "service": "ClinicFlow"}
    assert landing.status_code == 200
    assert b"ClinicFlow" in landing.data


def test_doctors_and_appointments_require_authentication(client):
    assert client.get("/api/doctors").status_code == 401
    assert client.get("/api/appointments").status_code == 401


def test_doctors_and_appointments_api(client, auth_headers, records):
    doctors = client.get("/api/doctors", headers=auth_headers)
    appointments = client.get("/api/appointments", headers=auth_headers)

    assert doctors.status_code == 200
    assert len(doctors.get_json()) == 2
    assert appointments.status_code == 200
    assert appointments.get_json()["pagination"] == {"page": 1, "per_page": 10, "total": 0, "pages": 0}


def test_search_pagination_and_total_pages(client, auth_headers, app, records):
    add_appointments(app, records)

    first = client.get("/api/appointments?page=1&per_page=5", headers=auth_headers).get_json()
    middle = client.get("/api/appointments?page=2&per_page=5", headers=auth_headers).get_json()
    beyond = client.get("/api/appointments?page=4&per_page=5", headers=auth_headers).get_json()
    empty = client.get("/api/appointments?patient_name=missing", headers=auth_headers).get_json()

    assert first["pagination"] == {"page": 1, "per_page": 5, "total": 12, "pages": 3}
    assert len(first["items"]) == 5
    assert middle["pagination"]["page"] == 2 and len(middle["items"]) == 5
    assert beyond["items"] == [] and beyond["pagination"]["pages"] == 3
    assert empty["items"] == [] and empty["pagination"] == {"page": 1, "per_page": 10, "total": 0, "pages": 0}


def test_search_is_case_insensitive(client, auth_headers, app, records):
    add_appointments(app, records)

    response = client.get("/api/appointments?patient_name=asha", headers=auth_headers)
    uppercase = client.get("/api/appointments?patient_name=ASHA", headers=auth_headers)

    assert response.get_json()["pagination"]["total"] == uppercase.get_json()["pagination"]["total"]
    assert response.get_json()["pagination"]["total"] > 0


def test_per_page_limits_and_invalid_values(client, auth_headers, app, records):
    add_appointments(app, records)

    maximum = client.get("/api/appointments?per_page=999", headers=auth_headers).get_json()
    invalid = client.get("/api/appointments?per_page=invalid", headers=auth_headers)

    assert maximum["pagination"]["per_page"] == 50
    assert invalid.status_code == 400


def test_start_time_sorting_and_safe_invalid_sort_fallback(client, auth_headers, app, records):
    add_appointments(app, records)

    ascending = client.get("/api/appointments?per_page=50&sort=start_time", headers=auth_headers).get_json()["items"]
    descending = client.get("/api/appointments?per_page=50&sort=-start_time", headers=auth_headers).get_json()["items"]
    invalid = client.get("/api/appointments?per_page=50&sort=patient_name", headers=auth_headers).get_json()["items"]

    ascending_times = [item["start_time"] for item in ascending]
    descending_times = [item["start_time"] for item in descending]
    assert ascending_times == sorted(ascending_times)
    assert descending_times == sorted(descending_times, reverse=True)
    assert [item["id"] for item in invalid] == [item["id"] for item in ascending]
