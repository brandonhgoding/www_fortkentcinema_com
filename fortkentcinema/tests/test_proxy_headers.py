"""Behind nginx, which headers Django trusts (see USE_PROXY_HEADERS in settings).

nginx's proxy_params forwards Host, X-Real-IP, X-Forwarded-For and
X-Forwarded-Proto. It does not set X-Forwarded-Host, so that header arrives
from the visitor; Django must not read it, or the links in password-reset
and verification emails could be pointed at a host the visitor chose.
"""

from django.core import mail
from django.test import TestCase, override_settings

from accounts.tests.factories import make_user

from .settings_probe import load_settings


class ProxyHeaderSettingsTests(TestCase):
    def test_production_shape_trusts_the_proto_header_but_not_the_host(self):
        settings = load_settings(USE_PROXY_HEADERS="True")
        self.assertEqual(
            settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
        )
        self.assertFalse(getattr(settings, "USE_X_FORWARDED_HOST", False))

    def test_without_the_proxy_nothing_is_trusted(self):
        settings = load_settings(USE_PROXY_HEADERS="False")
        self.assertFalse(hasattr(settings, "SECURE_PROXY_SSL_HEADER"))
        self.assertFalse(getattr(settings, "USE_X_FORWARDED_HOST", False))


@override_settings(ALLOWED_HOSTS=["www.fortkentcinema.com", "evil.example"])
class ForgedForwardedHostTests(TestCase):
    """Even an allowed host in X-Forwarded-Host must not redirect the
    emailed links away from the host nginx actually received."""

    def test_reset_link_uses_the_host_nginx_forwarded(self):
        make_user("ann@example.com", "pw-1-long-enough")
        self.client.post(
            "/password-reset",
            {"email": "ann@example.com"},
            HTTP_HOST="www.fortkentcinema.com",
            HTTP_X_FORWARDED_HOST="evil.example",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("://www.fortkentcinema.com/password-reset/", mail.outbox[0].body)
        self.assertNotIn("evil.example", mail.outbox[0].body)

    def test_verification_link_uses_the_host_nginx_forwarded(self):
        self.client.post(
            "/register",
            {
                "email": "new@example.com",
                "password1": "Brand-new-passphrase-7",
                "password2": "Brand-new-passphrase-7",
            },
            HTTP_HOST="www.fortkentcinema.com",
            HTTP_X_FORWARDED_HOST="evil.example",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("://www.fortkentcinema.com/register/verify/", mail.outbox[0].body)
        self.assertNotIn("evil.example", mail.outbox[0].body)
