from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from phone.admin import VoicemailAdmin
from phone.models import CallLog, Voicemail

SID = "RE" + "1" * 32
RECORDING_URL = f"https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/{SID}"


class VoicemailAdminTests(TestCase):
    """Playback goes through the dashboard proxy; the raw Twilio URL is
    never rendered, in admin any more than on the dashboard."""

    def setUp(self) -> None:
        self.client.force_login(
            get_user_model().objects.create_superuser("admin", password="pw")
        )
        self.voicemail = Voicemail.objects.create(
            recording_sid=SID, caller="+12075550100", recording_url=RECORDING_URL
        )
        self.change_url = reverse(
            "admin:phone_voicemail_change", args=[self.voicemail.pk]
        )

    @override_settings(TWILIO_ACCOUNT_SID="AC" + "0" * 32, TWILIO_AUTH_TOKEN="tok")
    def test_recording_plays_through_the_dashboard(self) -> None:
        response = self.client.get(self.change_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, reverse("dashboard:voicemail_audio", args=[self.voicemail.pk])
        )
        self.assertNotContains(response, "api.twilio.com")

    @override_settings(TWILIO_ACCOUNT_SID="")
    def test_without_an_account_sid_there_is_no_link(self) -> None:
        response = self.client.get(self.change_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "api.twilio.com")
        self.assertNotContains(response, "Listen")

    def test_changelist_renders(self) -> None:
        response = self.client.get(reverse("admin:phone_voicemail_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "api.twilio.com")


class VoicemailExcerptTests(TestCase):
    def excerpt(self, transcript: str) -> str:
        model_admin = VoicemailAdmin(Voicemail, admin.site)
        return model_admin.excerpt(Voicemail(recording_sid=SID, transcript=transcript))

    def test_a_short_transcript_is_shown_whole(self) -> None:
        self.assertEqual(self.excerpt("Call me back"), "Call me back")

    def test_a_long_transcript_is_cut_at_eighty_characters(self) -> None:
        self.assertEqual(self.excerpt("x" * 81), "x" * 80 + "…")
        self.assertEqual(self.excerpt("x" * 80), "x" * 80)

    def test_no_transcript_is_a_dash(self) -> None:
        self.assertEqual(self.excerpt(""), "—")


class CallLogAdminTests(TestCase):
    def setUp(self) -> None:
        self.client.force_login(
            get_user_model().objects.create_superuser("admin", password="pw")
        )
        self.log = CallLog.objects.create(
            call_sid="CA1", caller="+12075550100", choices=["1", "3"]
        )

    def test_changelist_shows_the_menu_choices(self) -> None:
        response = self.client.get(reverse("admin:phone_calllog_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1, 3")

    def test_change_page_renders_with_the_voicemail_inline(self) -> None:
        Voicemail.objects.create(recording_sid=SID, call=self.log)
        response = self.client.get(
            reverse("admin:phone_calllog_change", args=[self.log.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Voicemails")
