"""Calls from this app *to* Twilio's REST API, for voicemail recordings.

Playback goes through the dashboard rather than linking to Twilio, so it
works when the account requires HTTP auth on media and recording URLs never
reach any page: the dashboard and the admin both link here. URLs are built
from our own account SID and a validated recording SID — never from the
stored recording_url — so credentials can only ever be sent to api.twilio.com.
"""

import re

import requests
from django.conf import settings

API = "https://api.twilio.com/2010-04-01"
RECORDING_SID = re.compile(r"^RE[0-9a-f]{32}$")


class RecordingError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN)


def _url(recording_sid: str, extension: str) -> str:
    if not is_configured():
        raise RecordingError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set.")
    if not RECORDING_SID.match(recording_sid):
        raise RecordingError(f"Not a recording SID: {recording_sid!r}")
    account = settings.TWILIO_ACCOUNT_SID
    return f"{API}/Accounts/{account}/Recordings/{recording_sid}{extension}"


def _auth() -> tuple[str, str]:
    return (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def open_recording(recording_sid: str, range_header: str = "") -> requests.Response:
    """Start streaming the MP3. The caller must close the response.

    Range is passed through so the browser's audio player can seek.
    """
    headers = {"Range": range_header} if range_header else {}
    try:
        return requests.get(
            _url(recording_sid, ".mp3"),
            auth=_auth(),
            headers=headers,
            stream=True,
            timeout=(5, 30),
        )
    except requests.RequestException as exc:
        raise RecordingError(str(exc)) from exc


def delete_recording(recording_sid: str) -> None:
    """Delete the recording from Twilio. Already gone (404) counts as done."""
    try:
        response = requests.delete(
            _url(recording_sid, ".json"), auth=_auth(), timeout=10
        )
    except requests.RequestException as exc:
        raise RecordingError(str(exc)) from exc
    if response.status_code not in (204, 404):
        raise RecordingError(f"Twilio answered {response.status_code}")
