"""Staff surface for phone-line voicemails.

Nothing here sends mail either — see inquiry_views. This list plus the NEW
count on the dashboard home is how a message reaches a human.
"""

from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from phone.models import Voicemail, VoicemailStatus

from .mixins import StaffRequiredMixin


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
