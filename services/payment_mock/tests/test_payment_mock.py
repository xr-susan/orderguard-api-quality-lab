from fastapi.testclient import TestClient

from services.payment_mock.app.main import app
from services.payment_mock.app.store import store

client = TestClient(app)


def setup_function() -> None:
    store.reset()


def payment_payload(order_no: str = "ORDER-001") -> dict[str, object]:
    return {
        "merchant_order_no": order_no,
        "amount": "19.90",
        "currency": "CNY",
        "callback_url": "http://order-service:8000/payments/callback",
    }


def test_success_is_idempotent_and_observable() -> None:
    headers = {"Idempotency-Key": "payment-ORDER-001"}

    first = client.post("/payments", json=payment_payload(), headers=headers)
    second = client.post("/payments", json=payment_payload(), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    history = client.get("/__admin/requests/ORDER-001").json()
    assert history["count"] == 2
    assert [item["attempt"] for item in history["requests"]] == [1, 2]


def test_same_idempotency_key_rejects_different_payload() -> None:
    headers = {"Idempotency-Key": "shared-key"}
    assert (
        client.post("/payments", json=payment_payload("ORDER-A"), headers=headers).status_code
        == 201
    )

    response = client.post("/payments", json=payment_payload("ORDER-B"), headers=headers)

    assert response.status_code == 409


def test_transient_unavailable_recovers_after_configured_attempts() -> None:
    client.post(
        "/__admin/scenarios",
        json={
            "merchant_order_no": "ORDER-RETRY",
            "behavior": "unavailable",
            "fail_times": 2,
        },
    )
    headers = {"Idempotency-Key": "payment-ORDER-RETRY"}

    responses = [
        client.post("/payments", json=payment_payload("ORDER-RETRY"), headers=headers)
        for _ in range(3)
    ]

    assert [response.status_code for response in responses] == [503, 503, 201]
    assert client.get("/__admin/requests/ORDER-RETRY").json()["count"] == 3


def test_rate_limit_includes_retry_after() -> None:
    client.post(
        "/__admin/scenarios",
        json={
            "merchant_order_no": "ORDER-429",
            "behavior": "rate_limit",
            "retry_after_seconds": 0.25,
        },
    )

    response = client.post(
        "/payments",
        json=payment_payload("ORDER-429"),
        headers={"Idempotency-Key": "payment-ORDER-429"},
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "0.25"


def test_scenarios_are_isolated_and_resettable() -> None:
    client.post(
        "/__admin/scenarios",
        json={"merchant_order_no": "ORDER-BAD", "behavior": "unavailable"},
    )

    failed = client.post(
        "/payments",
        json=payment_payload("ORDER-BAD"),
        headers={"Idempotency-Key": "payment-ORDER-BAD"},
    )
    healthy = client.post(
        "/payments",
        json=payment_payload("ORDER-GOOD"),
        headers={"Idempotency-Key": "payment-ORDER-GOOD"},
    )

    assert failed.status_code == 503
    assert healthy.status_code == 201
    assert client.post("/__admin/reset").status_code == 204
    assert client.get("/__admin/requests/ORDER-BAD").json()["count"] == 0
