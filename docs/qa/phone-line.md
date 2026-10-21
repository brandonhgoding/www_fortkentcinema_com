# Phone line: manual checklist for a real call

Written 2026-10-21 from `main` at `5955bf3` (after the voicemail status
callback and the empty-recording rule). Copy quoted here comes from
`phone/views.py` and `phone/speech.py`; prices from `web/constants.py`.

The automated suite proves the TwiML and the webhooks; it cannot prove what a
caller hears or what Twilio actually sends. Work through this with a real
phone against the production number, or a dev number pointed at ngrok (see the
Phone line section of `README.md`). Tick boxes as you go and write anything
surprising in the Findings table at the end. Items marked **decides** feed a
code change.

---

## Part A: the menu

- [ ] Call. Expected: "Thanks for calling Fort Kent Cinema." then "Press 1 for
      today's showtimes, 2 for hours and prices, or 3 to leave a message."
      One voice (Polly.Matthew) for the whole call.
- [ ] Press a key during the greeting. The greeting is outside the Gather, so
      it should not be interrupted; note whether the key is buffered and
      answered once the menu starts.
- [ ] Press a key during the menu. Expected: menu stops mid-sentence and the
      option plays.
- [ ] Say nothing, twice. Expected: "Sorry, I didn't catch that." and the menu
      once more, then "Thanks for calling Fort Kent Cinema. Goodbye." and a
      hang-up. About two menu plays in total.
- [ ] Press 9, then 9 again. Expected: "Sorry, that's not an option." then
      goodbye.
- [ ] Press 1, then an invalid key at the second menu. Expected (by design):
      straight to goodbye with no hint, because the menu after an answer is
      the last attempt. **Decides** whether that stays.

## Part B: showtimes (press 1)

- [ ] With shows left today. Expected: "Today's showtimes: Hamnet at 4:00 PM
      and 7:15 PM." Listen to how "4:00 PM" is read, where "free for members"
      lands, and titles with numbers in them.
- [ ] With a double feature (two films in one engagement, no display title).
      Expected today: "A plus B at …" (review item M4). **Decides** the wording.
- [ ] After today's last show has started. Expected: "There are no more shows
      today. Our next showtimes are tomorrow: …" (or the weekday and date when
      the next day is not tomorrow).
- [ ] With nothing scheduled at all. Expected: "…check fort kent cinema dot
      com for updates", spoken as five words, not "fortkentcinema.com".
- [ ] At 11:58 PM Eastern with an 11:59 PM show and a 12:30 AM show. Expected:
      "Today's showtimes: X at 11:59 PM." At 12:01 AM: "X at 12:30 AM." A
      12:00 AM show is read as "tomorrow". **Decides** review item L3.
- [ ] A minute after a show started. Expected: that show is gone from the
      list. **Decides** whether a grace window is wanted (review item L3).
- [ ] On a DST day (2026-11-01 during the repeated 1 AM hour, 2026-03-08 after
      3 AM). Expected: no error, Eastern times, the right "tomorrow".

## Part C: hours and prices (press 2)

- [ ] Expected: "We're at 13 Hall Street in Fort Kent, and the box office
      opens 30 minutes before every show. Tickets are $8 for adults, $7 for
      seniors, and $6 for children. Matinees, for shows starting at 4:00 PM or
      earlier, are $6. Members pay $4 for any show, and some shows are free
      for members. You can also buy tickets ahead of time at fort kent cinema
      dot com." Listen for "eight dollars", the street number, and the website.
- [ ] Press 1 at the menu that follows. Expected: showtimes, then one more
      menu; silence ends the call.

## Part D: voicemail (press 3)

- [ ] Speak a message, press #. Expected: beep after "Press pound when you're
      finished.", recording stops at #, "Thanks, we got your message. Thanks
      for calling Fort Kent Cinema. Goodbye.", hang-up. Dashboard: one NEW
      voicemail with your number and a length close to what you spoke, the
      sidebar badge up by one, the home alert "You have 1 new voicemail".
- [ ] Speak, then pause for six seconds. Expected: the recording ends on
      Twilio's 5-second silence timeout and the thanks plays (review item
      M5). **Decides** whether to lengthen it.
- [ ] Hang up at the beep without speaking. Expected: no row, no badge change.
      Note which happened: Twilio skipped the action (the call would have
      played "We didn't get a message" only if you had stayed on), or Twilio
      sent a recording of a second or so and the status callback deleted it
      (Monitor → Logs → Recordings shows none). **Decides** whether
      `MIN_VOICEMAIL_SECONDS` is right.
- [ ] Say one word and hang up. Expected: a recording of about 1 second is
      discarded the same way. Two seconds or more is kept.
- [ ] Talk past two minutes. Expected: the recording stops at 2:00 and the
      thanks plays; dashboard length is at most 120 s.
- [ ] Talk, then hang up mid-message instead of pressing #. Expected: a
      voicemail still appears, with the partial length.
- [ ] Call with caller ID withheld (*67). Expected: the row shows "anonymous"
      or "+266696687" and the page renders; the call is answered normally.
- [ ] Twilio console → Monitor → Logs → Recordings after the above: one
      recording per kept message, none for the discarded ones.

## Part E: dashboard

- [ ] Play a voicemail, seek to the middle, drag back. Expected: it plays and
      seeks; the page source contains no api.twilio.com URL; no basic-auth
      prompt.
- [ ] Change the status to Handled, add a note. Expected: both stick; the
      badge drops by one.
- [ ] Delete. Expected: the recording is gone from Twilio (Monitor → Logs →
      Recordings) and the row is gone. Delete a row whose recording was
      already removed in Twilio. Expected: still succeeds.
- [ ] Django admin → Voicemail → "Listen". Expected today: links straight to
      Twilio (review item M3); with "Enforce HTTP Auth on Media URLs" on, it
      prompts for credentials.

## Part F: console and failure modes

- [ ] The number's Voice URL is exactly `https://www.fortkentcinema.com/phone/voice/`,
      HTTP POST. Try it once with `http://`, once without `www`, once without
      the trailing slash: each should fail (Twilio's error message or a
      silent hang-up), and the server log should show a WARNING naming the URL
      the signature was checked against.
- [ ] A Voice Fallback URL is set and points at a TwiML Bin with the static
      message. Test it by pointing the Voice URL at a bad path for one call.
- [ ] Monitor → Alerts: email notifications are on. After the previous step an
      alert email arrived.
- [ ] Monitor → Debugger: no errors after a clean run of Parts A to E.

## Findings

| Item | What happened | Follow-up |
|------|---------------|-----------|
|      |               |           |
