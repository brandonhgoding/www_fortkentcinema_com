"""Staff surface for phone-line voicemails.

Nothing here sends mail. This list plus the NEW
count on the dashboard home and the sidebar badge is how a message reaches
a human.
"""

import logging
from collections.abc import Iterator

from django.contrib import messages
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from phone import recordings
from phone.models import Voicemail, VoicemailStatus
from phone.views import TRANSCRIBE

from .mixins import StaffRequiredMixin

logger = logging.getLogger(__name__)

# Response headers worth passing from Twilio to the browser's audio player.
AUDIO_HEADERS = ("Content-Length", "Content-Range", "Accept-Ranges")


class VoicemailListView(StaffRequiredMixin, View):
    permission_required = "phone.view_voicemail"

    def get(self, request):
        voicemails = Voicemail.objects.all()

        status = (request.GET.get("status") or "").strip()
        if status in VoicemailStatus.values:
            voicemails = voicemails.filter(status=status)

        return render(
            request,
            "dashboard/voicemails.html",
            {
                "voicemails": voicemails,
                "new_count": Voicemail.objects.filter(
                    status=VoicemailStatus.NEW
                ).count(),
                "statuses": VoicemailStatus.choices,
                "selected_status": status,
                # Without an account SID, fall back to linking Twilio directly.
                "stream_audio": recordings.is_configured(),
                # With transcription off, a missing transcript isn't "pending".
                "transcribing": TRANSCRIBE,
            },
        )


class VoicemailStatusView(StaffRequiredMixin, View):
    permission_required = "phone.change_voicemail"

    def post(self, request, pk: int):
        voicemail = get_object_or_404(Voicemail, pk=pk)
        status = (request.POST.get("status") or "").strip()
        if status in VoicemailStatus.values:
            voicemail.status = status
            voicemail.save(update_fields=["status"])
        return redirect("dashboard:voicemails")


class VoicemailNotesView(StaffRequiredMixin, View):
    permission_required = "phone.change_voicemail"

    def post(self, request, pk: int):
        voicemail = get_object_or_404(Voicemail, pk=pk)
        voicemail.notes = (request.POST.get("notes") or "").strip()
        voicemail.save(update_fields=["notes"])
        messages.success(request, "Note saved")
        return redirect("dashboard:voicemails")


class VoicemailDeleteView(StaffRequiredMixin, View):
    """Deletes the recording from Twilio first, then the row.

    In that order on purpose: if Twilio fails, the row survives and the
    delete can be retried. Deleting the row first would orphan a recording
    we'd keep paying to store with no way left to find it.
    """

    permission_required = "phone.delete_voicemail"

    def post(self, request, pk: int):
        voicemail = get_object_or_404(Voicemail, pk=pk)
        if not recordings.is_configured():
            # Retrying can't help here, so don't ask staff to.
            messages.error(
                request,
                "Twilio isn't set up on this server, so the recording can't "
                "be deleted and the voicemail was kept.",
            )
            return redirect("dashboard:voicemails")
        try:
            recordings.delete_recording(voicemail.recording_sid)
        except recordings.RecordingError as exc:
            # Staff see "try again"; the reason lives here, so a bad token
            # and a Twilio outage can be told apart afterwards.
            logger.warning(
                "Couldn't delete recording %s from Twilio: %s",
                voicemail.recording_sid,
                exc,
            )
            messages.error(
                request,
                "Couldn't delete the recording from Twilio, so the voicemail "
                "was kept. Please try again.",
            )
            return redirect("dashboard:voicemails")
        voicemail.delete()
        messages.success(request, "Voicemail deleted")
        return redirect("dashboard:voicemails")


class VoicemailAudioView(StaffRequiredMixin, View):
    permission_required = "phone.view_voicemail"

    def get(self, request, pk: int) -> HttpResponse:
        voicemail = get_object_or_404(Voicemail, pk=pk)
        try:
            upstream = recordings.open_recording(
                voicemail.recording_sid, request.headers.get("Range", "")
            )
        except recordings.RecordingError as exc:
            logger.warning(
                "Couldn't fetch recording %s from Twilio: %s",
                voicemail.recording_sid,
                exc,
            )
            return HttpResponse("Recording unavailable", status=502)

        if upstream.status_code == 404:
            upstream.close()
            raise Http404("Recording not found")
        # 416 goes through too: its Content-Range tells the player the
        # file's real size, where a 502 would just stop playback.
        if upstream.status_code not in (200, 206, 416):
            upstream.close()
            logger.warning(
                "Twilio answered %s for recording %s",
                upstream.status_code,
                voicemail.recording_sid,
            )
            return HttpResponse("Recording unavailable", status=502)

        def chunks() -> Iterator[bytes]:
            try:
                yield from upstream.iter_content(chunk_size=64 * 1024)
            finally:
                upstream.close()

        response = StreamingHttpResponse(
            chunks(), status=upstream.status_code, content_type="audio/mpeg"
        )
        for header in AUDIO_HEADERS:
            if header in upstream.headers:
                response[header] = upstream.headers[header]
        response["Cache-Control"] = "private, max-age=3600"
        return response
