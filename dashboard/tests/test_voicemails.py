from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from phone.models import Voicemail, VoicemailStatus


class VoicemailListTests(TestCase):
    def setUp(self) -> None:
        self.staff = get_user_model().objects.create_user(
            username="staff", password="pw", is_staff=True
        )
        self.voicemail = Voicemail.objects.create(
            recording_sid="RE1",
            caller="+12075550100",
            recording_url="https://api.twilio.com/Recordings/RE1",
            transcript="Are you showing Hamnet on Friday?",
        )

    def test_requires_staff(self):
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertNotEqual(response.status_code, 200)

    def test_lists_voicemails_with_transcript_and_audio(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertContains(response, "+12075550100")
        self.assertContains(response, "Are you showing Hamnet on Friday?")
        self.assertContains(response, "https://api.twilio.com/Recordings/RE1.mp3")
        self.assertEqual(response.context["new_count"], 1)

    def test_pending_and_failed_transcripts_are_labelled(self):
        Voicemail.objects.create(recording_sid="RE2")
        Voicemail.objects.create(recording_sid="RE3", transcription_status="failed")
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertContains(response, "Transcript pending")
        self.assertContains(response, "Transcript unavailable")

    def test_filter_by_status(self):
        Voicemail.objects.create(
            recording_sid="RE2", caller="+12075550111", status=VoicemailStatus.HANDLED
        )
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("dashboard:voicemails"), {"status": "HANDLED"}
        )
        self.assertContains(response, "+12075550111")
        self.assertNotContains(response, "+12075550100")

    def test_mark_handled(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("dashboard:voicemail_status", args=[self.voicemail.pk]),
            {"status": "HANDLED"},
        )
        self.voicemail.refresh_from_db()
        self.assertEqual(self.voicemail.status, VoicemailStatus.HANDLED)

    def test_invalid_status_is_ignored(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("dashboard:voicemail_status", args=[self.voicemail.pk]),
            {"status": "BOGUS"},
        )
        self.voicemail.refresh_from_db()
        self.assertEqual(self.voicemail.status, VoicemailStatus.NEW)

    def test_home_alert_counts_new_voicemails(self):
        Voicemail.objects.create(recording_sid="RE2", status=VoicemailStatus.HANDLED)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "You have 1 new voicemail")
