import re
from unittest.mock import patch
from xml.sax.saxutils import escape

from django.test import TestCase, override_settings
from django.urls import reverse
from phone.models import CallLog, Voicemail, VoicemailStatus
from phone.speech import hours_and_prices_speech
from phone.views import VOICE

from .helpers import TOKEN, post_signed

CALL = {"CallSid": "CA123", "From": "+12075550100", "To": "+12075550199"}


@override_settings(TWILIO_AUTH_TOKEN=TOKEN, TWILIO_WEBHOOK_BASE_URL="")
class PhoneTestCase(TestCase):
    def call(
        self, name: str, data: dict[str, str] | None = None, query: str = ""
    ) -> str:
        path = reverse(f"phone:{name}") + query
        response = post_signed(self.client, path, {**CALL, **(data or {})})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/xml")
        return response.content.decode()

    def press(self, digits: str, attempt: int = 1) -> str:
        data = {"Digits": digits} if digits else {}
        return self.call("menu", data, query=f"?attempt={attempt}")


class VoiceTests(PhoneTestCase):
    def test_every_spoken_line_uses_the_configured_voice(self) -> None:
        self.call("incoming_call")
        twimls = [
            self.call("incoming_call"),
            *(self.press(d) for d in ("1", "2", "3", "9")),
            self.press("", attempt=2),
            self.call("voicemail_recorded", RECORDING),
        ]
        for twiml in twimls:
            says = re.findall(r"<Say[^>]*>", twiml)
            self.assertTrue(says)
            for say in says:
                self.assertIn(f'voice="{VOICE}"', say)


class IncomingCallTests(PhoneTestCase):
    def test_greets_and_gathers_one_digit(self) -> None:
        twiml = self.call("incoming_call")
        self.assertIn("Thanks for calling Fort Kent Cinema.", twiml)
        self.assertIn('<Gather action="/phone/menu/?attempt=1" numDigits="1"', twiml)
        self.assertIn("Press 1 for today's showtimes", twiml)
        # No input falls through to the menu as a miss.
        self.assertIn("<Redirect>/phone/menu/?attempt=1</Redirect>", twiml)

    def test_logs_the_call(self) -> None:
        self.call("incoming_call")
        log = CallLog.objects.get()
        self.assertEqual(
            (log.call_sid, log.caller, log.called, log.choices),
            ("CA123", "+12075550100", "+12075550199", []),
        )


class MenuTests(PhoneTestCase):
    def setUp(self) -> None:
        self.call("incoming_call")

    @patch("phone.views.showtimes_speech", return_value="Today's showtimes: Hamnet.")
    def test_1_reads_showtimes_then_offers_the_menu_once_more(self, _: object) -> None:
        twiml = self.press("1")
        self.assertIn("Today's showtimes: Hamnet.", twiml)
        self.assertIn('action="/phone/menu/?attempt=2"', twiml)

    def test_2_reads_hours_and_prices(self) -> None:
        self.assertIn(escape(hours_and_prices_speech()), self.press("2"))

    def test_3_records_a_voicemail_of_at_most_two_minutes(self) -> None:
        twiml = self.press("3")
        self.assertIn("after the beep", twiml)
        self.assertIn('action="/phone/voicemail/recorded/"', twiml)
        self.assertIn('maxLength="120"', twiml)
        self.assertIn("<Hangup />", twiml)

    def test_3_asks_twilio_to_report_the_recording_when_it_is_ready(self) -> None:
        twiml = self.press("3")
        self.assertIn('recordingStatusCallback="/phone/voicemail/status/"', twiml)

    def test_3_does_not_pay_for_transcription_by_default(self) -> None:
        twiml = self.press("3")
        self.assertNotIn("transcribe", twiml)

    @patch("phone.views.TRANSCRIBE", True)
    def test_3_transcribes_when_switched_on(self) -> None:
        twiml = self.press("3")
        self.assertIn('transcribe="true"', twiml)
        self.assertIn('transcribeCallback="/phone/voicemail/transcribed/"', twiml)

    def test_invalid_digit_repeats_the_menu_once(self) -> None:
        twiml = self.press("9")
        self.assertIn("Sorry, that's not an option.", twiml)
        self.assertIn('action="/phone/menu/?attempt=2"', twiml)

    def test_no_input_repeats_the_menu_once(self) -> None:
        twiml = self.press("")
        self.assertIn("Sorry, I didn't catch that.", twiml)
        self.assertIn('action="/phone/menu/?attempt=2"', twiml)

    def test_second_miss_says_goodbye_and_hangs_up(self) -> None:
        for digits in ("", "9"):
            with self.subTest(digits=digits):
                twiml = self.press(digits, attempt=2)
                self.assertIn("Goodbye.", twiml)
                self.assertIn("<Hangup />", twiml)
                self.assertNotIn("<Gather", twiml)

    def test_tampered_attempt_is_clamped(self) -> None:
        self.assertIn("<Hangup />", self.press("", attempt=99))
        self.assertIn("Sorry", self.call("menu", query="?attempt=nope"))

    def test_choices_are_logged_in_order(self) -> None:
        self.press("9")
        self.press("", attempt=2)
        self.assertEqual(CallLog.objects.get().choices, ["9", "none"])

    def test_menu_without_a_logged_call_still_logs(self) -> None:
        CallLog.objects.all().delete()
        self.press("2")
        self.assertEqual(CallLog.objects.get().choices, ["2"])


RECORDING = {
    "RecordingSid": "RE456",
    "RecordingUrl": "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/RE456",
    "RecordingDuration": "42",
}


class VoicemailTests(PhoneTestCase):
    def setUp(self) -> None:
        self.call("incoming_call")

    def test_recording_saves_a_new_voicemail_and_hangs_up(self) -> None:
        twiml = self.call("voicemail_recorded", RECORDING)
        self.assertIn("we got your message", twiml)
        self.assertIn("<Hangup />", twiml)

        voicemail = Voicemail.objects.get()
        self.assertEqual(voicemail.caller, "+12075550100")
        self.assertEqual(voicemail.recording_url, RECORDING["RecordingUrl"])
        self.assertEqual(voicemail.duration_seconds, 42)
        self.assertEqual(voicemail.call, CallLog.objects.get())
        self.assertEqual(voicemail.status, VoicemailStatus.NEW)
        self.assertEqual(voicemail.transcript, "")
        self.assertIsNotNone(voicemail.created_at)

    def test_transcript_is_added_to_the_voicemail(self) -> None:
        self.call("voicemail_recorded", RECORDING)
        self.call(
            "voicemail_transcribed",
            {
                **RECORDING,
                "TranscriptionText": "Do you have a showing Friday?",
                "TranscriptionStatus": "completed",
            },
        )
        voicemail = Voicemail.objects.get()
        self.assertEqual(voicemail.transcript, "Do you have a showing Friday?")
        self.assertEqual(voicemail.transcription_status, "completed")
        self.assertEqual(voicemail.duration_seconds, 42)

    def test_transcript_arriving_first_still_saves_the_voicemail(self) -> None:
        self.call(
            "voicemail_transcribed",
            {
                **RECORDING,
                "TranscriptionText": "Hi",
                "TranscriptionStatus": "completed",
            },
        )
        self.call("voicemail_recorded", RECORDING)
        voicemail = Voicemail.objects.get()
        self.assertEqual(
            (voicemail.transcript, voicemail.recording_url, voicemail.caller),
            ("Hi", RECORDING["RecordingUrl"], "+12075550100"),
        )

    def test_failed_transcription_is_recorded(self) -> None:
        self.call("voicemail_recorded", RECORDING)
        self.call(
            "voicemail_transcribed", {**RECORDING, "TranscriptionStatus": "failed"}
        )
        self.assertEqual(Voicemail.objects.get().transcription_status, "failed")

    def test_no_recording_saves_nothing_and_says_so(self) -> None:
        with self.assertLogs("phone.views", "ERROR"):
            twiml = self.call("voicemail_recorded")
        self.assertFalse(Voicemail.objects.exists())
        self.assertIn("didn't get your message", twiml)
        self.assertNotIn("we got your message", twiml)

    def test_action_without_a_sid_takes_it_from_the_recording_url(self) -> None:
        sid = "RE" + "a" * 32
        url = f"https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/{sid}"
        twiml = self.call(
            "voicemail_recorded", {"RecordingUrl": url, "RecordingDuration": "7"}
        )
        self.assertIn("we got your message", twiml)
        voicemail = Voicemail.objects.get()
        self.assertEqual(
            (voicemail.recording_sid, voicemail.duration_seconds), (sid, 7)
        )

    def test_a_malformed_sid_in_the_url_is_not_trusted(self) -> None:
        url = "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/not-a-sid"
        with self.assertLogs("phone.views", "ERROR"):
            self.call("voicemail_recorded", {"RecordingUrl": url})
        self.assertFalse(Voicemail.objects.exists())

    def test_repeated_action_without_a_duration_keeps_the_stored_one(self) -> None:
        self.call("voicemail_recorded", RECORDING)
        self.call("voicemail_recorded", {**RECORDING, "RecordingDuration": ""})
        self.assertEqual(Voicemail.objects.get().duration_seconds, 42)

    def status_callback(self, **extra: str) -> None:
        # Twilio's recordingStatusCallback carries the recording and call
        # SIDs but not From: the caller has to come from the CallLog.
        response = post_signed(
            self.client,
            reverse("phone:voicemail_status"),
            {
                "CallSid": CALL["CallSid"],
                **RECORDING,
                "RecordingStatus": "completed",
                **extra,
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_status_callback_saves_a_voicemail_the_action_lost(self) -> None:
        self.status_callback()
        voicemail = Voicemail.objects.get()
        self.assertEqual(voicemail.caller, "+12075550100")
        self.assertEqual(voicemail.call, CallLog.objects.get())
        self.assertEqual(voicemail.recording_url, RECORDING["RecordingUrl"])
        self.assertEqual(voicemail.duration_seconds, 42)
        self.assertEqual(voicemail.status, VoicemailStatus.NEW)

    def test_status_callback_after_the_action_keeps_staff_changes(self) -> None:
        self.call("voicemail_recorded", RECORDING)
        Voicemail.objects.update(status=VoicemailStatus.HANDLED, notes="Called back")
        self.status_callback(RecordingDuration="43")
        voicemail = Voicemail.objects.get()
        self.assertEqual(
            (voicemail.status, voicemail.notes, voicemail.duration_seconds),
            (VoicemailStatus.HANDLED, "Called back", 43),
        )

    def test_status_callback_ignores_a_recording_that_is_not_complete(self) -> None:
        for status in ("in-progress", "absent", "failed"):
            with self.subTest(status):
                self.status_callback(RecordingStatus=status)
                self.assertFalse(Voicemail.objects.exists())

    def test_audio_url_is_mp3(self) -> None:
        self.call("voicemail_recorded", RECORDING)
        self.assertEqual(
            Voicemail.objects.get().audio_url, RECORDING["RecordingUrl"] + ".mp3"
        )
