from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings
from phone import recordings

SID = "RE" + "a" * 32
ACCOUNT = "AC" + "b" * 32
BASE = f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT}/Recordings/{SID}"


@override_settings(TWILIO_ACCOUNT_SID=ACCOUNT, TWILIO_AUTH_TOKEN="tok")
class RecordingsTests(SimpleTestCase):
    @patch("phone.recordings.requests.get")
    def test_open_streams_the_mp3_with_basic_auth_and_range(self, get: Mock) -> None:
        recordings.open_recording(SID, "bytes=100-")
        get.assert_called_once_with(
            BASE + ".mp3",
            auth=(ACCOUNT, "tok"),
            headers={"Range": "bytes=100-"},
            stream=True,
            timeout=(5, 30),
        )

    @patch("phone.recordings.requests.delete")
    def test_delete_succeeds_on_204_and_404(self, delete: Mock) -> None:
        for status in (204, 404):
            delete.return_value = Mock(status_code=status)
            recordings.delete_recording(SID)
        delete.assert_called_with(BASE + ".json", auth=(ACCOUNT, "tok"), timeout=10)

    @patch("phone.recordings.requests.delete", return_value=Mock(status_code=500))
    def test_delete_raises_on_other_statuses(self, _: Mock) -> None:
        with self.assertRaises(recordings.RecordingError):
            recordings.delete_recording(SID)

    @patch(
        "phone.recordings.requests.delete",
        side_effect=requests.ConnectionError("down"),
    )
    def test_network_errors_become_recording_errors(self, _: Mock) -> None:
        with self.assertRaises(recordings.RecordingError):
            recordings.delete_recording(SID)

    @patch("phone.recordings.requests.get")
    def test_rejects_a_malformed_sid_before_sending_credentials(
        self, get: Mock
    ) -> None:
        for bad in ("", "RE123", "../Calls/CA1", "RE" + "a" * 31 + "/"):
            with self.subTest(bad), self.assertRaises(recordings.RecordingError):
                recordings.open_recording(bad)
        get.assert_not_called()

    @override_settings(TWILIO_ACCOUNT_SID="")
    @patch("phone.recordings.requests.delete")
    def test_refuses_without_an_account_sid(self, delete: Mock) -> None:
        self.assertFalse(recordings.is_configured())
        with self.assertRaises(recordings.RecordingError):
            recordings.delete_recording(SID)
        delete.assert_not_called()
