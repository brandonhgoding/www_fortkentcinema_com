// Dashboard chrome behaviour: sidebar toggle, keyboard shortcut.
document.addEventListener('alpine:init', () => {
  Alpine.data('dashboardLayout', () => ({
    sidebarOpen: false,
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
      // Empty the drawer so the last form never shows under the new title
      // while this one loads. The opener's hx-get swaps in the new form.
      document.getElementById('drawer-content')?.replaceChildren();
      document.getElementById('drawer-footer')?.replaceChildren();
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
// Every form starts with its hidden CSRF input, which cannot take focus, so
// a bare 'input' selector matched that and focused nothing.
document.body.addEventListener('htmx:afterSwap', (e) => {
  if (e.detail.target && e.detail.target.id === 'drawer-content') {
    const first = e.detail.target.querySelector(
      'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])'
    );
    first?.focus();
  }
});

// Messages queued before a full-page redirect render into #flash-messages
// (base_dashboard.html). Show them as toasts once the store exists.
document.addEventListener('alpine:initialized', () => {
  document.querySelectorAll('#flash-messages [data-kind]').forEach((el) => {
    window.dashboardToast(el.dataset.kind || 'info', el.textContent);
  });
});

// Busy state for a drawer form's own request (not the film search inside
// it): mark the drawer busy and disable the footer buttons so a double click
// cannot submit twice. An invalid submit swaps in a fresh footer; a save
// closes the drawer. Either way, afterRequest clears the state. It checks the
// drawer rather than the form, because by then the swap has detached the form.
document.body.addEventListener('htmx:beforeRequest', (e) => {
  const elt = e.detail.elt;
  if (!(elt instanceof HTMLFormElement) || !elt.closest('#drawer-content')) return;
  elt.closest('.drawer')?.setAttribute('aria-busy', 'true');
  document.querySelectorAll('#drawer-footer button').forEach((b) => { b.disabled = true; });
});
document.body.addEventListener('htmx:afterRequest', () => {
  const drawer = document.querySelector('.drawer[aria-busy]');
  if (!drawer) return;
  drawer.removeAttribute('aria-busy');
  document.querySelectorAll('#drawer-footer button').forEach((b) => { b.disabled = false; });
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

// Poll ballot (poll_detail.html): add the picked film to the ballot.
// Listens on body like engagementForm and blogEditor, since film-selected
// arrives both from the local combo ($dispatch, bubbles) and from a TMDB
// import (HX-Trigger). Kept out of hx-* attributes on the picker's wrapper:
// htmx inherits hx-vals, so a wrapper expression ran on the search request.
document.addEventListener('alpine:init', () => {
  Alpine.data('pollBallot', () => ({
    init() {
      this._onSel = (e) => {
        const id = e.detail && e.detail.id;
        if (!id) return;
        htmx.ajax('POST', this.$root.dataset.addUrl, {
          target: '#poll-options',
          swap: 'outerHTML',
          values: { film_id: id },
        });
      };
      document.body.addEventListener('film-selected', this._onSel);
    },
    destroy() { document.body.removeEventListener('film-selected', this._onSel); },
  }));
});

// Blog post editor (blog_editor.html).
document.addEventListener('alpine:init', () => {
  Alpine.data('blogEditor', () => ({
    tab: 'write',
    dirty: false,
    submitting: false,
    slugTouched: false,
    subtitleLength: 0,
    films: [],
    imagePreview: null,
    clearImage: false,
    init() {
      const el = document.getElementById('blog-initial-films');
      this.films = el ? JSON.parse(el.textContent) : [];
      this.subtitleLength = this.$refs.subtitle.value.length;
      // The URL follows the subtitle only on a new post whose URL nobody has
      // typed yet. Once a post is saved, its URL may already be shared.
      this.slugTouched = this.$root.dataset.isNew !== 'true' || this.$refs.slug.value !== '';
      window.addEventListener('beforeunload', (e) => {
        if (this.dirty && !this.submitting) e.preventDefault();
      });
      // From the local combo option ($dispatch, bubbles) and from a TMDB
      // import (HX-Trigger), the same pair engagementForm listens for.
      document.body.addEventListener('film-selected', (e) => {
        const f = e.detail || {};
        if (!f.id || this.films.some((x) => x.id === f.id)) return;
        this.films.push({ id: f.id, title: f.title, poster: f.poster || '' });
        this.dirty = true;
      });
    },
    markDirty(e) {
      // Typing in the film search box is not an edit to the post.
      if (e.target.name !== 'q') this.dirty = true;
    },
    onSubtitle() {
      const value = this.$refs.subtitle.value;
      this.subtitleLength = value.length;
      if (!this.slugTouched) this.$refs.slug.value = this.slugify(value);
    },
    // Mirrors django.utils.text.slugify, which fills a blank URL server-side.
    slugify(value) {
      return value
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/[^\w\s-]/g, '')
        .replace(/[-\s]+/g, '-')
        .slice(0, 100)
        .replace(/^[-_]+|[-_]+$/g, '');
    },
    removeFilm(id) {
      this.films = this.films.filter((f) => f.id !== id);
      this.dirty = true;
    },
    pickImage(e) {
      const file = e.target.files[0];
      if (this.imagePreview) URL.revokeObjectURL(this.imagePreview);
      this.imagePreview = file ? URL.createObjectURL(file) : null;
      this.clearImage = false;
    },
    confirmUnpublish(button) {
      window.dashboardConfirm({
        title: 'Unpublish Post',
        message: 'Take this post off the website? It becomes a draft again, and its film page stops linking to it.',
        confirmLabel: 'Unpublish',
      }).then((ok) => {
        if (!ok) return;
        this.submitting = true;
        button.form.requestSubmit(button);
      });
    },
  }));
});
