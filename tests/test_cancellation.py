from datetime import datetime, timedelta


def test_cancellation_at_least_24_hours_is_free(client, book, auth_headers, records):
    start = datetime.now() + timedelta(hours=48)
    appointment = book(records["doctors"][0].id, start, start + timedelta(minutes=30)).get_json()

    response = client.post(f"/api/appointments/{appointment['id']}/cancel", headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json()["cancellation_fee"] == 0


def test_late_cancellation_costs_200(client, book, auth_headers, records):
    start = datetime.now() + timedelta(hours=2)
    appointment = book(records["doctors"][0].id, start, start + timedelta(minutes=30)).get_json()

    response = client.post(f"/api/appointments/{appointment['id']}/cancel", headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json()["cancellation_fee"] == 200


def test_cancellation_after_start_is_rejected(client, book, auth_headers, records):
    start = datetime.now() - timedelta(hours=1)
    appointment = book(records["doctors"][0].id, start, start + timedelta(minutes=30)).get_json()

    response = client.post(f"/api/appointments/{appointment['id']}/cancel", headers=auth_headers)

    assert response.status_code == 400


def test_already_cancelled_appointment_is_rejected(client, book, auth_headers, records):
    start = datetime.now() + timedelta(hours=48)
    appointment = book(records["doctors"][0].id, start, start + timedelta(minutes=30)).get_json()
    endpoint = f"/api/appointments/{appointment['id']}/cancel"
    assert client.post(endpoint, headers=auth_headers).status_code == 200

    response = client.post(endpoint, headers=auth_headers)

    assert response.status_code == 400


def test_cancellation_fee_is_backend_authoritative(client, book, auth_headers, records):
    start = datetime.now() + timedelta(hours=2)
    appointment = book(records["doctors"][0].id, start, start + timedelta(minutes=30)).get_json()

    response = client.post(
        f"/api/appointments/{appointment['id']}/cancel",
        headers=auth_headers,
        json={"cancellation_fee": 0},
    )

    assert response.status_code == 200
    assert response.get_json()["cancellation_fee"] == 200