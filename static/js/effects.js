const v = /* @__PURE__ */ new Map();
let y = !1, u = 0, c = null;
function A(e, t, n) {
  const i = e.getBoundingClientRect(), x = (n - i.top) / (n * 0.6), r = Math.max(0, Math.min(1, x));
  r !== t.progress && (t.progress = r, t.cb(r));
}
function $() {
  u = 0;
  const e = window.innerHeight;
  v.forEach((t, n) => {
    t.active && A(n, t, e);
  });
}
function d() {
  u || (u = requestAnimationFrame($));
}
function N() {
  c || typeof IntersectionObserver > "u" || (c = new IntersectionObserver(
    (e) => {
      e.forEach((t) => {
        const n = v.get(t.target);
        n && (n.active = t.isIntersecting);
      }), d();
    },
    { rootMargin: "20% 0px" }
  ));
}
function k(e, t) {
  N();
  const n = { cb: t, progress: -1, active: !c };
  return v.set(e, n), c && c.observe(e), y || (window.addEventListener("scroll", d, { passive: !0 }), window.addEventListener("resize", d), y = !0), A(e, n, window.innerHeight), d(), () => {
    v.delete(e), c && c.unobserve(e), v.size === 0 && (y && (window.removeEventListener("scroll", d), window.removeEventListener("resize", d), y = !1), u && (cancelAnimationFrame(u), u = 0));
  };
}
function S() {
  try {
    return typeof window > "u" || typeof window.matchMedia != "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "static" : window.matchMedia("(pointer: coarse)").matches ? "ambient" : "full";
  } catch {
    return "static";
  }
}
const H = 0.3;
function Y(e) {
  try {
    if (S() === "static") {
      e.classList.add("fx-reveal", "fx-revealed");
      return;
    }
    e.classList.add("fx-reveal");
    let t = null, n = !1;
    t = k(e, (i) => {
      e.style.setProperty("--fx-fade", String(Math.min(i / H, 1))), i >= 1 && (e.classList.add("fx-revealed"), n = !0, t && (t(), t = null));
    }), n && t && (t(), t = null);
  } catch (t) {
    console.error("[effects] scroll reveal disabled:", t), e.classList.add("fx-reveal", "fx-revealed");
  }
}
function M(e = document) {
  e.querySelectorAll("[data-reveal]").forEach((t) => {
    t.dataset.revealInit || (t.dataset.revealInit = "1", Y(t));
  });
}
const l = /* @__PURE__ */ new Set();
let a = null, h = null;
function q(e) {
  h === null && (h = e);
  const t = e - h;
  l.forEach((n) => {
    try {
      n(t);
    } catch (i) {
      console.error("[effects] tick subscriber threw; removing it:", i), l.delete(n);
    }
  }), a = l.size ? requestAnimationFrame(q) : null, a === null && (h = null);
}
function C() {
  a !== null || l.size === 0 || typeof document < "u" && document.hidden || (a = requestAnimationFrame(q));
}
function O() {
  a !== null && (cancelAnimationFrame(a), a = null), h = null;
}
function _(e) {
  return l.add(e), C(), () => {
    l.delete(e), l.size === 0 && O();
  };
}
typeof document < "u" && document.addEventListener("visibilitychange", () => {
  document.hidden ? O() : C();
});
const L = 0.15, p = /* @__PURE__ */ new Set(), s = { x: -9999, y: -9999, sx: -9999, sy: -9999 };
let g = null, w = !1;
function z(e) {
  s.sx === -9999 && (s.sx = e.clientX, s.sy = e.clientY), s.x = e.clientX, s.y = e.clientY;
}
function F() {
  p.size === 0 && (w && (window.removeEventListener("mousemove", z), w = !1), g && (g(), g = null));
}
function B() {
  s.sx += (s.x - s.sx) * L, s.sy += (s.y - s.sy) * L, p.forEach((e) => {
    try {
      e(s);
    } catch (t) {
      console.error("[effects] pointer subscriber threw; removing it:", t), p.delete(e), F();
    }
  });
}
function X(e) {
  return p.add(e), w || (window.addEventListener("mousemove", z), w = !0), g || (g = _(B)), () => {
    p.delete(e), F();
  };
}
const D = 4;
function V(e, t = ":scope > article, :scope > a") {
  if (S() === "full")
    try {
      e.classList.add("fx-spotlight-grid");
      const n = document.createElement("div");
      n.className = "fx-spotlight", n.setAttribute("aria-hidden", "true"), e.appendChild(n);
      let i = !1;
      const x = () => e.querySelectorAll(t).forEach((r) => {
        r.classList.remove("fx-card--focus", "fx-card--dim"), r.style.transform = "";
      });
      X((r) => {
        const f = e.getBoundingClientRect(), E = r.sx >= f.left && r.sx <= f.right && r.sy >= f.top && r.sy <= f.bottom;
        if (e.classList.toggle("fx-spotlight-grid--active", E), !E) {
          i && (x(), i = !1);
          return;
        }
        i = !0, n.style.transform = `translate(${r.sx - f.left}px, ${r.sy - f.top}px)`, e.querySelectorAll(t).forEach((m) => {
          const o = m.getBoundingClientRect(), b = r.x >= o.left && r.x <= o.right && r.y >= o.top && r.y <= o.bottom;
          if (m.classList.toggle("fx-card--focus", b), m.classList.toggle("fx-card--dim", !b), b) {
            const R = o.left + o.width / 2, T = (r.sx - R) / (o.width / 2) * D;
            m.style.transform = `translateY(-6px) perspective(800px) rotateY(${T}deg)`;
          } else
            m.style.transform = "";
        });
      });
    } catch (n) {
      console.error("[effects] card spotlight disabled:", n);
    }
}
function P(e = document) {
  e.querySelectorAll("[data-spotlight]").forEach((t) => {
    t.dataset.spotlightInit || (t.dataset.spotlightInit = "1", V(t));
  });
}
const G = "hero--offscreen";
function j(e) {
  new IntersectionObserver((n) => {
    n.forEach((i) => {
      i.target.classList.toggle(G, !i.isIntersecting);
    });
  }).observe(e);
}
function J(e = document) {
  typeof IntersectionObserver == "function" && e.querySelectorAll("[data-hero-idle]").forEach((t) => {
    if (!t.dataset.heroIdleInit) {
      t.dataset.heroIdleInit = "1";
      try {
        j(t);
      } catch (n) {
        console.error("[effects] hero idle disabled:", n);
      }
    }
  });
}
function I() {
  M(document), P(document), J(document);
}
document.readyState !== "loading" ? I() : document.addEventListener("DOMContentLoaded", I);
document.body.addEventListener("htmx:afterSwap", (e) => {
  M(e.target), P(e.target);
});
