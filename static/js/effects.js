var w = 0, y = 0, h = 0, q = 1e3, I, m, S = 0, f = 0, A = 0, b = typeof performance == "object" && performance.now ? performance : Date, H = typeof window == "object" && window.requestAnimationFrame ? window.requestAnimationFrame.bind(window) : function(t) {
  setTimeout(t, 17);
};
function C() {
  return f || (H(Q), f = b.now() + A);
}
function Q() {
  f = 0;
}
function P() {
  this._call = this._time = this._next = null;
}
P.prototype = Y.prototype = {
  constructor: P,
  restart: function(t, e, n) {
    if (typeof t != "function") throw new TypeError("callback is not a function");
    n = (n == null ? C() : +n) + (e == null ? 0 : +e), !this._next && m !== this && (m ? m._next = this : I = this, m = this), this._call = t, this._time = n, F();
  },
  stop: function() {
    this._call && (this._call = null, this._time = 1 / 0, F());
  }
};
function Y(t, e, n) {
  var r = new P();
  return r.restart(t, e, n), r;
}
function Z() {
  C(), ++w;
  for (var t = I, e; t; )
    (e = f - t._time) >= 0 && t._call.call(void 0, e), t = t._next;
  --w;
}
function N() {
  f = (S = b.now()) + A, w = y = 0;
  try {
    Z();
  } finally {
    w = 0, et(), f = 0;
  }
}
function tt() {
  var t = b.now(), e = t - S;
  e > q && (A -= e, S = t);
}
function et() {
  for (var t, e = I, n, r = 1 / 0; e; )
    e._call ? (r > e._time && (r = e._time), t = e, e = e._next) : (n = e._next, e._next = null, e = t ? t._next = n : I = n);
  m = t, F(r);
}
function F(t) {
  if (!w) {
    y && (y = clearTimeout(y));
    var e = t - f;
    e > 24 ? (t < 1 / 0 && (y = setTimeout(N, t - b.now() - A)), h && (h = clearInterval(h))) : (h || (S = b.now(), h = setInterval(tt, q)), w = 1, H(N));
  }
}
const u = /* @__PURE__ */ new Set();
let v = null;
function $() {
  v || u.size === 0 || (v = Y((t) => {
    u.forEach((e) => {
      try {
        e(t);
      } catch (n) {
        console.error("[effects] tick subscriber threw; removing it:", n), u.delete(e);
      }
    });
  }));
}
function j() {
  v && (v.stop(), v = null);
}
function W(t) {
  return u.add(t), $(), () => {
    u.delete(t), u.size === 0 && j();
  };
}
typeof document < "u" && document.addEventListener("visibilitychange", () => {
  document.hidden ? j() : $();
});
const O = 0.15, g = /* @__PURE__ */ new Set(), o = { x: -9999, y: -9999, sx: -9999, sy: -9999 };
let x = null, k = !1;
function X(t) {
  o.sx === -9999 && (o.sx = t.clientX, o.sy = t.clientY), o.x = t.clientX, o.y = t.clientY;
}
function B() {
  g.size === 0 && (k && (window.removeEventListener("mousemove", X), k = !1), x && (x(), x = null));
}
function nt() {
  o.sx += (o.x - o.sx) * O, o.sy += (o.y - o.sy) * O, g.forEach((t) => {
    try {
      t(o);
    } catch (e) {
      console.error("[effects] pointer subscriber threw; removing it:", e), g.delete(t), B();
    }
  });
}
function it(t) {
  return g.add(t), k || (window.addEventListener("mousemove", X), k = !0), x || (x = W(nt)), () => {
    g.delete(t), B();
  };
}
function G() {
  try {
    return typeof window > "u" || typeof window.matchMedia != "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "static" : window.matchMedia("(pointer: coarse)").matches ? "ambient" : "full";
  } catch {
    return "static";
  }
}
const rt = 70, ot = 0.35;
function st(t) {
  const e = G();
  if (e !== "static")
    try {
      let T = function() {
        c = t.width = window.innerWidth, s = t.height = window.innerHeight;
      };
      var n = T;
      const r = t.getContext("2d");
      if (!r) return;
      let c = 0, s = 0;
      T();
      const J = window.innerWidth < 700 ? 25 : 50, K = Array.from({ length: J }, () => ({
        x: Math.random() * c,
        y: Math.random() * s,
        r: Math.random() * 1.6 + 0.4,
        vx: (Math.random() - 0.5) * 0.15,
        vy: -(Math.random() * 0.2 + 0.05),
        a: Math.random() * 0.4 + 0.1
      })), E = { sx: -9999, sy: -9999 };
      e === "full" && it((_) => {
        E.sx = _.sx, E.sy = _.sy;
      }), W(() => {
        r.clearRect(0, 0, c, s);
        const _ = Math.max(ot, 1 - window.scrollY / (s * 2));
        K.forEach((i) => {
          const z = i.x - E.sx, D = i.y - E.sy, M = Math.hypot(z, D);
          M < rt && M > 0 && (i.x += z / M * 1.1, i.y += D / M * 1.1), i.x += i.vx, i.y += i.vy, i.y < -5 && (i.y = s + 5, i.x = Math.random() * c), i.x < -5 && (i.x = c + 5), i.x > c + 5 && (i.x = -5), r.beginPath(), r.arc(i.x, i.y, i.r, 0, Math.PI * 2), r.fillStyle = `rgba(201, 168, 76, ${i.a * _})`, r.fill();
        });
      }), window.addEventListener("resize", T);
    } catch (r) {
      console.error("[effects] ambient dust disabled:", r);
    }
}
function ct(t = document) {
  const e = t.querySelector("[data-ambient-dust]");
  !e || e.dataset.dustInit || (e.dataset.dustInit = "1", st(e));
}
const at = 0.6, p = /* @__PURE__ */ new Map();
let L = !1, d = 0, a = null;
function U(t, e, n) {
  const r = t.getBoundingClientRect(), c = (n - r.top) / (n * at), s = Math.max(0, Math.min(1, c));
  s !== e.progress && (e.progress = s, e.cb(s));
}
function ft() {
  d = 0;
  const t = window.innerHeight;
  p.forEach((e, n) => {
    e.active && U(n, e, t);
  });
}
function l() {
  d || (d = requestAnimationFrame(ft));
}
function lt() {
  a || typeof IntersectionObserver > "u" || (a = new IntersectionObserver(
    (t) => {
      t.forEach((e) => {
        const n = p.get(e.target);
        n && (n.active = e.isIntersecting);
      }), l();
    },
    { rootMargin: "20% 0px" }
  ));
}
function ut(t, e) {
  lt();
  const n = { cb: e, progress: -1, active: !a };
  return p.set(t, n), a && a.observe(t), L || (window.addEventListener("scroll", l, { passive: !0 }), window.addEventListener("resize", l), L = !0), U(t, n, window.innerHeight), l(), () => {
    p.delete(t), a && a.unobserve(t), p.size === 0 && (L && (window.removeEventListener("scroll", l), window.removeEventListener("resize", l), L = !1), d && (cancelAnimationFrame(d), d = 0));
  };
}
const dt = 0.3;
function wt(t) {
  try {
    if (G() === "static") {
      t.classList.add("fx-reveal", "fx-revealed");
      return;
    }
    t.classList.add("fx-reveal");
    let e = ut(t, (n) => {
      t.style.setProperty("--fx-draw", String(n)), t.style.setProperty("--fx-fade", String(Math.min(n / dt, 1))), n >= 1 && (t.classList.add("fx-revealed"), e && (e(), e = null));
    });
  } catch (e) {
    console.error("[effects] scroll reveal disabled:", e), t.classList.add("fx-reveal", "fx-revealed");
  }
}
function V(t = document) {
  t.querySelectorAll("[data-reveal]").forEach((e) => {
    e.dataset.revealInit || (e.dataset.revealInit = "1", wt(e));
  });
}
function R() {
  ct(document), V(document);
}
document.readyState !== "loading" ? R() : document.addEventListener("DOMContentLoaded", R);
document.body.addEventListener("htmx:afterSwap", (t) => V(t.target));
