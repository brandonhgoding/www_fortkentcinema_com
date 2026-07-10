// Dashboard chrome behaviour: sidebar toggle, fullscreen, keyboard shortcut.
document.addEventListener('alpine:init', () => {
  Alpine.data('dashboardLayout', () => ({
    sidebarOpen: false,
    isFullscreen: false,
    toggleFullscreen() {
      this.isFullscreen = !this.isFullscreen;
      if (this.isFullscreen) {
        document.documentElement.requestFullscreen?.().catch(() => {});
      } else {
        document.exitFullscreen?.().catch(() => {});
      }
    },
    init() {
      document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement) this.isFullscreen = false;
      });
    },
  }));
});

document.addEventListener('alpine:init', () => {
  // Toast store — mirrors ToastContext (auto-dismiss 6s).
  Alpine.store('toast', {
    items: [],
    add(kind, message) {
      const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      this.items.push({ id, kind, message });
      setTimeout(() => this.dismiss(id), 6000);
    },
    dismiss(id) {
      this.items = this.items.filter((t) => t.id !== id);
    },
    icon(kind) {
      return { warning: '⚠', info: 'ℹ', success: '✓', error: '✕' }[kind] || 'ℹ';
    },
  });

  // Confirm store — mirrors ConfirmContext (promise-based, ESC cancels).
  Alpine.store('confirm', {
    open: false,
    title: '',
    message: '',
    confirmLabel: 'Confirm',
    variant: 'default',
    _resolve: null,
    ask({ title, message, confirmLabel = 'Confirm', variant = 'default' }) {
      this.title = title;
      this.message = message;
      this.confirmLabel = confirmLabel;
      this.variant = variant;
      this.open = true;
      document.body.style.overflow = 'hidden';
      return new Promise((resolve) => {
        this._resolve = resolve;
      });
    },
    _settle(value) {
      this.open = false;
      document.body.style.overflow = '';
      const r = this._resolve;
      this._resolve = null;
      if (r) r(value);
    },
    accept() {
      this._settle(true);
    },
    cancel() {
      this._settle(false);
    },
  });
});

window.dashboardToast = (kind, message) => window.Alpine?.store('toast').add(kind, message);
window.dashboardConfirm = (opts) => window.Alpine.store('confirm').ask(opts);

// Alt+N -> go to engagements (create-drawer wiring lands in the Engagements sub-project).
document.addEventListener('keydown', (e) => {
  const el = document.activeElement;
  const typing =
    el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.hasAttribute('contenteditable'));
  if (typing) return;
  if (e.altKey && (e.key === 'n' || e.key === 'N')) {
    e.preventDefault();
    window.location.href = '/dashboard/engagements';
  }
});

document.addEventListener('alpine:init', () => {
  Alpine.store('drawer', {
    open: false,
    title: '',
    show(title = '') {
      this.title = title;
      this.open = true;
      document.body.style.overflow = 'hidden';
    },
    close() {
      this.open = false;
      document.body.style.overflow = '';
    },
  });
});

// After a fragment is swapped into the drawer content, focus the first field.
document.body.addEventListener('htmx:afterSwap', (e) => {
  if (e.detail.target && e.detail.target.id === 'drawer-content') {
    const first = e.detail.target.querySelector('input, select, textarea');
    first?.focus();
  }
});

// HX-Trigger bridge: close-drawer + dashboard-toast (kind/message).
document.body.addEventListener('close-drawer', () => window.Alpine?.store('drawer').close());
document.body.addEventListener('dashboard-toast', (e) => {
  const d = e.detail || {};
  if (d.message) window.dashboardToast(d.kind || 'info', d.message);
});

// Themed confirm for HTMX requests: elements with data-dashboard-confirm='{...}'.
document.body.addEventListener('htmx:confirm', (e) => {
  const raw = e.detail.elt.getAttribute('data-dashboard-confirm');
  if (!raw) return; // no custom confirm -> let HTMX proceed normally
  e.preventDefault();
  let opts = {};
  try { opts = JSON.parse(raw); } catch (_) { opts = { title: 'Confirm', message: raw }; }
  window.dashboardConfirm(opts).then((ok) => { if (ok) e.detail.issueRequest(true); });
});

document.addEventListener('alpine:init', () => {
  Alpine.data('filmCombo', () => ({
    open: false,
    // Called from an option button after a local selection: clear + close.
    selectDone() {
      this.open = false;
      const input = this.$root.querySelector('input[name="q"]');
      if (input) input.value = '';
      const results = this.$root.querySelector('.dropdown');
      if (results) results.innerHTML = '';
    },
    // Roving focus across the rendered option buttons.
    move(dir) {
      this.open = true;
      const items = Array.from(this.$root.querySelectorAll('.dropdown button'));
      if (!items.length) return;
      const idx = items.indexOf(document.activeElement);
      const next = Math.max(0, Math.min(items.length - 1, idx + dir));
      items[next].focus();
    },
  }));
});

// When a film is imported from TMDB, the option button lives inside a combo;
// close/clear that combo after the server fires film-selected.
document.body.addEventListener('film-selected', (e) => {
  const combos = document.querySelectorAll('[x-data="filmCombo"]');
  combos.forEach((c) => {
    const input = c.querySelector('input[name="q"]');
    if (input) input.value = '';
    const results = c.querySelector('.dropdown');
    if (results) results.innerHTML = '';
    if (window.Alpine) window.Alpine.$data(c).open = false;
  });
});

document.addEventListener('alpine:init', () => {
  Alpine.data('statusDropdown', () => ({ open: false }));
});

document.addEventListener('alpine:init', () => {
  Alpine.data('engagementForm', () => ({
    films: [],
    kind: 'REGULAR',
    init() {
      const el = document.getElementById('engagement-initial-films');
      this.films = el ? JSON.parse(el.textContent) : [];
      this.kind = this.$root.dataset.initialKind || 'REGULAR';
      // film-selected fires on document.body from BOTH the local combo $dispatch
      // (bubbles up) and the server TMDB-import HX-Trigger. Only one engagement
      // form exists at a time, so apply unconditionally.
      this._onSel = (e) => this.addFilm(e.detail);
      document.body.addEventListener('film-selected', this._onSel);
    },
    destroy() { document.body.removeEventListener('film-selected', this._onSel); },
    addFilm(film) {
      if (this.kind === 'DOUBLE_FEATURE') {
        if (!this.films.some((f) => f.id === film.id)) this.films.push({ id: film.id, title: film.title, poster: film.poster });
      } else {
        this.films = [{ id: film.id, title: film.title, poster: film.poster }];
      }
    },
    removeFilm(id) { this.films = this.films.filter((f) => f.id !== id); },
    onKindChange() {
      if (this.kind !== 'DOUBLE_FEATURE') this.films = this.films.slice(0, 1);
    },
  }));
});

document.addEventListener('alpine:init', () => {
  Alpine.data('bulkShowtimeForm', () => ({
    times: [''],
    add() { this.times.push(''); },
    remove(i) { this.times.splice(i, 1); if (!this.times.length) this.times = ['']; },
  }));
});
