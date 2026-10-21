"""Twilio webhooks for the phone line.

Each view returns TwiML telling Twilio what to say next. Action URLs are
relative, so Twilio resolves them against the URL it just called — the same
host and scheme it signed — and ngrok and production need no config here.
"""

import logging

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from twilio.twiml.voice_response import Gather, VoiceResponse

from . import recordings
from .decorators import twilio_webhook
from .models import CallLog, Voicemail
from .recordings import RECORDING_SID
from .speech import hours_and_prices_speech, showtimes_speech

logger = logging.getLogger(__name__)

GREETING = "Thanks for calling Fort Kent Cinema."
MENU = "Press 1 for today's showtimes, 2 for hours and prices, or 3 to leave a message."
GOODBYE = "Thanks for calling Fort Kent Cinema. Goodbye."

# The menu plays at most twice in a row without a valid key: once, then
# repeated once after a miss, then goodbye.
LAST_ATTEMPT = 2
VOICEMAIL_MAX_SECONDS = 120
# Twilio keeps silent recordings, so a caller who hangs up at the beep
# leaves one of a second or so. Nothing that short holds a name and a
# number; it is not a message and must not light up the dashboard.
MIN_VOICEMAIL_SECONDS = 2

# Twilio transcription costs ~$0.05 a minute — most of a voicemail's cost —
# so it is off; staff listen in the dashboard instead. Setting this to True
# turns it back on: the transcription webhook and Voicemail.transcript are
# kept for exactly that.
TRANSCRIBE = False

# Amazon Polly voice for everything the line says. Every <Say> goes through
# _say() so the whole call is one voice; swapping it is this one line (e.g.
# "Polly.Matthew-Neural" for the more natural, slightly pricier version).
VOICE = "Polly.Matthew"


def _say(verb: VoiceResponse | Gather, text: str) -> None:
    verb.say(text, voice=VOICE)


def _twiml(response: VoiceResponse) -> HttpResponse:
    return HttpResponse(str(response), content_type="text/xml")


def _log_call(request: HttpRequest, choice: str | None = None) -> None:
    """Record the call and, at the menu, the key pressed.

    The log is evidence for the Level 2 agent, not the call itself, so a
    database error here is logged and the caller still hears the line.
    """
    try:
        log, _ = CallLog.objects.get_or_create(
            call_sid=request.POST.get("CallSid", ""),
            defaults={
                "caller": request.POST.get("From", ""),
                "called": request.POST.get("To", ""),
            },
        )
        if choice is not None:
            log.add_choice(choice)
    except Exception:
        logger.exception("Couldn't log call %s", request.POST.get("CallSid", ""))


def _add_menu(response: VoiceResponse, attempt: int) -> None:
    action = f"{reverse('phone:menu')}?attempt={attempt}"
    gather = response.gather(num_digits=1, action=action, timeout=6)
    _say(gather, MENU)
    # Reached only when the caller presses nothing: the menu view sees no
    # Digits and treats it as a miss.
    response.redirect(action)


def _attempt(request: HttpRequest) -> int:
    try:
        return min(max(int(request.GET.get("attempt", 1)), 1), LAST_ATTEMPT)
    except ValueError:
        return 1


@twilio_webhook
def incoming_call(request: HttpRequest) -> HttpResponse:
    _log_call(request)
    response = VoiceResponse()
    _say(response, GREETING)
    _add_menu(response, attempt=1)
    return _twiml(response)


@twilio_webhook
def menu(request: HttpRequest) -> HttpResponse:
    attempt = _attempt(request)
    digit = request.POST.get("Digits", "")
    _log_call(request, choice=digit or "none")

    response = VoiceResponse()
    if digit in ("1", "2"):
        _say(
            response, showtimes_speech() if digit == "1" else hours_and_prices_speech()
        )
        # Offer the menu again so a caller can hear prices after showtimes,
        # but as the last attempt: silence now means they're done.
        _add_menu(response, attempt=LAST_ATTEMPT)
    elif digit == "3":
        _say(
            response,
            "Please leave your name, number and message after the beep. "
            "Press pound when you're finished.",
        )
        response.record(
            max_length=VOICEMAIL_MAX_SECONDS,
            play_beep=True,
            finish_on_key="#",
            action=reverse("phone:voicemail_recorded"),
            # The action callback is the caller's path back into the call,
            # and Twilio sends it exactly once; the status callback fires
            # when the file is ready and is retried, so a message survives
            # a restart that swallowed the action. Both upsert the same row.
            recording_status_callback=reverse("phone:voicemail_status"),
            **(
                {
                    "transcribe": True,
                    "transcribe_callback": reverse("phone:voicemail_transcribed"),
                }
                if TRANSCRIBE
                else {}
            ),
        )
        # Twilio's docs say TwiML after <Record> is unreachable; this is
        # kept for the case they leave open, a caller who never starts a
        # recording. An empty recording reaches the action callback instead
        # and is turned away there with the same words.
        _say(response, f"We didn't get a message. {GOODBYE}")
        response.hangup()
    elif attempt < LAST_ATTEMPT:
        _say(
            response,
            "Sorry, that's not an option." if digit else "Sorry, I didn't catch that.",
        )
        _add_menu(response, attempt=attempt + 1)
    else:
        _say(response, GOODBYE)
        response.hangup()
    return _twiml(response)


def _recording_sid(request: HttpRequest) -> str:
    """The recording's SID, or "" when the request names none.

    Twilio documents RecordingSid for the status callback but not for the
    <Record> action, where only RecordingUrl is promised; the URL ends in
    the SID, so fall back to that, but only when it looks like one.
    """
    sid = request.POST.get("RecordingSid", "")
    if sid:
        return sid
    tail = request.POST.get("RecordingUrl", "").rstrip("/").rsplit("/", 1)[-1]
    return tail if RECORDING_SID.match(tail) else ""


def _upsert_voicemail(
    request: HttpRequest, recording_sid: str, **fields: object
) -> Voicemail:
    """Create or update the voicemail for a recording.

    Only fields the request actually carries are passed in, so a repeated
    webhook never blanks what an earlier one stored, and staff edits
    (status, notes) are never touched.
    """
    call = CallLog.objects.filter(call_sid=request.POST.get("CallSid", "")).first()
    voicemail, _ = Voicemail.objects.update_or_create(
        recording_sid=recording_sid,
        defaults=fields,
        create_defaults={
            **fields,
            "call": call,
            # The status callback has no From; the call log does.
            "caller": request.POST.get("From", "") or (call.caller if call else ""),
            "recording_url": request.POST.get("RecordingUrl", ""),
        },
    )
    return voicemail


def _recording_fields(request: HttpRequest) -> dict[str, object]:
    fields: dict[str, object] = {}
    if request.POST.get("RecordingUrl"):
        fields["recording_url"] = request.POST["RecordingUrl"]
    duration = request.POST.get("RecordingDuration", "")
    if duration.isdigit():
        fields["duration_seconds"] = int(duration)
    return fields


def _too_short(fields: dict[str, object]) -> bool:
    """True for a recording that can't hold a message. An unknown length
    is kept: losing a real message costs more than a stray empty one."""
    duration = fields.get("duration_seconds")
    return isinstance(duration, int) and duration < MIN_VOICEMAIL_SECONDS


@twilio_webhook
def voicemail_recorded(request: HttpRequest) -> HttpResponse:
    response = VoiceResponse()
    sid = _recording_sid(request)
    fields = _recording_fields(request)
    if sid and _too_short(fields):
        # No row: the status callback deletes the recording once it is
        # ready, which keeps a call to Twilio out of the caller's wait.
        _say(response, f"We didn't get a message. {GOODBYE}")
    elif sid:
        _upsert_voicemail(request, sid, **fields)
        _say(response, f"Thanks, we got your message. {GOODBYE}")
    else:
        # Don't thank a caller for a message nobody will ever hear.
        logger.error(
            "Voicemail action callback for call %s named no recording: %s",
            request.POST.get("CallSid", ""),
            dict(request.POST.items()),
        )
        _say(response, f"Sorry, we didn't get your message. {GOODBYE}")
    response.hangup()
    return _twiml(response)


@twilio_webhook
def voicemail_status(request: HttpRequest) -> HttpResponse:
    """Twilio's recordingStatusCallback: the recording is ready to fetch.

    This arrives after the action callback (and is retried on failure), so
    it is the safety net for a message whose action callback was lost.
    """
    sid = _recording_sid(request)
    fields = _recording_fields(request)
    if sid and request.POST.get("RecordingStatus") == "completed":
        if _too_short(fields):
            _discard_recording(sid)
        else:
            _upsert_voicemail(request, sid, **fields)
    # Twilio ignores the body of a status callback; it only needs a 2xx.
    return _twiml(VoiceResponse())


def _discard_recording(sid: str) -> None:
    """Delete an empty recording from Twilio. Best effort: there is no row
    to retry from, so a failure is logged and the file is left there."""
    if not recordings.is_configured():
        logger.warning(
            "Empty recording %s left at Twilio: TWILIO_ACCOUNT_SID is not set.", sid
        )
        return
    try:
        recordings.delete_recording(sid)
    except recordings.RecordingError as exc:
        logger.warning("Couldn't delete empty recording %s from Twilio: %s", sid, exc)


@twilio_webhook
def voicemail_transcribed(request: HttpRequest) -> HttpResponse:
    sid = _recording_sid(request)
    if sid:
        _upsert_voicemail(
            request,
            sid,
            transcript=request.POST.get("TranscriptionText", ""),
            transcription_status=request.POST.get("TranscriptionStatus", ""),
        )
    # Twilio ignores the body of a transcription callback; it only needs a 2xx.
    return _twiml(VoiceResponse())
