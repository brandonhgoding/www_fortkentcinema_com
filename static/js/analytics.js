/**
 * Conversion tracking.
 *
 * One delegated click listener. Elements declare what they are with data-track
 * attributes; this file has no knowledge of specific tiers, phone numbers or
 * URLs, so adding a tracked element never means editing this file:
 *
 *   <a href="..." data-track="membership_join_click" data-track-tier="family">
 *
 * Any `data-track-*` attribute becomes an event parameter (data-track-tier ->
 * `tier`). Nothing here ever attaches a monetary `value`: these are outbound
 * clicks, not purchases, and someone who clicks "Join" and then abandons the
 * Square checkout has not paid us. Revenue is fired only by /thanks, which
 * Square redirects to *after* payment succeeds. See ThanksView in web/views.py.
 *
 * gtag is absent in dev (GA4_MEASUREMENT_ID unset) — every call site tolerates
 * that rather than throwing.
 */

const TRACK_ATTR = "data-track";
const PARAM_PREFIX = "data-track-";

/** Turn data-track-* attributes into GA4 event params. */
export function paramsFor(el) {
  const params = {};
  for (const attr of el.attributes) {
    if (attr.name.startsWith(PARAM_PREFIX) && attr.name !== TRACK_ATTR) {
      const key = attr.name.slice(PARAM_PREFIX.length).replace(/-/g, "_");
      params[key] = attr.value;
    }
  }
  return params;
}

/** Send to GA4, or do nothing if gtag isn't loaded (dev, tests, blocked). */
export function send(eventName, params, gtag) {
  const fn = gtag || (typeof window !== "undefined" ? window.gtag : undefined);
  if (typeof fn !== "function") return false;
  fn("event", eventName, params);
  return true;
}

export function handleClick(event, gtag) {
  const el = event.target.closest(`[${TRACK_ATTR}]`);
  if (!el) return;

  const name = el.getAttribute(TRACK_ATTR);
  if (!name) return;

  send(name, paramsFor(el), gtag);
}

export function installAnalytics(doc, gtag) {
  doc.addEventListener("click", (event) => handleClick(event, gtag));
}

if (typeof document !== "undefined") {
  installAnalytics(document);
}
