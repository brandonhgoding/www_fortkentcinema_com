"""The Square customer profile looked up or made for a checkout's buyer."""

from boxoffice.customers import ensure_customer
from boxoffice.gateway import GatewayError
from boxoffice.tests.fakes import FakeGateway
from django.test import SimpleTestCase

ANN = {"first_name": "Ann", "last_name": "Lee", "email": "ann@example.com",
       "key": "tok", "label": "FK-ABCDE"}


class EnsureCustomerTests(SimpleTestCase):
    def test_makes_a_profile_from_the_fields_with_a_keyed_idempotency(self):
        gw = FakeGateway()
        self.assertEqual(ensure_customer(gw, phone="+12075550100", **ANN), "C-1")
        self.assertEqual(gw.customers["C-1"], {
            "given_name": "Ann", "family_name": "Lee",
            "email": "ann@example.com", "phone": "+12075550100"})
        create = [c for c in gw.calls if c[0] == "create_customer"][0][1]
        self.assertEqual(create["idempotency_key"], "customer-tok")

    def test_reuses_the_profile_with_that_email(self):
        gw = FakeGateway()
        gw.customers["C-9"] = {"given_name": "Annie", "family_name": "Lee",
                               "email": "ann@example.com", "phone": ""}
        self.assertEqual(ensure_customer(gw, phone="", **ANN), "C-9")
        self.assertEqual([c[0] for c in gw.calls], ["find_customer"])

    def test_rejected_phone_is_left_off_under_a_second_key(self):
        gw = FakeGateway(reject_phone=True)
        self.assertEqual(ensure_customer(gw, phone="+12075550100", **ANN), "C-1")
        self.assertEqual(gw.customers["C-1"]["phone"], "")
        keys = [c[1]["idempotency_key"] for c in gw.calls if c[0] == "create_customer"]
        self.assertEqual(keys, ["customer-tok", "customer-tok-nophone"])

    def test_gateway_failure_gives_blank_and_warns_with_the_label(self):
        gw = FakeGateway(fail_with=GatewayError("boom"))
        with self.assertLogs("boxoffice.customers", "WARNING") as logs:
            self.assertEqual(ensure_customer(gw, phone="", **ANN), "")
        self.assertIn("FK-ABCDE", logs.output[0])
