var H = 0, j = 0, O = 0, ne = 1e3, ft, F, st = 0, L = 0, yt = 0, Y = typeof performance == "object" && performance.now ? performance : Date, re = typeof window == "object" && window.requestAnimationFrame ? window.requestAnimationFrame.bind(window) : function(t) {
  setTimeout(t, 17);
};
function ie() {
  return L || (re(ke), L = Y.now() + yt);
}
function ke() {
  L = 0;
}
function Nt() {
  this._call = this._time = this._next = null;
}
Nt.prototype = ae.prototype = {
  constructor: Nt,
  restart: function(t, e, n) {
    if (typeof t != "function") throw new TypeError("callback is not a function");
    n = (n == null ? ie() : +n) + (e == null ? 0 : +e), !this._next && F !== this && (F ? F._next = this : ft = this, F = this), this._call = t, this._time = n, $t();
  },
  stop: function() {
    this._call && (this._call = null, this._time = 1 / 0, $t());
  }
};
function ae(t, e, n) {
  var r = new Nt();
  return r.restart(t, e, n), r;
}
function Ee() {
  ie(), ++H;
  for (var t = ft, e; t; )
    (e = L - t._time) >= 0 && t._call.call(void 0, e), t = t._next;
  --H;
}
function Ct() {
  L = (st = Y.now()) + yt, H = j = 0;
  try {
    Ee();
  } finally {
    H = 0, Ae(), L = 0;
  }
}
function Se() {
  var t = Y.now(), e = t - st;
  e > ne && (yt -= e, st = t);
}
function Ae() {
  for (var t, e = ft, n, r = 1 / 0; e; )
    e._call ? (r > e._time && (r = e._time), t = e, e = e._next) : (n = e._next, e._next = null, e = t ? t._next = n : ft = n);
  F = t, $t(r);
}
function $t(t) {
  if (!H) {
    j && (j = clearTimeout(j));
    var e = t - L;
    e > 24 ? (t < 1 / 0 && (j = setTimeout(Ct, t - Y.now() - yt)), O && (O = clearInterval(O))) : (O || (st = Y.now(), O = setInterval(Se, ne)), H = 1, re(Ct));
  }
}
const P = /* @__PURE__ */ new Set();
let B = null;
function oe() {
  B || P.size === 0 || (B = ae((t) => {
    P.forEach((e) => {
      try {
        e(t);
      } catch (n) {
        console.error("[effects] tick subscriber threw; removing it:", n), P.delete(e);
      }
    });
  }));
}
function fe() {
  B && (B.stop(), B = null);
}
function se(t) {
  return P.add(t), oe(), () => {
    P.delete(t), P.size === 0 && fe();
  };
}
typeof document < "u" && document.addEventListener("visibilitychange", () => {
  document.hidden ? fe() : oe();
});
const Ot = 0.15, U = /* @__PURE__ */ new Set(), y = { x: -9999, y: -9999, sx: -9999, sy: -9999 };
let D = null, ct = !1;
function ce(t) {
  y.sx === -9999 && (y.sx = t.clientX, y.sy = t.clientY), y.x = t.clientX, y.y = t.clientY;
}
function ue() {
  U.size === 0 && (ct && (window.removeEventListener("mousemove", ce), ct = !1), D && (D(), D = null));
}
function Le() {
  y.sx += (y.x - y.sx) * Ot, y.sy += (y.y - y.sy) * Ot, U.forEach((t) => {
    try {
      t(y);
    } catch (e) {
      console.error("[effects] pointer subscriber threw; removing it:", e), U.delete(t), ue();
    }
  });
}
function Lt(t) {
  return U.add(t), ct || (window.addEventListener("mousemove", ce), ct = !0), D || (D = se(Le)), () => {
    U.delete(t), ue();
  };
}
function K() {
  try {
    return typeof window > "u" || typeof window.matchMedia != "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "static" : window.matchMedia("(pointer: coarse)").matches ? "ambient" : "full";
  } catch {
    return "static";
  }
}
const Ie = 70, _e = 0.35;
function Re(t) {
  const e = K();
  if (e !== "static")
    try {
      let o = function() {
        i = t.width = window.innerWidth, a = t.height = window.innerHeight;
      };
      var n = o;
      const r = t.getContext("2d");
      if (!r) return;
      let i = 0, a = 0;
      o();
      const f = window.innerWidth < 700 ? 25 : 50, c = Array.from({ length: f }, () => ({
        x: Math.random() * i,
        y: Math.random() * a,
        r: Math.random() * 1.6 + 0.4,
        vx: (Math.random() - 0.5) * 0.15,
        vy: -(Math.random() * 0.2 + 0.05),
        a: Math.random() * 0.4 + 0.1
      })), s = { sx: -9999, sy: -9999 };
      e === "full" && Lt((l) => {
        s.sx = l.sx, s.sy = l.sy;
      }), se(() => {
        r.clearRect(0, 0, i, a);
        const l = Math.max(_e, 1 - window.scrollY / (a * 2));
        c.forEach((u) => {
          const d = u.x - s.sx, p = u.y - s.sy, w = Math.hypot(d, p);
          w < Ie && w > 0 && (u.x += d / w * 1.1, u.y += p / w * 1.1), u.x += u.vx, u.y += u.vy, u.y < -5 && (u.y = a + 5, u.x = Math.random() * i), u.x < -5 && (u.x = i + 5), u.x > i + 5 && (u.x = -5), r.beginPath(), r.arc(u.x, u.y, u.r, 0, Math.PI * 2), r.fillStyle = `rgba(201, 168, 76, ${u.a * l})`, r.fill();
        });
      }), window.addEventListener("resize", o);
    } catch (r) {
      console.error("[effects] ambient dust disabled:", r);
    }
}
function Pe(t = document) {
  const e = t.querySelector("[data-ambient-dust]");
  !e || e.dataset.dustInit || (e.dataset.dustInit = "1", Re(e));
}
const qe = 0.6, G = /* @__PURE__ */ new Map();
let nt = !1, q = 0, E = null;
function le(t, e, n) {
  const r = t.getBoundingClientRect(), i = (n - r.top) / (n * qe), a = Math.max(0, Math.min(1, i));
  a !== e.progress && (e.progress = a, e.cb(a));
}
function Te() {
  q = 0;
  const t = window.innerHeight;
  G.forEach((e, n) => {
    e.active && le(n, e, t);
  });
}
function _() {
  q || (q = requestAnimationFrame(Te));
}
function He() {
  E || typeof IntersectionObserver > "u" || (E = new IntersectionObserver(
    (t) => {
      t.forEach((e) => {
        const n = G.get(e.target);
        n && (n.active = e.isIntersecting);
      }), _();
    },
    { rootMargin: "20% 0px" }
  ));
}
function ze(t, e) {
  He();
  const n = { cb: e, progress: -1, active: !E };
  return G.set(t, n), E && E.observe(t), nt || (window.addEventListener("scroll", _, { passive: !0 }), window.addEventListener("resize", _), nt = !0), le(t, n, window.innerHeight), _(), () => {
    G.delete(t), E && E.unobserve(t), G.size === 0 && (nt && (window.removeEventListener("scroll", _), window.removeEventListener("resize", _), nt = !1), q && (cancelAnimationFrame(q), q = 0));
  };
}
const Ce = 0.3;
function Oe(t) {
  try {
    if (K() === "static") {
      t.classList.add("fx-reveal", "fx-revealed");
      return;
    }
    t.classList.add("fx-reveal");
    let e = ze(t, (n) => {
      t.style.setProperty("--fx-draw", String(n)), t.style.setProperty("--fx-fade", String(Math.min(n / Ce, 1))), n >= 1 && (t.classList.add("fx-revealed"), e && (e(), e = null));
    });
  } catch (e) {
    console.error("[effects] scroll reveal disabled:", e), t.classList.add("fx-reveal", "fx-revealed");
  }
}
function de(t = document) {
  t.querySelectorAll("[data-reveal]").forEach((e) => {
    e.dataset.revealInit || (e.dataset.revealInit = "1", Oe(e));
  });
}
const he = "fkc-neon-power-on", je = 200, Fe = 45, Be = 2500, De = [
  { at: 1300, opacity: "0.7" },
  { at: 1420, opacity: "0.15" },
  { at: 1500, opacity: "0.9" },
  { at: 1610, opacity: "0.3" },
  { at: 1700, opacity: "1" },
  { at: 1780, opacity: "0.5" },
  { at: 1900, opacity: "1" }
];
function Ge() {
  try {
    return sessionStorage.getItem(he) === "1";
  } catch {
    return !1;
  }
}
function Ye() {
  try {
    sessionStorage.setItem(he, "1");
  } catch {
  }
}
function Ue() {
  try {
    return K() === "static" || Ge();
  } catch {
    return !0;
  }
}
function wt(t) {
  t.classList.remove("hero--pre-show"), t.classList.add("hero--live"), t.dispatchEvent(new CustomEvent("neon:live"));
}
function Xe(t) {
  try {
    if (Ue()) {
      wt(t);
      return;
    }
    t.classList.add("hero--pre-show");
    const e = t.querySelector(".marquee-title");
    e && (e.style.opacity = "0.06"), t.querySelectorAll(".bulb").forEach((n, r) => {
      setTimeout(() => n.classList.add("bulb--lit"), je + r * Fe);
    }), e && De.forEach((n) => {
      setTimeout(() => {
        e.style.opacity = n.opacity;
      }, n.at);
    }), setTimeout(() => {
      e && (e.style.opacity = ""), t.querySelectorAll(".bulb--lit").forEach((n) => {
        n.classList.remove("bulb--lit");
      }), Ye(), wt(t);
    }, Be);
  } catch (e) {
    console.error("[effects] neon power-on disabled:", e), wt(t);
  }
}
function We(t = document) {
  t.querySelectorAll("[data-neon]").forEach((e) => {
    e.dataset.neonInit || (e.dataset.neonInit = "1", Xe(e));
  });
}
function ot(t, e) {
  return t == null || e == null ? NaN : t < e ? -1 : t > e ? 1 : t >= e ? 0 : NaN;
}
function Ve(t, e) {
  return t == null || e == null ? NaN : e < t ? -1 : e > t ? 1 : e >= t ? 0 : NaN;
}
function xe(t) {
  let e, n, r;
  t.length !== 2 ? (e = ot, n = (f, c) => ot(t(f), c), r = (f, c) => t(f) - c) : (e = t === ot || t === Ve ? t : Ke, n = t, r = t);
  function i(f, c, s = 0, l = f.length) {
    if (s < l) {
      if (e(c, c) !== 0) return l;
      do {
        const u = s + l >>> 1;
        n(f[u], c) < 0 ? s = u + 1 : l = u;
      } while (s < l);
    }
    return s;
  }
  function a(f, c, s = 0, l = f.length) {
    if (s < l) {
      if (e(c, c) !== 0) return l;
      do {
        const u = s + l >>> 1;
        n(f[u], c) <= 0 ? s = u + 1 : l = u;
      } while (s < l);
    }
    return s;
  }
  function o(f, c, s = 0, l = f.length) {
    const u = i(f, c, s, l - 1);
    return u > s && r(f[u - 1], c) > -r(f[u], c) ? u - 1 : u;
  }
  return { left: i, center: o, right: a };
}
function Ke() {
  return 0;
}
function Ze(t) {
  return t === null ? NaN : +t;
}
const Je = xe(ot), Qe = Je.right;
xe(Ze).center;
const tn = Math.sqrt(50), en = Math.sqrt(10), nn = Math.sqrt(2);
function ut(t, e, n) {
  const r = (e - t) / Math.max(0, n), i = Math.floor(Math.log10(r)), a = r / Math.pow(10, i), o = a >= tn ? 10 : a >= en ? 5 : a >= nn ? 2 : 1;
  let f, c, s;
  return i < 0 ? (s = Math.pow(10, -i) / o, f = Math.round(t * s), c = Math.round(e * s), f / s < t && ++f, c / s > e && --c, s = -s) : (s = Math.pow(10, i) * o, f = Math.round(t / s), c = Math.round(e / s), f * s < t && ++f, c * s > e && --c), c < f && 0.5 <= n && n < 2 ? ut(t, e, n * 2) : [f, c, s];
}
function rn(t, e, n) {
  if (e = +e, t = +t, n = +n, !(n > 0)) return [];
  if (t === e) return [t];
  const r = e < t, [i, a, o] = r ? ut(e, t, n) : ut(t, e, n);
  if (!(a >= i)) return [];
  const f = a - i + 1, c = new Array(f);
  if (r)
    if (o < 0) for (let s = 0; s < f; ++s) c[s] = (a - s) / -o;
    else for (let s = 0; s < f; ++s) c[s] = (a - s) * o;
  else if (o < 0) for (let s = 0; s < f; ++s) c[s] = (i + s) / -o;
  else for (let s = 0; s < f; ++s) c[s] = (i + s) * o;
  return c;
}
function kt(t, e, n) {
  return e = +e, t = +t, n = +n, ut(t, e, n)[2];
}
function an(t, e, n) {
  e = +e, t = +t, n = +n;
  const r = e < t, i = r ? kt(e, t, n) : kt(t, e, n);
  return (r ? -1 : 1) * (i < 0 ? 1 / -i : i);
}
function on(t, e) {
  switch (arguments.length) {
    case 0:
      break;
    case 1:
      this.range(t);
      break;
    default:
      this.range(e).domain(t);
      break;
  }
  return this;
}
function It(t, e, n) {
  t.prototype = e.prototype = n, n.constructor = t;
}
function ge(t, e) {
  var n = Object.create(t.prototype);
  for (var r in e) n[r] = e[r];
  return n;
}
function Z() {
}
var X = 0.7, lt = 1 / X, T = "\\s*([+-]?\\d+)\\s*", W = "\\s*([+-]?(?:\\d*\\.)?\\d+(?:[eE][+-]?\\d+)?)\\s*", v = "\\s*([+-]?(?:\\d*\\.)?\\d+(?:[eE][+-]?\\d+)?)%\\s*", fn = /^#([0-9a-f]{3,8})$/, sn = new RegExp(`^rgb\\(${T},${T},${T}\\)$`), cn = new RegExp(`^rgb\\(${v},${v},${v}\\)$`), un = new RegExp(`^rgba\\(${T},${T},${T},${W}\\)$`), ln = new RegExp(`^rgba\\(${v},${v},${v},${W}\\)$`), dn = new RegExp(`^hsl\\(${W},${v},${v}\\)$`), hn = new RegExp(`^hsla\\(${W},${v},${v},${W}\\)$`), jt = {
  aliceblue: 15792383,
  antiquewhite: 16444375,
  aqua: 65535,
  aquamarine: 8388564,
  azure: 15794175,
  beige: 16119260,
  bisque: 16770244,
  black: 0,
  blanchedalmond: 16772045,
  blue: 255,
  blueviolet: 9055202,
  brown: 10824234,
  burlywood: 14596231,
  cadetblue: 6266528,
  chartreuse: 8388352,
  chocolate: 13789470,
  coral: 16744272,
  cornflowerblue: 6591981,
  cornsilk: 16775388,
  crimson: 14423100,
  cyan: 65535,
  darkblue: 139,
  darkcyan: 35723,
  darkgoldenrod: 12092939,
  darkgray: 11119017,
  darkgreen: 25600,
  darkgrey: 11119017,
  darkkhaki: 12433259,
  darkmagenta: 9109643,
  darkolivegreen: 5597999,
  darkorange: 16747520,
  darkorchid: 10040012,
  darkred: 9109504,
  darksalmon: 15308410,
  darkseagreen: 9419919,
  darkslateblue: 4734347,
  darkslategray: 3100495,
  darkslategrey: 3100495,
  darkturquoise: 52945,
  darkviolet: 9699539,
  deeppink: 16716947,
  deepskyblue: 49151,
  dimgray: 6908265,
  dimgrey: 6908265,
  dodgerblue: 2003199,
  firebrick: 11674146,
  floralwhite: 16775920,
  forestgreen: 2263842,
  fuchsia: 16711935,
  gainsboro: 14474460,
  ghostwhite: 16316671,
  gold: 16766720,
  goldenrod: 14329120,
  gray: 8421504,
  green: 32768,
  greenyellow: 11403055,
  grey: 8421504,
  honeydew: 15794160,
  hotpink: 16738740,
  indianred: 13458524,
  indigo: 4915330,
  ivory: 16777200,
  khaki: 15787660,
  lavender: 15132410,
  lavenderblush: 16773365,
  lawngreen: 8190976,
  lemonchiffon: 16775885,
  lightblue: 11393254,
  lightcoral: 15761536,
  lightcyan: 14745599,
  lightgoldenrodyellow: 16448210,
  lightgray: 13882323,
  lightgreen: 9498256,
  lightgrey: 13882323,
  lightpink: 16758465,
  lightsalmon: 16752762,
  lightseagreen: 2142890,
  lightskyblue: 8900346,
  lightslategray: 7833753,
  lightslategrey: 7833753,
  lightsteelblue: 11584734,
  lightyellow: 16777184,
  lime: 65280,
  limegreen: 3329330,
  linen: 16445670,
  magenta: 16711935,
  maroon: 8388608,
  mediumaquamarine: 6737322,
  mediumblue: 205,
  mediumorchid: 12211667,
  mediumpurple: 9662683,
  mediumseagreen: 3978097,
  mediumslateblue: 8087790,
  mediumspringgreen: 64154,
  mediumturquoise: 4772300,
  mediumvioletred: 13047173,
  midnightblue: 1644912,
  mintcream: 16121850,
  mistyrose: 16770273,
  moccasin: 16770229,
  navajowhite: 16768685,
  navy: 128,
  oldlace: 16643558,
  olive: 8421376,
  olivedrab: 7048739,
  orange: 16753920,
  orangered: 16729344,
  orchid: 14315734,
  palegoldenrod: 15657130,
  palegreen: 10025880,
  paleturquoise: 11529966,
  palevioletred: 14381203,
  papayawhip: 16773077,
  peachpuff: 16767673,
  peru: 13468991,
  pink: 16761035,
  plum: 14524637,
  powderblue: 11591910,
  purple: 8388736,
  rebeccapurple: 6697881,
  red: 16711680,
  rosybrown: 12357519,
  royalblue: 4286945,
  saddlebrown: 9127187,
  salmon: 16416882,
  sandybrown: 16032864,
  seagreen: 3050327,
  seashell: 16774638,
  sienna: 10506797,
  silver: 12632256,
  skyblue: 8900331,
  slateblue: 6970061,
  slategray: 7372944,
  slategrey: 7372944,
  snow: 16775930,
  springgreen: 65407,
  steelblue: 4620980,
  tan: 13808780,
  teal: 32896,
  thistle: 14204888,
  tomato: 16737095,
  turquoise: 4251856,
  violet: 15631086,
  wheat: 16113331,
  white: 16777215,
  whitesmoke: 16119285,
  yellow: 16776960,
  yellowgreen: 10145074
};
It(Z, V, {
  copy(t) {
    return Object.assign(new this.constructor(), this, t);
  },
  displayable() {
    return this.rgb().displayable();
  },
  hex: Ft,
  // Deprecated! Use color.formatHex.
  formatHex: Ft,
  formatHex8: xn,
  formatHsl: gn,
  formatRgb: Bt,
  toString: Bt
});
function Ft() {
  return this.rgb().formatHex();
}
function xn() {
  return this.rgb().formatHex8();
}
function gn() {
  return me(this).formatHsl();
}
function Bt() {
  return this.rgb().formatRgb();
}
function V(t) {
  var e, n;
  return t = (t + "").trim().toLowerCase(), (e = fn.exec(t)) ? (n = e[1].length, e = parseInt(e[1], 16), n === 6 ? Dt(e) : n === 3 ? new x(e >> 8 & 15 | e >> 4 & 240, e >> 4 & 15 | e & 240, (e & 15) << 4 | e & 15, 1) : n === 8 ? rt(e >> 24 & 255, e >> 16 & 255, e >> 8 & 255, (e & 255) / 255) : n === 4 ? rt(e >> 12 & 15 | e >> 8 & 240, e >> 8 & 15 | e >> 4 & 240, e >> 4 & 15 | e & 240, ((e & 15) << 4 | e & 15) / 255) : null) : (e = sn.exec(t)) ? new x(e[1], e[2], e[3], 1) : (e = cn.exec(t)) ? new x(e[1] * 255 / 100, e[2] * 255 / 100, e[3] * 255 / 100, 1) : (e = un.exec(t)) ? rt(e[1], e[2], e[3], e[4]) : (e = ln.exec(t)) ? rt(e[1] * 255 / 100, e[2] * 255 / 100, e[3] * 255 / 100, e[4]) : (e = dn.exec(t)) ? Ut(e[1], e[2] / 100, e[3] / 100, 1) : (e = hn.exec(t)) ? Ut(e[1], e[2] / 100, e[3] / 100, e[4]) : jt.hasOwnProperty(t) ? Dt(jt[t]) : t === "transparent" ? new x(NaN, NaN, NaN, 0) : null;
}
function Dt(t) {
  return new x(t >> 16 & 255, t >> 8 & 255, t & 255, 1);
}
function rt(t, e, n, r) {
  return r <= 0 && (t = e = n = NaN), new x(t, e, n, r);
}
function mn(t) {
  return t instanceof Z || (t = V(t)), t ? (t = t.rgb(), new x(t.r, t.g, t.b, t.opacity)) : new x();
}
function Et(t, e, n, r) {
  return arguments.length === 1 ? mn(t) : new x(t, e, n, r ?? 1);
}
function x(t, e, n, r) {
  this.r = +t, this.g = +e, this.b = +n, this.opacity = +r;
}
It(x, Et, ge(Z, {
  brighter(t) {
    return t = t == null ? lt : Math.pow(lt, t), new x(this.r * t, this.g * t, this.b * t, this.opacity);
  },
  darker(t) {
    return t = t == null ? X : Math.pow(X, t), new x(this.r * t, this.g * t, this.b * t, this.opacity);
  },
  rgb() {
    return this;
  },
  clamp() {
    return new x(A(this.r), A(this.g), A(this.b), dt(this.opacity));
  },
  displayable() {
    return -0.5 <= this.r && this.r < 255.5 && -0.5 <= this.g && this.g < 255.5 && -0.5 <= this.b && this.b < 255.5 && 0 <= this.opacity && this.opacity <= 1;
  },
  hex: Gt,
  // Deprecated! Use color.formatHex.
  formatHex: Gt,
  formatHex8: yn,
  formatRgb: Yt,
  toString: Yt
}));
function Gt() {
  return `#${S(this.r)}${S(this.g)}${S(this.b)}`;
}
function yn() {
  return `#${S(this.r)}${S(this.g)}${S(this.b)}${S((isNaN(this.opacity) ? 1 : this.opacity) * 255)}`;
}
function Yt() {
  const t = dt(this.opacity);
  return `${t === 1 ? "rgb(" : "rgba("}${A(this.r)}, ${A(this.g)}, ${A(this.b)}${t === 1 ? ")" : `, ${t})`}`;
}
function dt(t) {
  return isNaN(t) ? 1 : Math.max(0, Math.min(1, t));
}
function A(t) {
  return Math.max(0, Math.min(255, Math.round(t) || 0));
}
function S(t) {
  return t = A(t), (t < 16 ? "0" : "") + t.toString(16);
}
function Ut(t, e, n, r) {
  return r <= 0 ? t = e = n = NaN : n <= 0 || n >= 1 ? t = e = NaN : e <= 0 && (t = NaN), new b(t, e, n, r);
}
function me(t) {
  if (t instanceof b) return new b(t.h, t.s, t.l, t.opacity);
  if (t instanceof Z || (t = V(t)), !t) return new b();
  if (t instanceof b) return t;
  t = t.rgb();
  var e = t.r / 255, n = t.g / 255, r = t.b / 255, i = Math.min(e, n, r), a = Math.max(e, n, r), o = NaN, f = a - i, c = (a + i) / 2;
  return f ? (e === a ? o = (n - r) / f + (n < r) * 6 : n === a ? o = (r - e) / f + 2 : o = (e - n) / f + 4, f /= c < 0.5 ? a + i : 2 - a - i, o *= 60) : f = c > 0 && c < 1 ? 0 : o, new b(o, f, c, t.opacity);
}
function pn(t, e, n, r) {
  return arguments.length === 1 ? me(t) : new b(t, e, n, r ?? 1);
}
function b(t, e, n, r) {
  this.h = +t, this.s = +e, this.l = +n, this.opacity = +r;
}
It(b, pn, ge(Z, {
  brighter(t) {
    return t = t == null ? lt : Math.pow(lt, t), new b(this.h, this.s, this.l * t, this.opacity);
  },
  darker(t) {
    return t = t == null ? X : Math.pow(X, t), new b(this.h, this.s, this.l * t, this.opacity);
  },
  rgb() {
    var t = this.h % 360 + (this.h < 0) * 360, e = isNaN(t) || isNaN(this.s) ? 0 : this.s, n = this.l, r = n + (n < 0.5 ? n : 1 - n) * e, i = 2 * n - r;
    return new x(
      vt(t >= 240 ? t - 240 : t + 120, i, r),
      vt(t, i, r),
      vt(t < 120 ? t + 240 : t - 120, i, r),
      this.opacity
    );
  },
  clamp() {
    return new b(Xt(this.h), it(this.s), it(this.l), dt(this.opacity));
  },
  displayable() {
    return (0 <= this.s && this.s <= 1 || isNaN(this.s)) && 0 <= this.l && this.l <= 1 && 0 <= this.opacity && this.opacity <= 1;
  },
  formatHsl() {
    const t = dt(this.opacity);
    return `${t === 1 ? "hsl(" : "hsla("}${Xt(this.h)}, ${it(this.s) * 100}%, ${it(this.l) * 100}%${t === 1 ? ")" : `, ${t})`}`;
  }
}));
function Xt(t) {
  return t = (t || 0) % 360, t < 0 ? t + 360 : t;
}
function it(t) {
  return Math.max(0, Math.min(1, t || 0));
}
function vt(t, e, n) {
  return (t < 60 ? e + (n - e) * t / 60 : t < 180 ? n : t < 240 ? e + (n - e) * (240 - t) / 60 : e) * 255;
}
const _t = (t) => () => t;
function bn(t, e) {
  return function(n) {
    return t + n * e;
  };
}
function wn(t, e, n) {
  return t = Math.pow(t, n), e = Math.pow(e, n) - t, n = 1 / n, function(r) {
    return Math.pow(t + r * e, n);
  };
}
function vn(t) {
  return (t = +t) == 1 ? ye : function(e, n) {
    return n - e ? wn(e, n, t) : _t(isNaN(e) ? n : e);
  };
}
function ye(t, e) {
  var n = e - t;
  return n ? bn(t, n) : _t(isNaN(t) ? e : t);
}
const Wt = (function t(e) {
  var n = vn(e);
  function r(i, a) {
    var o = n((i = Et(i)).r, (a = Et(a)).r), f = n(i.g, a.g), c = n(i.b, a.b), s = ye(i.opacity, a.opacity);
    return function(l) {
      return i.r = o(l), i.g = f(l), i.b = c(l), i.opacity = s(l), i + "";
    };
  }
  return r.gamma = t, r;
})(1);
function Mn(t, e) {
  e || (e = []);
  var n = t ? Math.min(e.length, t.length) : 0, r = e.slice(), i;
  return function(a) {
    for (i = 0; i < n; ++i) r[i] = t[i] * (1 - a) + e[i] * a;
    return r;
  };
}
function Nn(t) {
  return ArrayBuffer.isView(t) && !(t instanceof DataView);
}
function $n(t, e) {
  var n = e ? e.length : 0, r = t ? Math.min(n, t.length) : 0, i = new Array(r), a = new Array(n), o;
  for (o = 0; o < r; ++o) i[o] = Rt(t[o], e[o]);
  for (; o < n; ++o) a[o] = e[o];
  return function(f) {
    for (o = 0; o < r; ++o) a[o] = i[o](f);
    return a;
  };
}
function kn(t, e) {
  var n = /* @__PURE__ */ new Date();
  return t = +t, e = +e, function(r) {
    return n.setTime(t * (1 - r) + e * r), n;
  };
}
function ht(t, e) {
  return t = +t, e = +e, function(n) {
    return t * (1 - n) + e * n;
  };
}
function En(t, e) {
  var n = {}, r = {}, i;
  (t === null || typeof t != "object") && (t = {}), (e === null || typeof e != "object") && (e = {});
  for (i in e)
    i in t ? n[i] = Rt(t[i], e[i]) : r[i] = e[i];
  return function(a) {
    for (i in n) r[i] = n[i](a);
    return r;
  };
}
var St = /[-+]?(?:\d+\.?\d*|\.?\d+)(?:[eE][-+]?\d+)?/g, Mt = new RegExp(St.source, "g");
function Sn(t) {
  return function() {
    return t;
  };
}
function An(t) {
  return function(e) {
    return t(e) + "";
  };
}
function Ln(t, e) {
  var n = St.lastIndex = Mt.lastIndex = 0, r, i, a, o = -1, f = [], c = [];
  for (t = t + "", e = e + ""; (r = St.exec(t)) && (i = Mt.exec(e)); )
    (a = i.index) > n && (a = e.slice(n, a), f[o] ? f[o] += a : f[++o] = a), (r = r[0]) === (i = i[0]) ? f[o] ? f[o] += i : f[++o] = i : (f[++o] = null, c.push({ i: o, x: ht(r, i) })), n = Mt.lastIndex;
  return n < e.length && (a = e.slice(n), f[o] ? f[o] += a : f[++o] = a), f.length < 2 ? c[0] ? An(c[0].x) : Sn(e) : (e = c.length, function(s) {
    for (var l = 0, u; l < e; ++l) f[(u = c[l]).i] = u.x(s);
    return f.join("");
  });
}
function Rt(t, e) {
  var n = typeof e, r;
  return e == null || n === "boolean" ? _t(e) : (n === "number" ? ht : n === "string" ? (r = V(e)) ? (e = r, Wt) : Ln : e instanceof V ? Wt : e instanceof Date ? kn : Nn(e) ? Mn : Array.isArray(e) ? $n : typeof e.valueOf != "function" && typeof e.toString != "function" || isNaN(e) ? En : ht)(t, e);
}
function In(t, e) {
  return t = +t, e = +e, function(n) {
    return Math.round(t * (1 - n) + e * n);
  };
}
function _n(t) {
  return function() {
    return t;
  };
}
function Rn(t) {
  return +t;
}
var Vt = [0, 1];
function R(t) {
  return t;
}
function At(t, e) {
  return (e -= t = +t) ? function(n) {
    return (n - t) / e;
  } : _n(isNaN(e) ? NaN : 0.5);
}
function Pn(t, e) {
  var n;
  return t > e && (n = t, t = e, e = n), function(r) {
    return Math.max(t, Math.min(e, r));
  };
}
function qn(t, e, n) {
  var r = t[0], i = t[1], a = e[0], o = e[1];
  return i < r ? (r = At(i, r), a = n(o, a)) : (r = At(r, i), a = n(a, o)), function(f) {
    return a(r(f));
  };
}
function Tn(t, e, n) {
  var r = Math.min(t.length, e.length) - 1, i = new Array(r), a = new Array(r), o = -1;
  for (t[r] < t[0] && (t = t.slice().reverse(), e = e.slice().reverse()); ++o < r; )
    i[o] = At(t[o], t[o + 1]), a[o] = n(e[o], e[o + 1]);
  return function(f) {
    var c = Qe(t, f, 1, r) - 1;
    return a[c](i[c](f));
  };
}
function Hn(t, e) {
  return e.domain(t.domain()).range(t.range()).interpolate(t.interpolate()).clamp(t.clamp()).unknown(t.unknown());
}
function zn() {
  var t = Vt, e = Vt, n = Rt, r, i, a, o = R, f, c, s;
  function l() {
    var d = Math.min(t.length, e.length);
    return o !== R && (o = Pn(t[0], t[d - 1])), f = d > 2 ? Tn : qn, c = s = null, u;
  }
  function u(d) {
    return d == null || isNaN(d = +d) ? a : (c || (c = f(t.map(r), e, n)))(r(o(d)));
  }
  return u.invert = function(d) {
    return o(i((s || (s = f(e, t.map(r), ht)))(d)));
  }, u.domain = function(d) {
    return arguments.length ? (t = Array.from(d, Rn), l()) : t.slice();
  }, u.range = function(d) {
    return arguments.length ? (e = Array.from(d), l()) : e.slice();
  }, u.rangeRound = function(d) {
    return e = Array.from(d), n = In, l();
  }, u.clamp = function(d) {
    return arguments.length ? (o = d ? !0 : R, l()) : o !== R;
  }, u.interpolate = function(d) {
    return arguments.length ? (n = d, l()) : n;
  }, u.unknown = function(d) {
    return arguments.length ? (a = d, u) : a;
  }, function(d, p) {
    return r = d, i = p, l();
  };
}
function Cn() {
  return zn()(R, R);
}
function On(t) {
  return Math.abs(t = Math.round(t)) >= 1e21 ? t.toLocaleString("en").replace(/,/g, "") : t.toString(10);
}
function xt(t, e) {
  if (!isFinite(t) || t === 0) return null;
  var n = (t = e ? t.toExponential(e - 1) : t.toExponential()).indexOf("e"), r = t.slice(0, n);
  return [
    r.length > 1 ? r[0] + r.slice(2) : r,
    +t.slice(n + 1)
  ];
}
function z(t) {
  return t = xt(Math.abs(t)), t ? t[1] : NaN;
}
function jn(t, e) {
  return function(n, r) {
    for (var i = n.length, a = [], o = 0, f = t[0], c = 0; i > 0 && f > 0 && (c + f + 1 > r && (f = Math.max(1, r - c)), a.push(n.substring(i -= f, i + f)), !((c += f + 1) > r)); )
      f = t[o = (o + 1) % t.length];
    return a.reverse().join(e);
  };
}
function Fn(t) {
  return function(e) {
    return e.replace(/[0-9]/g, function(n) {
      return t[+n];
    });
  };
}
var Bn = /^(?:(.)?([<>=^]))?([+\-( ])?([$#])?(0)?(\d+)?(,)?(\.\d+)?(~)?([a-z%])?$/i;
function gt(t) {
  if (!(e = Bn.exec(t))) throw new Error("invalid format: " + t);
  var e;
  return new Pt({
    fill: e[1],
    align: e[2],
    sign: e[3],
    symbol: e[4],
    zero: e[5],
    width: e[6],
    comma: e[7],
    precision: e[8] && e[8].slice(1),
    trim: e[9],
    type: e[10]
  });
}
gt.prototype = Pt.prototype;
function Pt(t) {
  this.fill = t.fill === void 0 ? " " : t.fill + "", this.align = t.align === void 0 ? ">" : t.align + "", this.sign = t.sign === void 0 ? "-" : t.sign + "", this.symbol = t.symbol === void 0 ? "" : t.symbol + "", this.zero = !!t.zero, this.width = t.width === void 0 ? void 0 : +t.width, this.comma = !!t.comma, this.precision = t.precision === void 0 ? void 0 : +t.precision, this.trim = !!t.trim, this.type = t.type === void 0 ? "" : t.type + "";
}
Pt.prototype.toString = function() {
  return this.fill + this.align + this.sign + this.symbol + (this.zero ? "0" : "") + (this.width === void 0 ? "" : Math.max(1, this.width | 0)) + (this.comma ? "," : "") + (this.precision === void 0 ? "" : "." + Math.max(0, this.precision | 0)) + (this.trim ? "~" : "") + this.type;
};
function Dn(t) {
  t: for (var e = t.length, n = 1, r = -1, i; n < e; ++n)
    switch (t[n]) {
      case ".":
        r = i = n;
        break;
      case "0":
        r === 0 && (r = n), i = n;
        break;
      default:
        if (!+t[n]) break t;
        r > 0 && (r = 0);
        break;
    }
  return r > 0 ? t.slice(0, r) + t.slice(i + 1) : t;
}
var mt;
function Gn(t, e) {
  var n = xt(t, e);
  if (!n) return mt = void 0, t.toPrecision(e);
  var r = n[0], i = n[1], a = i - (mt = Math.max(-8, Math.min(8, Math.floor(i / 3))) * 3) + 1, o = r.length;
  return a === o ? r : a > o ? r + new Array(a - o + 1).join("0") : a > 0 ? r.slice(0, a) + "." + r.slice(a) : "0." + new Array(1 - a).join("0") + xt(t, Math.max(0, e + a - 1))[0];
}
function Kt(t, e) {
  var n = xt(t, e);
  if (!n) return t + "";
  var r = n[0], i = n[1];
  return i < 0 ? "0." + new Array(-i).join("0") + r : r.length > i + 1 ? r.slice(0, i + 1) + "." + r.slice(i + 1) : r + new Array(i - r.length + 2).join("0");
}
const Zt = {
  "%": (t, e) => (t * 100).toFixed(e),
  b: (t) => Math.round(t).toString(2),
  c: (t) => t + "",
  d: On,
  e: (t, e) => t.toExponential(e),
  f: (t, e) => t.toFixed(e),
  g: (t, e) => t.toPrecision(e),
  o: (t) => Math.round(t).toString(8),
  p: (t, e) => Kt(t * 100, e),
  r: Kt,
  s: Gn,
  X: (t) => Math.round(t).toString(16).toUpperCase(),
  x: (t) => Math.round(t).toString(16)
};
function Jt(t) {
  return t;
}
var Qt = Array.prototype.map, te = ["y", "z", "a", "f", "p", "n", "µ", "m", "", "k", "M", "G", "T", "P", "E", "Z", "Y"];
function Yn(t) {
  var e = t.grouping === void 0 || t.thousands === void 0 ? Jt : jn(Qt.call(t.grouping, Number), t.thousands + ""), n = t.currency === void 0 ? "" : t.currency[0] + "", r = t.currency === void 0 ? "" : t.currency[1] + "", i = t.decimal === void 0 ? "." : t.decimal + "", a = t.numerals === void 0 ? Jt : Fn(Qt.call(t.numerals, String)), o = t.percent === void 0 ? "%" : t.percent + "", f = t.minus === void 0 ? "−" : t.minus + "", c = t.nan === void 0 ? "NaN" : t.nan + "";
  function s(u, d) {
    u = gt(u);
    var p = u.fill, w = u.align, M = u.sign, C = u.symbol, J = u.zero, pt = u.width, bt = u.comma, $ = u.precision, qt = u.trim, g = u.type;
    g === "n" ? (bt = !0, g = "g") : Zt[g] || ($ === void 0 && ($ = 12), qt = !0, g = "g"), (J || p === "0" && w === "=") && (J = !0, p = "0", w = "=");
    var Me = (d && d.prefix !== void 0 ? d.prefix : "") + (C === "$" ? n : C === "#" && /[boxX]/.test(g) ? "0" + g.toLowerCase() : ""), Ne = (C === "$" ? r : /[%p]/.test(g) ? o : "") + (d && d.suffix !== void 0 ? d.suffix : ""), Tt = Zt[g], $e = /[defgprs%]/.test(g);
    $ = $ === void 0 ? 6 : /[gprs]/.test(g) ? Math.max(1, Math.min(21, $)) : Math.max(0, Math.min(20, $));
    function Ht(h) {
      var k = Me, m = Ne, I, zt, Q;
      if (g === "c")
        m = Tt(h) + m, h = "";
      else {
        h = +h;
        var tt = h < 0 || 1 / h < 0;
        if (h = isNaN(h) ? c : Tt(Math.abs(h), $), qt && (h = Dn(h)), tt && +h == 0 && M !== "+" && (tt = !1), k = (tt ? M === "(" ? M : f : M === "-" || M === "(" ? "" : M) + k, m = (g === "s" && !isNaN(h) && mt !== void 0 ? te[8 + mt / 3] : "") + m + (tt && M === "(" ? ")" : ""), $e) {
          for (I = -1, zt = h.length; ++I < zt; )
            if (Q = h.charCodeAt(I), 48 > Q || Q > 57) {
              m = (Q === 46 ? i + h.slice(I + 1) : h.slice(I)) + m, h = h.slice(0, I);
              break;
            }
        }
      }
      bt && !J && (h = e(h, 1 / 0));
      var et = k.length + h.length + m.length, N = et < pt ? new Array(pt - et + 1).join(p) : "";
      switch (bt && J && (h = e(N + h, N.length ? pt - m.length : 1 / 0), N = ""), w) {
        case "<":
          h = k + h + m + N;
          break;
        case "=":
          h = k + N + h + m;
          break;
        case "^":
          h = N.slice(0, et = N.length >> 1) + k + h + m + N.slice(et);
          break;
        default:
          h = N + k + h + m;
          break;
      }
      return a(h);
    }
    return Ht.toString = function() {
      return u + "";
    }, Ht;
  }
  function l(u, d) {
    var p = Math.max(-8, Math.min(8, Math.floor(z(d) / 3))) * 3, w = Math.pow(10, -p), M = s((u = gt(u), u.type = "f", u), { suffix: te[8 + p / 3] });
    return function(C) {
      return M(w * C);
    };
  }
  return {
    format: s,
    formatPrefix: l
  };
}
var at, pe, be;
Un({
  thousands: ",",
  grouping: [3],
  currency: ["$", ""]
});
function Un(t) {
  return at = Yn(t), pe = at.format, be = at.formatPrefix, at;
}
function Xn(t) {
  return Math.max(0, -z(Math.abs(t)));
}
function Wn(t, e) {
  return Math.max(0, Math.max(-8, Math.min(8, Math.floor(z(e) / 3))) * 3 - z(Math.abs(t)));
}
function Vn(t, e) {
  return t = Math.abs(t), e = Math.abs(e) - t, Math.max(0, z(e) - z(t)) + 1;
}
function Kn(t, e, n, r) {
  var i = an(t, e, n), a;
  switch (r = gt(r ?? ",f"), r.type) {
    case "s": {
      var o = Math.max(Math.abs(t), Math.abs(e));
      return r.precision == null && !isNaN(a = Wn(i, o)) && (r.precision = a), be(r, o);
    }
    case "":
    case "e":
    case "g":
    case "p":
    case "r": {
      r.precision == null && !isNaN(a = Vn(i, Math.max(Math.abs(t), Math.abs(e)))) && (r.precision = a - (r.type === "e"));
      break;
    }
    case "f":
    case "%": {
      r.precision == null && !isNaN(a = Xn(i)) && (r.precision = a - (r.type === "%") * 2);
      break;
    }
  }
  return pe(r);
}
function Zn(t) {
  var e = t.domain;
  return t.ticks = function(n) {
    var r = e();
    return rn(r[0], r[r.length - 1], n ?? 10);
  }, t.tickFormat = function(n, r) {
    var i = e();
    return Kn(i[0], i[i.length - 1], n ?? 10, r);
  }, t.nice = function(n) {
    n == null && (n = 10);
    var r = e(), i = 0, a = r.length - 1, o = r[i], f = r[a], c, s, l = 10;
    for (f < o && (s = o, o = f, f = s, s = i, i = a, a = s); l-- > 0; ) {
      if (s = kt(o, f, n), s === c)
        return r[i] = o, r[a] = f, e(r);
      if (s > 0)
        o = Math.floor(o / s) * s, f = Math.ceil(f / s) * s;
      else if (s < 0)
        o = Math.ceil(o * s) / s, f = Math.floor(f * s) / s;
      else
        break;
      c = s;
    }
    return t;
  }, t;
}
function we() {
  var t = Cn();
  return t.copy = function() {
    return Hn(t, we());
  }, on.apply(t, arguments), Zn(t);
}
function Jn(t) {
  return --t * t * t + 1;
}
const Qn = 90;
function tr(t) {
  if (K() === "full")
    try {
      const e = Array.from(t.querySelectorAll(".bulb"));
      if (e.length === 0) return;
      const n = we().domain([Qn, 0]).range([0, 1]).clamp(!0);
      let r = null;
      const i = () => {
        r || (r = Lt((a) => {
          e.forEach((o) => {
            const f = o.getBoundingClientRect(), c = a.sx - (f.left + f.width / 2), s = a.sy - (f.top + f.height / 2), l = Jn(n(Math.hypot(c, s)));
            l > 0.01 ? (o.style.transform = `scale(${1 + 0.4 * l})`, o.style.boxShadow = `0 0 ${6 + 12 * l}px #fff4c0, 0 0 ${12 + 22 * l}px rgba(201, 168, 76, ${0.3 + 0.5 * l})`) : o.style.transform && (o.style.transform = "", o.style.boxShadow = "");
          });
        }));
      };
      t.classList.contains("hero--live") ? i() : t.addEventListener("neon:live", i, { once: !0 });
    } catch (e) {
      console.error("[effects] cursor bulbs disabled:", e);
    }
}
function er(t = document) {
  t.querySelectorAll("[data-cursor-bulbs]").forEach((e) => {
    e.dataset.cursorBulbsInit || (e.dataset.cursorBulbsInit = "1", tr(e));
  });
}
const nr = 4;
function rr(t, e = ":scope > article, :scope > a") {
  if (K() === "full")
    try {
      t.classList.add("fx-spotlight-grid");
      const n = document.createElement("div");
      n.className = "fx-spotlight", n.setAttribute("aria-hidden", "true"), t.appendChild(n);
      let r = !1;
      const i = () => t.querySelectorAll(e).forEach((a) => {
        a.classList.remove("fx-card--focus", "fx-card--dim"), a.style.transform = "";
      });
      Lt((a) => {
        const o = t.getBoundingClientRect(), f = a.sx >= o.left && a.sx <= o.right && a.sy >= o.top && a.sy <= o.bottom;
        if (t.classList.toggle("fx-spotlight-grid--active", f), !f) {
          r && (i(), r = !1);
          return;
        }
        r = !0, n.style.transform = `translate(${a.sx - o.left}px, ${a.sy - o.top}px)`, t.querySelectorAll(e).forEach((c) => {
          const s = c.getBoundingClientRect(), l = a.x >= s.left && a.x <= s.right && a.y >= s.top && a.y <= s.bottom;
          if (c.classList.toggle("fx-card--focus", l), c.classList.toggle("fx-card--dim", !l), l) {
            const u = s.left + s.width / 2, d = (a.sx - u) / (s.width / 2) * nr;
            c.style.transform = `translateY(-6px) perspective(800px) rotateY(${d}deg)`;
          } else
            c.style.transform = "";
        });
      });
    } catch (n) {
      console.error("[effects] card spotlight disabled:", n);
    }
}
function ve(t = document) {
  t.querySelectorAll("[data-spotlight]").forEach((e) => {
    e.dataset.spotlightInit || (e.dataset.spotlightInit = "1", rr(e));
  });
}
function ee() {
  Pe(document), de(document), We(document), er(document), ve(document);
}
document.readyState !== "loading" ? ee() : document.addEventListener("DOMContentLoaded", ee);
document.body.addEventListener("htmx:afterSwap", (t) => {
  de(t.target), ve(t.target);
});
