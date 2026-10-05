"""Staff surface for phone-line voicemails.

Nothing here sends mail either — see inquiry_views. This list plus the NEW
count on the dashboard home and the sidebar badge is how a message reaches
a human.
"""

from collections.abc import Iterator

from django.contrib import messages
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from phone import recordings
from phone.models import Voicemail, VoicemailStatus

from .mixins import StaffRequiredMixin

# Response headers worth passing from Twilio to the browser's audio player.
AUDIO_HEADERS = ("Content-Length", "Content-Range", "Accept-Ranges")


class VoicemailListView(StaffRequiredMixin, View):
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
            },
        )


class VoicemailStatusView(StaffRequiredMixin, View):
    def post(self, request, pk: int):
        voicemail = get_object_or_404(Voicemail, pk=pk)
        status = (request.POST.get("status") or "").strip()
        if status in VoicemailStatus.values:
            voicemail.status = status
            voicemail.save(update_fields=["status"])
        return redirect("dashboard:voicemails")


class VoicemailNotesView(StaffRequiredMixin, View):
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

    def post(self, request, pk: int):
        voicemail = get_object_or_404(Voicemail, pk=pk)
        try:
            recordings.delete_recording(voicemail.recording_sid)
        except recordings.RecordingError:
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
    def get(self, request, pk: int) -> HttpResponse:
        voicemail = get_object_or_404(Voicemail, pk=pk)
        try:
            upstream = recordings.open_recording(
                voicemail.recording_sid, request.headers.get("Range", "")
            )
        except recordings.RecordingError:
            return HttpResponse("Recording unavailable", status=502)

        if upstream.status_code == 404:
            upstream.close()
            raise Http404("Recording not found")
        if upstream.status_code not in (200, 206):
            upstream.close()
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
