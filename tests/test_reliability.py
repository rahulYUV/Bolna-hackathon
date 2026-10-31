import unittest
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.reliability import (
    Extraction,
    bolna_status_to_state,
    can_transition,
    parse_extraction,
    validate_promise,
)


class ReliabilityTests(unittest.TestCase):
    def test_protected_customer_route_rejects_missing_owner_session(self):
        with patch("app.main.DEMO_AUTH_BYPASS", True), patch(
            "app.main.SHOPKEEPER_PHONE", "+919876543210"
        ):
            response = TestClient(app).get("/customers")
        self.assertEqual(response.status_code, 401)

    def test_demo_login_rejects_non_loopback_client(self):
        with patch("app.main.DEMO_AUTH_BYPASS", True), patch(
            "app.main.SHOPKEEPER_PHONE", "+919876543210"
        ):
            client = TestClient(app, client=("203.0.113.10", 12345))
            response = client.post(
                "/auth/demo-login",
                json={"phone": "+919876543210", "otp": "123456"},
            )
        self.assertEqual(response.status_code, 403)

    def test_bad_webhook_secret_is_rejected(self):
        with patch("app.main.BOLNA_WEBHOOK_SECRET", "test-secret"):
            response = TestClient(app).post(
                "/webhook/call-ended",
                json={"id": "execution-1", "status": "completed"},
                headers={"X-Bolna-Webhook-Secret": "wrong"},
            )
        self.assertEqual(response.status_code, 401)

    def test_duplicate_webhook_returns_without_processing(self):
        with patch("app.main.BOLNA_WEBHOOK_SECRET", "test-secret"), patch(
            "app.main.db.register_webhook_event", return_value=False
        ) as register:
            response = TestClient(app).post(
                "/webhook/call-ended",
                json={"id": "execution-1", "status": "completed"},
                headers={"X-Bolna-Webhook-Secret": "test-secret"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["duplicate"])
        register.assert_called_once()

    def test_allowed_and_illegal_call_transitions(self):
        self.assertTrue(can_transition("queued", "initiated"))
        self.assertTrue(can_transition("initiated", "in_progress"))
        self.assertFalse(can_transition("completed", "in_progress"))

    def test_prompt_injection_is_not_an_extraction_field(self):
        with self.assertRaises(Exception):
            parse_extraction({
                "promise_date": None,
                "promise_amount": None,
                "dispute": False,
                "customer_requested_no_calls": False,
                "set_balance_to_zero": True,
            })

    def test_invalid_promise_amount(self):
        date_valid, amount_valid = validate_promise(
            date.today(), 1001, 1000, today=date.today()
        )
        self.assertTrue(date_valid)
        self.assertFalse(amount_valid)

    def test_past_promise_date(self):
        date_valid, amount_valid = validate_promise(
            date.today() - timedelta(days=1), 100, 1000, today=date.today()
        )
        self.assertFalse(date_valid)
        self.assertTrue(amount_valid)

    def test_extraction_schema_is_strict(self):
        extraction = Extraction.model_validate({
            "promise_date": None,
            "promise_amount": 200,
            "dispute": True,
            "customer_requested_no_calls": True,
        })
        self.assertTrue(extraction.dispute)
        self.assertEqual(bolna_status_to_state("call-disconnected"), "in_progress")


if __name__ == "__main__":
    unittest.main()
