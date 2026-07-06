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
