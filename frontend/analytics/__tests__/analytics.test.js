import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  handleClick,
  installAnalytics,
  paramsFor,
  send,
} from '../../../static/js/analytics.js';

function el(html) {
  document.body.innerHTML = html;
  return document.body.firstElementChild;
}

describe('paramsFor', () => {
  it('turns data-track-* attributes into event params', () => {
    const node = el('<a data-track="x" data-track-tier="family" data-track-location="footer"></a>');
    expect(paramsFor(node)).toEqual({ tier: 'family', location: 'footer' });
  });

  it('kebab-cases into snake_case', () => {
    const node = el('<a data-track="x" data-track-item-name="Cinema Supporter"></a>');
    expect(paramsFor(node)).toEqual({ item_name: 'Cinema Supporter' });
  });

  it('ignores data-track itself and unrelated attributes', () => {
    const node = el('<a data-track="x" href="/y" class="z" data-other="q"></a>');
    expect(paramsFor(node)).toEqual({});
  });
});

describe('send', () => {
  it('forwards the event to gtag', () => {
    const gtag = vi.fn();
    expect(send('giftcard_click', { a: 1 }, gtag)).toBe(true);
    expect(gtag).toHaveBeenCalledWith('event', 'giftcard_click', { a: 1 });
  });

  it('does nothing when gtag is absent', () => {
    // The dev/staging case: GA4_MEASUREMENT_ID is unset, so gtag never loads.
    // Must not throw.
    expect(() => send('giftcard_click', {}, undefined)).not.toThrow();
    expect(send('giftcard_click', {}, undefined)).toBe(false);
  });
});

describe('click handling', () => {
  let gtag;

  beforeEach(() => {
    gtag = vi.fn();
    document.body.innerHTML = '';
  });

  it('fires the declared event with its params', () => {
    const node = el('<a data-track="phone_click" data-track-location="footer">Call</a>');
    handleClick({ target: node }, gtag);
    expect(gtag).toHaveBeenCalledWith('event', 'phone_click', { location: 'footer' });
  });

  it('fires when a child of the tracked element is clicked', () => {
    el('<a data-track="giftcard_click"><span id="inner">Buy</span></a>');
    const inner = document.getElementById('inner');
    handleClick({ target: inner }, gtag);
    expect(gtag).toHaveBeenCalledWith('event', 'giftcard_click', {});
  });

  it('ignores clicks on untracked elements', () => {
    const node = el('<a href="/somewhere">Plain link</a>');
    handleClick({ target: node }, gtag);
    expect(gtag).not.toHaveBeenCalled();
  });

  it('never attaches a monetary value to a click', () => {
    // The whole point: a click is intent, not revenue.
    const node = el('<a data-track="giftcard_click" data-track-amount="50">Buy</a>');
    handleClick({ target: node }, gtag);
    const params = gtag.mock.calls[0][2];
    expect(params).not.toHaveProperty('value');
    expect(params).not.toHaveProperty('currency');
  });

  it('installs a delegated listener that survives later DOM changes', () => {
    installAnalytics(document, gtag);
    // Element added *after* install — delegation must still catch it.
    document.body.innerHTML = '<a data-track="phone_click" data-track-location="footer">Call</a>';
    document.querySelector('[data-track]').click();
    expect(gtag).toHaveBeenCalledWith('event', 'phone_click', { location: 'footer' });
  });
});
