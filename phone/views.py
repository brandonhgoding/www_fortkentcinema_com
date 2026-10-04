"""Twilio webhooks for the phone line.

Each view returns TwiML telling Twilio what to say next. Action URLs are
relative, so Twilio resolves them against the URL it just called — the same
host and scheme it signed — and ngrok and production need no config here.
"""

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from twilio.twiml.voice_response import Gather, VoiceResponse

from .decorators import twilio_webhook
from .models import CallLog, Voicemail
from .speech import hours_and_prices_speech, showtimes_speech

GREETING = "Thanks for calling Fort Kent Cinema."
MENU = (
    "Press 1 for today's showtimes, 2 for hours and prices, " "or 3 to leave a message."
)
GOODBYE = "Thanks for calling Fort Kent Cinema. Goodbye."

# The menu plays at most twice in a row without a valid key: once, then
# repeated once after a miss, then goodbye.
LAST_ATTEMPT = 2
VOICEMAIL_MAX_SECONDS = 120

# Amazon Polly voice for everything the line says. Every <Say> goes through
# _say() so the whole call is one voice; swapping it is this one line (e.g.
# "Polly.Matthew-Neural" for the more natural, slightly pricier version).
VOICE = "Polly.Matthew"


def _say(verb: VoiceResponse | Gather, text: str) -> None:
    verb.say(text, voice=VOICE)


def _twiml(response: VoiceResponse) -> HttpResponse:
    return HttpResponse(str(response), content_type="text/xml")


def _call_log(request: HttpRequest) -> CallLog:
    log, _ = CallLog.objects.get_or_create(
        call_sid=request.POST.get("CallSid", ""),
        defaults={
            "caller": request.POST.get("From", ""),
            "called": request.POST.get("To", ""),
        },
    )
    return log


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
    _call_log(request)
    response = VoiceResponse()
    _say(response, GREETING)
    _add_menu(response, attempt=1)
    return _twiml(response)


@twilio_webhook
def menu(request: HttpRequest) -> HttpResponse:
    attempt = _attempt(request)
    digit = request.POST.get("Digits", "")
    _call_log(request).add_choice(digit or "none")

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
            transcribe=True,
            transcribe_callback=reverse("phone:voicemail_transcribed"),
        )
        # Twilio skips the action and falls through here when nothing was
        # recorded (the caller stayed silent).
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


def _upsert_voicemail(request: HttpRequest, **fields: object) -> Voicemail:
    voicemail, _ = Voicemail.objects.update_or_create(
        recording_sid=request.POST.get("RecordingSid", ""),
        defaults=fields,
        create_defaults={
            **fields,
            "call": CallLog.objects.filter(
                call_sid=request.POST.get("CallSid", "")
            ).first(),
            "caller": request.POST.get("From", ""),
            "recording_url": request.POST.get("RecordingUrl", ""),
        },
    )
    return voicemail


@twilio_webhook
def voicemail_recorded(request: HttpRequest) -> HttpResponse:
    if request.POST.get("RecordingSid"):
        duration = request.POST.get("RecordingDuration", "")
        _upsert_voicemail(
            request,
            recording_url=request.POST.get("RecordingUrl", ""),
            duration_seconds=int(duration) if duration.isdigit() else None,
        )
    response = VoiceResponse()
    _say(response, f"Thanks, we got your message. {GOODBYE}")
    response.hangup()
    return _twiml(response)


@twilio_webhook
def voicemail_transcribed(request: HttpRequest) -> HttpResponse:
    if request.POST.get("RecordingSid"):
        _upsert_voicemail(
            request,
            transcript=request.POST.get("TranscriptionText", ""),
            transcription_status=request.POST.get("TranscriptionStatus", ""),
        )
    # Twilio ignores the body of a transcription callback; it only needs a 2xx.
    return _twiml(VoiceResponse())
