import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app, require_shopkeeper


class CustomerRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[require_shopkeeper] = lambda: {"phone": "+919876543210"}
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    @patch("app.main.db.create_customer")
    def test_add_customer(self, create_customer):
        create_customer.return_value = {
            "id": 1,
            "name": "Asha",
            "phone": "+919876543210",
            "amount_due": 500,
            "status": "pending",
            "promise_date": None,
        }
        response = self.client.post(
            "/customers",
            json={"name": "Asha", "phone": "98765 43210", "amount_due": 500},
        )
        self.assertEqual(response.status_code, 201)
        create_customer.assert_called_once_with("Asha", "+919876543210", 500)

    @patch("app.main.db.get_customer")
    @patch("app.main.db.update_customer")
    def test_update_customer(self, update_customer, get_customer):
        get_customer.return_value = {"id": 1, "name": "Asha", "phone": "+919876543210", "amount_due": 500}
        update_customer.return_value = {
            "id": 1,
            "name": "Asha",
            "phone": "+919876543210",
            "amount_due": 250,
            "status": "pending",
            "promise_date": None,
        }
        response = self.client.patch("/customers/1", json={"amount_due": 250})
        self.assertEqual(response.status_code, 200)
        update_customer.assert_called_once_with(1, "Asha", "+919876543210", 250)

    @patch("app.main.db.set_customer_paid")
    def test_mark_paid_and_unpaid(self, set_customer_paid):
        set_customer_paid.return_value = {"id": 1, "amount_due": 0, "status": "paid", "promise_date": None}
        paid = self.client.post("/customers/1/mark-paid")
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(set_customer_paid.call_args.kwargs, {"paid": True})

        set_customer_paid.return_value = {"id": 1, "amount_due": 500, "status": "pending", "promise_date": None}
        unpaid = self.client.post("/customers/1/mark-unpaid")
        self.assertEqual(unpaid.status_code, 200)
        self.assertEqual(set_customer_paid.call_args.kwargs, {"paid": False})

    @patch("app.main.db.record_payment")
    def test_partial_payment(self, record_payment):
        record_payment.return_value = {"id": 1, "amount_due": 250, "status": "pending"}
        response = self.client.post("/customers/1/payments", json={"amount": 250, "method": "cash"})
        self.assertEqual(response.status_code, 200)
        record_payment.assert_called_once_with(1, 250, "cash")

    @patch("app.main.db.dashboard_summary")
    def test_dashboard_summary(self, dashboard_summary):
        dashboard_summary.return_value = {"outstanding": 1000, "recovery_rate": None}
        response = self.client.get("/dashboard/summary")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["recovery_rate"])

    @patch("app.main.db.dashboard_followups")
    def test_dashboard_followups(self, dashboard_followups):
        dashboard_followups.return_value = {"items": [], "page": 1, "page_size": 25, "total": 0}
        response = self.client.get("/dashboard/followups")
        self.assertEqual(response.status_code, 200)
        dashboard_followups.assert_called_once_with(1, 25)


if __name__ == "__main__":
    unittest.main()
