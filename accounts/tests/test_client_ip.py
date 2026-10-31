from unittest import mock

from axes.helpers import get_client_ip_address
from django.test import RequestFactory, SimpleTestCase, override_settings

from accounts.client_ip import UNKNOWN, bucket, request_ip


def make(**meta):
    return RequestFactory().get("/", **meta)


class RequestIpTests(SimpleTestCase):
    @override_settings(USE_PROXY_HEADERS=True)
    def test_proxy_mode_reads_x_real_ip(self):
        req = make(REMOTE_ADDR="", HTTP_X_REAL_IP="203.0.113.7")
        self.assertEqual(request_ip(req), "203.0.113.7")

    @override_settings(USE_PROXY_HEADERS=True)
    def test_proxy_mode_ignores_forwarded_for(self):
        req = make(
            REMOTE_ADDR="",
            HTTP_X_REAL_IP="203.0.113.7",
            HTTP_X_FORWARDED_FOR="1.2.3.4",
        )
        self.assertEqual(request_ip(req), "203.0.113.7")

    @override_settings(USE_PROXY_HEADERS=False)
    def test_direct_mode_uses_remote_addr(self):
        req = make(REMOTE_ADDR="198.51.100.2", HTTP_X_REAL_IP="1.2.3.4")
        self.assertEqual(request_ip(req), "198.51.100.2")

    @override_settings(USE_PROXY_HEADERS=False)
    def test_empty_or_garbage_is_none(self):
        self.assertIsNone(request_ip(make(REMOTE_ADDR="")))
        self.assertIsNone(request_ip(make(REMOTE_ADDR="not-an-ip")))

    @override_settings(USE_PROXY_HEADERS=True)
    def test_garbage_header_is_none(self):
        self.assertIsNone(request_ip(make(REMOTE_ADDR="", HTTP_X_REAL_IP="nope")))

    def test_object_without_meta_is_none(self):
        self.assertIsNone(request_ip(object()))

    @override_settings(USE_PROXY_HEADERS=True)
    def test_axes_uses_it(self):
        req = make(REMOTE_ADDR="", HTTP_X_REAL_IP="203.0.113.7")
        self.assertEqual(get_client_ip_address(req), request_ip(req))
        self.assertEqual(get_client_ip_address(req), "203.0.113.7")


class BucketTests(SimpleTestCase):
    @override_settings(USE_PROXY_HEADERS=True)
    def test_known_address_is_its_own_bucket(self):
        with mock.patch("accounts.client_ip._warned", False):
            self.assertEqual(bucket(make(HTTP_X_REAL_IP="203.0.113.7")), "203.0.113.7")

    @override_settings(USE_PROXY_HEADERS=True)
    def test_missing_address_shares_one_bucket_and_warns_once(self):
        # nginx not sending X-Real-IP must not switch every throttle off
        # silently: all such requests count together, and the log says so.
        with mock.patch("accounts.client_ip._warned", False):
            with self.assertLogs("accounts.client_ip", "WARNING") as logs:
                self.assertEqual(bucket(make(REMOTE_ADDR="")), UNKNOWN)
            self.assertIn("X-Real-IP", logs.output[0])
            with self.assertNoLogs("accounts.client_ip", "WARNING"):
                self.assertEqual(bucket(make(REMOTE_ADDR="")), UNKNOWN)
