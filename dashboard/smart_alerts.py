from __future__ import annotations

import datetime


def build_smart_alerts(engagements, tomorrow_showtimes_count: int,
                       today: datetime.date,
                       new_inquiries: int = 0,
                       new_voicemails: int = 0,
                       square_pull_status: str | None = None,
                       square_sync_failures: int = 0) -> list[dict]:
    """Server-side port of the React useSmartAlerts hook.

    engagements: iterable of Engagement (all engagements).
    tomorrow_showtimes_count: number of showtimes scheduled for tomorrow.
    today: local date.
    """
    engagements = list(engagements)
    alerts: list[dict] = []

    if tomorrow_showtimes_count == 0 and engagements:
        alerts.append({
            "id": "no-showtimes-tomorrow", "type": "warning",
            "message": "No showtimes scheduled for tomorrow",
        })

    two_days = today + datetime.timedelta(days=2)
    for e in engagements:
        if e.status != "CONFIRMED":
            continue
        if today <= e.end_date <= two_days:
            days_left = (e.end_date - today).days
            unit = "day" if days_left == 1 else "days"
            alerts.append({
                "id": f"ending-soon-{e.id}", "type": "info",
                "message": f"{e.display_title} ends in {days_left} {unit}",
            })

    draft_count = sum(1 for e in engagements if e.status == "DRAFT")
    if draft_count > 0:
        unit = "engagement" if draft_count == 1 else "engagements"
        alerts.append({
            "id": "draft-engagements", "type": "info",
            "message": f"You have {draft_count} draft {unit} waiting to be confirmed",
        })

    if new_inquiries > 0:
        unit = "inquiry" if new_inquiries == 1 else "inquiries"
        alerts.append({
            "id": "new-sponsorship-inquiries", "type": "info",
            "message": f"You have {new_inquiries} new sponsorship {unit}",
        })

    if new_voicemails > 0:
        unit = "voicemail" if new_voicemails == 1 else "voicemails"
        alerts.append({
            "id": "new-voicemails", "type": "info",
            "message": f"You have {new_voicemails} new {unit}",
        })

    if square_pull_status == "FAILED":
        alerts.append({
            "id": "square-pull-failed", "type": "warning",
            "message": "Yesterday's Square sales pull failed",
        })
    elif square_pull_status == "MISSING":
        alerts.append({
            "id": "square-pull-missing", "type": "warning",
            "message": "No Square sales pull ran yesterday",
        })

    if square_sync_failures > 0:
        unit = "run" if square_sync_failures == 1 else "runs"
        alerts.append({
            "id": "square-sync-failed", "type": "warning",
            "message": f"{square_sync_failures} {unit} failed to sync to Square",
        })

    return alerts
