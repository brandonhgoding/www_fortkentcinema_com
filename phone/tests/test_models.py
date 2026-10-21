import datetime

from django.test import TestCase
from phone.models import CallLog, Voicemail


class VoicemailCallbackNumberTests(TestCase):
    """Only a real number gets a tel: link. Twilio sends "anonymous", a SIP
    URI, or +266696687 (ANONYMOUS on a keypad) when the caller ID is
    withheld, and none of those can be dialled."""

    def number(self, caller: str) -> str:
        return Voicemail(recording_sid="RE1", caller=caller).callback_number

    def test_an_e164_number_can_be_called_back(self) -> None:
        self.assertEqual(self.number("+12075550100"), "+12075550100")

    def test_withheld_caller_ids_have_no_number(self) -> None:
        for caller in ("anonymous", "+266696687", "sip:alice@example.com", ""):
            with self.subTest(caller=caller):
                self.assertEqual(self.number(caller), "")


class CallLogStrTests(TestCase):
    def test_str_shows_the_eastern_time(self) -> None:
        # 03:30 UTC on 5 October is 11:30 PM EDT on 4 October, which is
        # what the dashboard list shows; admin's inline header should match.
        log = CallLog.objects.create(call_sid="CA1", caller="+12075550100")
        log.started_at = datetime.datetime(2026, 10, 5, 3, 30, tzinfo=datetime.UTC)
        self.assertEqual(str(log), "+12075550100 @ 2026-10-04 23:30")

    def test_str_names_an_unknown_caller(self) -> None:
        log = CallLog(call_sid="CA1", caller="")
        log.started_at = datetime.datetime(2026, 10, 5, 3, 30, tzinfo=datetime.UTC)
        self.assertEqual(str(log), "Unknown caller @ 2026-10-04 23:30")
