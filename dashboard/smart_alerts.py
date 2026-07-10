from __future__ import annotations

import datetime


def build_smart_alerts(engagements, tomorrow_showtimes_count: int,
                       today: datetime.date) -> list[dict]:
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

    return alerts
