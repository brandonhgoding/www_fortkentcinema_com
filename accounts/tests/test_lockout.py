from django.test import RequestFactory, SimpleTestCase

from accounts.lockout import lockout_username


class LockoutUsernameTests(SimpleTestCase):
    def test_lockout_username_strips_and_lowercases(self) -> None:
        request = RequestFactory().post("/login")
        self.assertEqual(
            lockout_username(request, credentials={"username": " A@X.com "}),
            "a@x.com",
        )
        request = RequestFactory().post("/login", {"username": " B@X.com"})
        self.assertEqual(lockout_username(request, credentials=None), "b@x.com")
        request = RequestFactory().post("/login")
        self.assertEqual(lockout_username(request, credentials=None), "")
