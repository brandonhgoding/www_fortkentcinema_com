import re
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.tests.factories import make_user
from phone.models import Voicemail, VoicemailStatus
from phone.recordings import RecordingError
from dashboard.tests.helpers import make_staff

SID = "RE" + "1" * 32
RECORDING_URL = f"https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/{SID}"
CONFIGURED = override_settings(
    TWILIO_ACCOUNT_SID="AC" + "0" * 32, TWILIO_AUTH_TOKEN="tok"
)
UNCONFIGURED = override_settings(TWILIO_ACCOUNT_SID="")


class VoicemailTestCase(TestCase):
    def setUp(self) -> None:
        self.staff = make_staff(
            email="staff@example.com", password="pw"
        )
        self.voicemail = Voicemail.objects.create(
            recording_sid=SID,
            caller="+12075550100",
            recording_url=RECORDING_URL,
            transcript="Are you showing Hamnet on Friday?",
        )

    def login(self) -> None:
        self.client.force_login(self.staff)


class VoicemailListTests(VoicemailTestCase):
    def test_requires_staff(self):
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertNotEqual(response.status_code, 200)

    def test_lists_voicemails_with_transcript(self):
        self.login()
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertContains(response, "+12075550100")
        self.assertContains(response, "Are you showing Hamnet on Friday?")
        self.assertEqual(response.context["new_count"], 1)

    def test_a_real_number_gets_a_tel_link(self):
        self.login()
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertContains(response, 'href="tel:+12075550100"')

    def test_a_withheld_caller_id_is_shown_but_not_linked(self):
        # Twilio sends "anonymous" (or +266696687) when the caller blocks
        # their number; wrapping that in tel: gives staff a dead link.
        self.voicemail.caller = "anonymous"
        self.voicemail.save()
        self.login()
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertContains(response, "anonymous")
        self.assertNotContains(response, "tel:")

    @CONFIGURED
    def test_audio_streams_through_the_dashboard_without_exposing_twilio(self):
        self.login()
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertContains(
            response, reverse("dashboard:voicemail_audio", args=[self.voicemail.pk])
        )
        self.assertNotContains(response, "api.twilio.com")

    @UNCONFIGURED
    def test_without_an_account_sid_the_page_names_the_setting_not_twilio(self):
        # The raw Twilio URL is never put on a page: it is either open to
        # anyone holding it or prompts staff for the account credentials.
        self.login()
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertNotContains(response, "api.twilio.com")
        self.assertContains(response, "TWILIO_ACCOUNT_SID")

    def test_no_transcript_shows_no_pending_label_while_transcription_is_off(self):
        Voicemail.objects.create(recording_sid="RE2")
        self.login()
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertNotContains(response, "Transcript pending")

    @patch("dashboard.voicemail_views.TRANSCRIBE", True)
    def test_pending_and_failed_transcripts_are_labelled(self):
        Voicemail.objects.create(recording_sid="RE2")
        Voicemail.objects.create(recording_sid="RE3", transcription_status="failed")
        self.login()
        response = self.client.get(reverse("dashboard:voicemails"))
        self.assertContains(response, "Transcript pending")
        self.assertContains(response, "Transcript unavailable")

    def test_filter_by_status(self):
        Voicemail.objects.create(
            recording_sid="RE2", caller="+12075550111", status=VoicemailStatus.HANDLED
        )
        self.login()
        response = self.client.get(
            reverse("dashboard:voicemails"), {"status": "HANDLED"}
        )
        self.assertContains(response, "+12075550111")
        self.assertNotContains(response, "+12075550100")

    def test_the_new_count_ignores_the_filter(self):
        Voicemail.objects.create(
            recording_sid="RE2", caller="+12075550111", status=VoicemailStatus.HANDLED
        )
        self.login()
        response = self.client.get(
            reverse("dashboard:voicemails"), {"status": "HANDLED"}
        )
        self.assertEqual(response.context["new_count"], 1)

    def test_the_home_alert_link_lists_only_new_voicemails(self):
        Voicemail.objects.create(
            recording_sid="RE2", caller="+12075550111", status=VoicemailStatus.HANDLED
        )
        self.login()
        response = self.client.get(reverse("dashboard:voicemails") + "?status=NEW")
        self.assertContains(response, "+12075550100")
        self.assertNotContains(response, "+12075550111")

    def test_an_unknown_status_filter_lists_everything(self):
        Voicemail.objects.create(
            recording_sid="RE2", caller="+12075550111", status=VoicemailStatus.HANDLED
        )
        self.login()
        response = self.client.get(reverse("dashboard:voicemails"), {"status": "BOGUS"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+12075550100")
        self.assertContains(response, "+12075550111")

    def test_mark_handled(self):
        self.login()
        self.client.post(
            reverse("dashboard:voicemail_status", args=[self.voicemail.pk]),
            {"status": "HANDLED"},
        )
        self.voicemail.refresh_from_db()
        self.assertEqual(self.voicemail.status, VoicemailStatus.HANDLED)

    def test_invalid_status_is_ignored(self):
        self.login()
        self.client.post(
            reverse("dashboard:voicemail_status", args=[self.voicemail.pk]),
            {"status": "BOGUS"},
        )
        self.voicemail.refresh_from_db()
        self.assertEqual(self.voicemail.status, VoicemailStatus.NEW)

    def test_home_alert_counts_new_voicemails(self):
        Voicemail.objects.create(recording_sid="RE2", status=VoicemailStatus.HANDLED)
        self.login()
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "You have 1 new voicemail")


class VoicemailNotesTests(VoicemailTestCase):
    def notes_url(self) -> str:
        return reverse("dashboard:voicemail_notes", args=[self.voicemail.pk])

    def test_requires_staff(self):
        self.client.post(self.notes_url(), {"notes": "x"})
        self.voicemail.refresh_from_db()
        self.assertEqual(self.voicemail.notes, "")

    def test_saves_and_shows_the_note(self):
        self.login()
        response = self.client.post(
            self.notes_url(), {"notes": "  Called back Tue, wants a rental quote  "}
        )
        self.assertRedirects(response, reverse("dashboard:voicemails"))
        self.voicemail.refresh_from_db()
        self.assertEqual(self.voicemail.notes, "Called back Tue, wants a rental quote")
        page = self.client.get(reverse("dashboard:voicemails"))
        self.assertContains(page, "Called back Tue, wants a rental quote")

    def test_blank_clears_the_note(self):
        self.voicemail.notes = "old"
        self.voicemail.save()
        self.login()
        self.client.post(self.notes_url(), {"notes": ""})
        self.voicemail.refresh_from_db()
        self.assertEqual(self.voicemail.notes, "")


class VoicemailDeleteTests(VoicemailTestCase):
    def delete(self):
        return self.client.post(
            reverse("dashboard:voicemail_delete", args=[self.voicemail.pk])
        )

    @patch("dashboard.voicemail_views.recordings.delete_recording")
    def test_requires_staff(self, delete_recording: Mock):
        self.delete()
        self.assertTrue(Voicemail.objects.exists())
        delete_recording.assert_not_called()

    @CONFIGURED
    @patch("dashboard.voicemail_views.recordings.delete_recording")
    def test_deletes_the_twilio_recording_then_the_row(self, delete_recording: Mock):
        self.login()
        response = self.delete()
        self.assertRedirects(response, reverse("dashboard:voicemails"))
        delete_recording.assert_called_once_with(SID)
        self.assertFalse(Voicemail.objects.exists())

    @CONFIGURED
    @patch(
        "dashboard.voicemail_views.recordings.delete_recording",
        side_effect=RecordingError("Twilio answered 500"),
    )
    def test_twilio_failure_keeps_the_voicemail(self, _: Mock):
        self.login()
        # Staff see "try again"; the reason goes to the log, so a bad token
        # and a Twilio outage can be told apart afterwards.
        with self.assertLogs("dashboard.voicemail_views", "WARNING") as logs:
            response = self.delete()
        self.assertTrue(Voicemail.objects.exists())
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertIn("voicemail was kept", messages[0])
        self.assertIn("Twilio answered 500", logs.output[0])
        self.assertIn(SID, logs.output[0])

    @UNCONFIGURED
    def test_without_an_account_sid_nothing_is_deleted(self):
        # The real delete_recording refuses, so the row survives rather than
        # orphaning a recording in Twilio.
        self.login()
        response = self.delete()
        self.assertTrue(Voicemail.objects.exists())
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertIn("isn't set up", messages[0])

    def test_get_does_not_delete(self):
        self.login()
        self.client.get(reverse("dashboard:voicemail_delete", args=[self.voicemail.pk]))
        self.assertTrue(Voicemail.objects.exists())


def upstream(status: int, body: bytes = b"ID3audio", **headers: str) -> Mock:
    response = Mock(status_code=status, headers=headers)
    response.iter_content.return_value = iter([body])
    return response


@CONFIGURED
class VoicemailAudioTests(VoicemailTestCase):
    def audio_url(self) -> str:
        return reverse("dashboard:voicemail_audio", args=[self.voicemail.pk])

    @patch("dashboard.voicemail_views.recordings.open_recording")
    def test_requires_staff(self, open_recording: Mock):
        self.assertNotEqual(self.client.get(self.audio_url()).status_code, 200)
        open_recording.assert_not_called()

    @patch("dashboard.voicemail_views.recordings.open_recording")
    def test_streams_the_mp3(self, open_recording: Mock):
        source = upstream(200, **{"Content-Length": "8", "Accept-Ranges": "bytes"})
        open_recording.return_value = source
        self.login()
        response = self.client.get(self.audio_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "audio/mpeg")
        self.assertEqual(response["Content-Length"], "8")
        self.assertEqual(response["Accept-Ranges"], "bytes")
        self.assertEqual(b"".join(response.streaming_content), b"ID3audio")
        source.close.assert_called_once()

    @patch("dashboard.voicemail_views.recordings.open_recording")
    def test_passes_range_through_so_the_player_can_seek(self, open_recording: Mock):
        open_recording.return_value = upstream(206, **{"Content-Range": "bytes 4-7/8"})
        self.login()
        response = self.client.get(self.audio_url(), HTTP_RANGE="bytes=4-")
        open_recording.assert_called_once_with(SID, "bytes=4-")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], "bytes 4-7/8")

    @patch("dashboard.voicemail_views.recordings.open_recording")
    def test_without_a_range_the_whole_file_is_asked_for(self, open_recording: Mock):
        open_recording.return_value = upstream(200)
        self.login()
        self.client.get(self.audio_url())
        open_recording.assert_called_once_with(SID, "")

    @patch("dashboard.voicemail_views.recordings.open_recording")
    def test_audio_is_cached_only_by_the_browser_that_fetched_it(
        self, open_recording: Mock
    ):
        open_recording.return_value = upstream(200)
        self.login()
        response = self.client.get(self.audio_url())
        self.assertEqual(response["Cache-Control"], "private, max-age=3600")

    @patch("dashboard.voicemail_views.recordings.open_recording")
    def test_missing_recording_is_404(self, open_recording: Mock):
        source = upstream(404)
        open_recording.return_value = source
        self.login()
        self.assertEqual(self.client.get(self.audio_url()).status_code, 404)
        source.close.assert_called_once()

    @patch("dashboard.voicemail_views.recordings.open_recording")
    def test_a_twilio_outage_is_502_logged_and_closed(self, open_recording: Mock):
        source = upstream(503)
        open_recording.return_value = source
        self.login()
        with (
            self.assertLogs("django.request", "ERROR"),
            self.assertLogs("dashboard.voicemail_views", "WARNING") as logs,
        ):
            response = self.client.get(self.audio_url())
        self.assertEqual(response.status_code, 502)
        self.assertIn("503", logs.output[0])
        source.close.assert_called_once()

    @patch("dashboard.voicemail_views.recordings.open_recording")
    def test_an_unsatisfiable_range_is_passed_to_the_player(self, open_recording: Mock):
        # The browser asked past the end of the file; 416 with Content-Range
        # tells it the real size, where a 502 would just stop playback.
        open_recording.return_value = upstream(416, **{"Content-Range": "bytes */8"})
        self.login()
        response = self.client.get(self.audio_url(), HTTP_RANGE="bytes=99-")
        self.assertEqual(response.status_code, 416)
        self.assertEqual(response["Content-Range"], "bytes */8")

    @patch("dashboard.voicemail_views.recordings.open_recording")
    def test_a_twilio_error_status_is_502_and_logged(self, open_recording: Mock):
        self.login()
        open_recording.return_value = upstream(401)
        # A 502 is logged as an ERROR (and emailed to ADMINS in production)
        # by django.request; the view adds the reason at WARNING.
        with (
            self.assertLogs("django.request", "ERROR"),
            self.assertLogs("dashboard.voicemail_views", "WARNING") as logs,
        ):
            response = self.client.get(self.audio_url())
        self.assertEqual(response.status_code, 502)
        self.assertIn("401", logs.output[0])
        self.assertIn(SID, logs.output[0])

    @patch(
        "dashboard.voicemail_views.recordings.open_recording",
        side_effect=RecordingError("connection refused"),
    )
    def test_a_recording_error_is_502_and_logged(self, _: Mock):
        self.login()
        with (
            self.assertLogs("django.request", "ERROR"),
            self.assertLogs("dashboard.voicemail_views", "WARNING") as logs,
        ):
            response = self.client.get(self.audio_url())
        self.assertEqual(response.status_code, 502)
        self.assertIn("connection refused", logs.output[0])


class VoicemailPermissionTests(VoicemailTestCase):
    """Every voicemail route, three ways in: anonymous is sent to log in,
    a signed-in non-staff user is refused, and the POST-only routes refuse
    a GET even from staff."""

    def routes(self) -> list[tuple[str, str]]:
        pk = self.voicemail.pk
        return [
            ("get", reverse("dashboard:voicemails")),
            ("post", reverse("dashboard:voicemail_status", args=[pk])),
            ("post", reverse("dashboard:voicemail_notes", args=[pk])),
            ("post", reverse("dashboard:voicemail_delete", args=[pk])),
            ("get", reverse("dashboard:voicemail_audio", args=[pk])),
        ]

    @patch("dashboard.voicemail_views.recordings.open_recording")
    @patch("dashboard.voicemail_views.recordings.delete_recording")
    def test_anonymous_is_redirected_to_login(self, *_: Mock):
        for method, url in self.routes():
            with self.subTest(url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response["Location"])

    @patch("dashboard.voicemail_views.recordings.open_recording")
    @patch("dashboard.voicemail_views.recordings.delete_recording")
    def test_signed_in_non_staff_is_refused(self, *_: Mock):
        self.client.force_login(
            make_user(email="member@example.com", password="pw")
        )
        for method, url in self.routes():
            with self.subTest(url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 403)
        self.voicemail.refresh_from_db()
        self.assertEqual(self.voicemail.status, VoicemailStatus.NEW)

    def test_post_only_routes_refuse_get_even_from_staff(self):
        self.login()
        for method, url in self.routes():
            if method == "post":
                with self.subTest(url):
                    self.assertEqual(self.client.get(url).status_code, 405)


class SidebarBadgeTests(VoicemailTestCase):
    def sidebar_link(self) -> str:
        self.login()
        html = self.client.get(reverse("dashboard:engagements")).content.decode()
        match = re.search(r'<a href="/dashboard/voicemails".*?</a>', html, re.S)
        assert match
        return match.group(0)

    def test_shows_the_new_count_on_every_page(self):
        Voicemail.objects.create(recording_sid="RE2")
        Voicemail.objects.create(recording_sid="RE3", status=VoicemailStatus.HANDLED)
        self.assertIn(
            '<span class="sidebarBadge" aria-label="2 new">2</span>',
            self.sidebar_link(),
        )

    def test_hidden_when_nothing_is_new(self):
        Voicemail.objects.update(status=VoicemailStatus.HANDLED)
        self.assertNotIn("sidebarBadge", self.sidebar_link())


class VoicemailViewOnlyTests(VoicemailTestCase):
    @CONFIGURED
    def test_view_only_user_sees_player_without_forms(self):
        self.voicemail.notes = "Called back Tuesday"
        self.voicemail.save(update_fields=["notes"])
        make_staff(
            email="viewer@example.com", password="pw", perms=("phone.view_voicemail",)
        )
        self.client.login(username="viewer@example.com", password="pw")
        response = self.client.get(reverse("dashboard:voicemails"))
        pk = self.voicemail.pk
        self.assertContains(
            response, reverse("dashboard:voicemail_audio", args=[pk])
        )
        for name in ("voicemail_status", "voicemail_notes", "voicemail_delete"):
            with self.subTest(name):
                self.assertNotContains(
                    response, reverse(f"dashboard:{name}", args=[pk])
                )
        self.assertContains(response, "Called back Tuesday")
        self.assertContains(
            response, self.voicemail.get_status_display() + "\n"
        )
