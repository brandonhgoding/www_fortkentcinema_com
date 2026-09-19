const B = /* @__PURE__ */ new Map();
let te = !1, R = 0, $ = null;
function tt(e, t, n) {
  const r = e.getBoundingClientRect(), i = (n - r.top) / (n * 0.6), a = Math.max(0, Math.min(1, i));
  a !== t.progress && (t.progress = a, t.cb(a));
}
function kt() {
  R = 0;
  const e = window.innerHeight;
  B.forEach((t, n) => {
    t.active && tt(n, t, e);
  });
}
function _() {
  R || (R = requestAnimationFrame(kt));
}
function $t() {
  $ || typeof IntersectionObserver > "u" || ($ = new IntersectionObserver(
    (e) => {
      e.forEach((t) => {
        const n = B.get(t.target);
        n && (n.active = t.isIntersecting);
      }), _();
    },
    { rootMargin: "20% 0px" }
  ));
}
function Et(e, t) {
  $t();
  const n = { cb: t, progress: -1, active: !$ };
  return B.set(e, n), $ && $.observe(e), te || (window.addEventListener("scroll", _, { passive: !0 }), window.addEventListener("resize", _), te = !0), tt(e, n, window.innerHeight), _(), () => {
    B.delete(e), $ && $.unobserve(e), B.size === 0 && (te && (window.removeEventListener("scroll", _), window.removeEventListener("resize", _), te = !1), R && (cancelAnimationFrame(R), R = 0));
  };
}
function ge() {
  try {
    return typeof window > "u" || typeof window.matchMedia != "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "static" : window.matchMedia("(pointer: coarse)").matches ? "ambient" : "full";
  } catch {
    return "static";
  }
}
const St = 0.3;
function At(e) {
  try {
    if (ge() === "static") {
      e.classList.add("fx-reveal", "fx-revealed");
      return;
    }
    e.classList.add("fx-reveal");
    let t = null, n = !1;
    t = Et(e, (r) => {
      e.style.setProperty("--fx-draw", String(r)), e.style.setProperty("--fx-fade", String(Math.min(r / St, 1))), r >= 1 && (e.classList.add("fx-revealed"), n = !0, t && (t(), t = null));
    }), n && t && (t(), t = null);
  } catch (t) {
    console.error("[effects] scroll reveal disabled:", t), e.classList.add("fx-reveal", "fx-revealed");
  }
}
function nt(e = document) {
  e.querySelectorAll("[data-reveal]").forEach((t) => {
    t.dataset.revealInit || (t.dataset.revealInit = "1", At(t));
  });
}
const rt = "fkc-neon-power-on", Lt = 200, _t = 45, It = 2500, Rt = [
  { at: 1300, opacity: "0.7" },
  { at: 1420, opacity: "0.15" },
  { at: 1500, opacity: "0.9" },
  { at: 1610, opacity: "0.3" },
  { at: 1700, opacity: "1" },
  { at: 1780, opacity: "0.5" },
  { at: 1900, opacity: "1" }
];
function Pt() {
  try {
    return sessionStorage.getItem(rt) === "1";
  } catch {
    return !1;
  }
}
function qt() {
  try {
    sessionStorage.setItem(rt, "1");
  } catch {
  }
}
function Tt() {
  try {
    return ge() === "static" || Pt();
  } catch {
    return !0;
  }
}
function we(e) {
  e.classList.remove("hero--pre-show"), e.classList.add("hero--live"), e.dispatchEvent(new CustomEvent("neon:live"));
}
function Ht(e) {
  try {
    if (Tt()) {
      we(e);
      return;
    }
    e.classList.add("hero--pre-show");
    const t = e.querySelector(".marquee-title");
    t && (t.style.opacity = "0.06"), e.querySelectorAll(".bulb").forEach((n, r) => {
      setTimeout(() => n.classList.add("bulb--lit"), Lt + r * _t);
    }), t && Rt.forEach((n) => {
      setTimeout(() => {
        t.style.opacity = n.opacity;
      }, n.at);
    }), setTimeout(() => {
      t && (t.style.opacity = ""), e.querySelectorAll(".bulb--lit").forEach((n) => {
        n.classList.remove("bulb--lit");
      }), qt(), we(e);
    }, It);
  } catch (t) {
    console.error("[effects] neon power-on disabled:", t), we(e);
  }
}
function Ot(e = document) {
  e.querySelectorAll("[data-neon]").forEach((t) => {
    t.dataset.neonInit || (t.dataset.neonInit = "1", Ht(t));
  });
}
function ae(e, t) {
  return e == null || t == null ? NaN : e < t ? -1 : e > t ? 1 : e >= t ? 0 : NaN;
}
function zt(e, t) {
  return e == null || t == null ? NaN : t < e ? -1 : t > e ? 1 : t >= e ? 0 : NaN;
}
function it(e) {
  let t, n, r;
  e.length !== 2 ? (t = ae, n = (f, c) => ae(e(f), c), r = (f, c) => e(f) - c) : (t = e === ae || e === zt ? e : Ct, n = e, r = e);
  function i(f, c, s = 0, l = f.length) {
    if (s < l) {
      if (t(c, c) !== 0) return l;
      do {
        const u = s + l >>> 1;
        n(f[u], c) < 0 ? s = u + 1 : l = u;
      } while (s < l);
    }
    return s;
  }
  function a(f, c, s = 0, l = f.length) {
    if (s < l) {
      if (t(c, c) !== 0) return l;
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
function Ct() {
  return 0;
}
function jt(e) {
  return e === null ? NaN : +e;
}
const Ft = it(ae), Bt = Ft.right;
it(jt).center;
const Dt = Math.sqrt(50), Gt = Math.sqrt(10), Yt = Math.sqrt(2);
function oe(e, t, n) {
  const r = (t - e) / Math.max(0, n), i = Math.floor(Math.log10(r)), a = r / Math.pow(10, i), o = a >= Dt ? 10 : a >= Gt ? 5 : a >= Yt ? 2 : 1;
  let f, c, s;
  return i < 0 ? (s = Math.pow(10, -i) / o, f = Math.round(e * s), c = Math.round(t * s), f / s < e && ++f, c / s > t && --c, s = -s) : (s = Math.pow(10, i) * o, f = Math.round(e / s), c = Math.round(t / s), f * s < e && ++f, c * s > t && --c), c < f && 0.5 <= n && n < 2 ? oe(e, t, n * 2) : [f, c, s];
}
function Xt(e, t, n) {
  if (t = +t, e = +e, n = +n, !(n > 0)) return [];
  if (e === t) return [e];
  const r = t < e, [i, a, o] = r ? oe(t, e, n) : oe(e, t, n);
  if (!(a >= i)) return [];
  const f = a - i + 1, c = new Array(f);
  if (r)
    if (o < 0) for (let s = 0; s < f; ++s) c[s] = (a - s) / -o;
    else for (let s = 0; s < f; ++s) c[s] = (a - s) * o;
  else if (o < 0) for (let s = 0; s < f; ++s) c[s] = (i + s) / -o;
  else for (let s = 0; s < f; ++s) c[s] = (i + s) * o;
  return c;
}
function Ne(e, t, n) {
  return t = +t, e = +e, n = +n, oe(e, t, n)[2];
}
function Ut(e, t, n) {
  t = +t, e = +e, n = +n;
  const r = t < e, i = r ? Ne(t, e, n) : Ne(e, t, n);
  return (r ? -1 : 1) * (i < 0 ? 1 / -i : i);
}
function Vt(e, t) {
  switch (arguments.length) {
    case 0:
      break;
    case 1:
      this.range(e);
      break;
    default:
      this.range(t).domain(e);
      break;
  }
  return this;
}
function Le(e, t, n) {
  e.prototype = t.prototype = n, n.constructor = e;
}
function at(e, t) {
  var n = Object.create(e.prototype);
  for (var r in t) n[r] = t[r];
  return n;
}
function W() {
}
var Y = 0.7, fe = 1 / Y, P = "\\s*([+-]?\\d+)\\s*", X = "\\s*([+-]?(?:\\d*\\.)?\\d+(?:[eE][+-]?\\d+)?)\\s*", b = "\\s*([+-]?(?:\\d*\\.)?\\d+(?:[eE][+-]?\\d+)?)%\\s*", Kt = /^#([0-9a-f]{3,8})$/, Wt = new RegExp(`^rgb\\(${P},${P},${P}\\)$`), Zt = new RegExp(`^rgb\\(${b},${b},${b}\\)$`), Jt = new RegExp(`^rgba\\(${P},${P},${P},${X}\\)$`), Qt = new RegExp(`^rgba\\(${b},${b},${b},${X}\\)$`), en = new RegExp(`^hsl\\(${X},${b},${b}\\)$`), tn = new RegExp(`^hsla\\(${X},${b},${b},${X}\\)$`), Oe = {
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
Le(W, U, {
  copy(e) {
    return Object.assign(new this.constructor(), this, e);
  },
  displayable() {
    return this.rgb().displayable();
  },
  hex: ze,
  // Deprecated! Use color.formatHex.
  formatHex: ze,
  formatHex8: nn,
  formatHsl: rn,
  formatRgb: Ce,
  toString: Ce
});
function ze() {
  return this.rgb().formatHex();
}
function nn() {
  return this.rgb().formatHex8();
}
function rn() {
  return ot(this).formatHsl();
}
function Ce() {
  return this.rgb().formatRgb();
}
function U(e) {
  var t, n;
  return e = (e + "").trim().toLowerCase(), (t = Kt.exec(e)) ? (n = t[1].length, t = parseInt(t[1], 16), n === 6 ? je(t) : n === 3 ? new m(t >> 8 & 15 | t >> 4 & 240, t >> 4 & 15 | t & 240, (t & 15) << 4 | t & 15, 1) : n === 8 ? ne(t >> 24 & 255, t >> 16 & 255, t >> 8 & 255, (t & 255) / 255) : n === 4 ? ne(t >> 12 & 15 | t >> 8 & 240, t >> 8 & 15 | t >> 4 & 240, t >> 4 & 15 | t & 240, ((t & 15) << 4 | t & 15) / 255) : null) : (t = Wt.exec(e)) ? new m(t[1], t[2], t[3], 1) : (t = Zt.exec(e)) ? new m(t[1] * 255 / 100, t[2] * 255 / 100, t[3] * 255 / 100, 1) : (t = Jt.exec(e)) ? ne(t[1], t[2], t[3], t[4]) : (t = Qt.exec(e)) ? ne(t[1] * 255 / 100, t[2] * 255 / 100, t[3] * 255 / 100, t[4]) : (t = en.exec(e)) ? De(t[1], t[2] / 100, t[3] / 100, 1) : (t = tn.exec(e)) ? De(t[1], t[2] / 100, t[3] / 100, t[4]) : Oe.hasOwnProperty(e) ? je(Oe[e]) : e === "transparent" ? new m(NaN, NaN, NaN, 0) : null;
}
function je(e) {
  return new m(e >> 16 & 255, e >> 8 & 255, e & 255, 1);
}
function ne(e, t, n, r) {
  return r <= 0 && (e = t = n = NaN), new m(e, t, n, r);
}
function an(e) {
  return e instanceof W || (e = U(e)), e ? (e = e.rgb(), new m(e.r, e.g, e.b, e.opacity)) : new m();
}
function ke(e, t, n, r) {
  return arguments.length === 1 ? an(e) : new m(e, t, n, r ?? 1);
}
function m(e, t, n, r) {
  this.r = +e, this.g = +t, this.b = +n, this.opacity = +r;
}
Le(m, ke, at(W, {
  brighter(e) {
    return e = e == null ? fe : Math.pow(fe, e), new m(this.r * e, this.g * e, this.b * e, this.opacity);
  },
  darker(e) {
    return e = e == null ? Y : Math.pow(Y, e), new m(this.r * e, this.g * e, this.b * e, this.opacity);
  },
  rgb() {
    return this;
  },
  clamp() {
    return new m(S(this.r), S(this.g), S(this.b), se(this.opacity));
  },
  displayable() {
    return -0.5 <= this.r && this.r < 255.5 && -0.5 <= this.g && this.g < 255.5 && -0.5 <= this.b && this.b < 255.5 && 0 <= this.opacity && this.opacity <= 1;
  },
  hex: Fe,
  // Deprecated! Use color.formatHex.
  formatHex: Fe,
  formatHex8: on,
  formatRgb: Be,
  toString: Be
}));
function Fe() {
  return `#${E(this.r)}${E(this.g)}${E(this.b)}`;
}
function on() {
  return `#${E(this.r)}${E(this.g)}${E(this.b)}${E((isNaN(this.opacity) ? 1 : this.opacity) * 255)}`;
}
function Be() {
  const e = se(this.opacity);
  return `${e === 1 ? "rgb(" : "rgba("}${S(this.r)}, ${S(this.g)}, ${S(this.b)}${e === 1 ? ")" : `, ${e})`}`;
}
function se(e) {
  return isNaN(e) ? 1 : Math.max(0, Math.min(1, e));
}
function S(e) {
  return Math.max(0, Math.min(255, Math.round(e) || 0));
}
function E(e) {
  return e = S(e), (e < 16 ? "0" : "") + e.toString(16);
}
function De(e, t, n, r) {
  return r <= 0 ? e = t = n = NaN : n <= 0 || n >= 1 ? e = t = NaN : t <= 0 && (e = NaN), new p(e, t, n, r);
}
function ot(e) {
  if (e instanceof p) return new p(e.h, e.s, e.l, e.opacity);
  if (e instanceof W || (e = U(e)), !e) return new p();
  if (e instanceof p) return e;
  e = e.rgb();
  var t = e.r / 255, n = e.g / 255, r = e.b / 255, i = Math.min(t, n, r), a = Math.max(t, n, r), o = NaN, f = a - i, c = (a + i) / 2;
  return f ? (t === a ? o = (n - r) / f + (n < r) * 6 : n === a ? o = (r - t) / f + 2 : o = (t - n) / f + 4, f /= c < 0.5 ? a + i : 2 - a - i, o *= 60) : f = c > 0 && c < 1 ? 0 : o, new p(o, f, c, e.opacity);
}
function fn(e, t, n, r) {
  return arguments.length === 1 ? ot(e) : new p(e, t, n, r ?? 1);
}
function p(e, t, n, r) {
  this.h = +e, this.s = +t, this.l = +n, this.opacity = +r;
}
Le(p, fn, at(W, {
  brighter(e) {
    return e = e == null ? fe : Math.pow(fe, e), new p(this.h, this.s, this.l * e, this.opacity);
  },
  darker(e) {
    return e = e == null ? Y : Math.pow(Y, e), new p(this.h, this.s, this.l * e, this.opacity);
  },
  rgb() {
    var e = this.h % 360 + (this.h < 0) * 360, t = isNaN(e) || isNaN(this.s) ? 0 : this.s, n = this.l, r = n + (n < 0.5 ? n : 1 - n) * t, i = 2 * n - r;
    return new m(
      ve(e >= 240 ? e - 240 : e + 120, i, r),
      ve(e, i, r),
      ve(e < 120 ? e + 240 : e - 120, i, r),
      this.opacity
    );
  },
  clamp() {
    return new p(Ge(this.h), re(this.s), re(this.l), se(this.opacity));
  },
  displayable() {
    return (0 <= this.s && this.s <= 1 || isNaN(this.s)) && 0 <= this.l && this.l <= 1 && 0 <= this.opacity && this.opacity <= 1;
  },
  formatHsl() {
    const e = se(this.opacity);
    return `${e === 1 ? "hsl(" : "hsla("}${Ge(this.h)}, ${re(this.s) * 100}%, ${re(this.l) * 100}%${e === 1 ? ")" : `, ${e})`}`;
  }
}));
function Ge(e) {
  return e = (e || 0) % 360, e < 0 ? e + 360 : e;
}
function re(e) {
  return Math.max(0, Math.min(1, e || 0));
}
function ve(e, t, n) {
  return (e < 60 ? t + (n - t) * e / 60 : e < 180 ? n : e < 240 ? t + (n - t) * (240 - e) / 60 : t) * 255;
}
const _e = (e) => () => e;
function sn(e, t) {
  return function(n) {
    return e + n * t;
  };
}
function cn(e, t, n) {
  return e = Math.pow(e, n), t = Math.pow(t, n) - e, n = 1 / n, function(r) {
    return Math.pow(e + r * t, n);
  };
}
function un(e) {
  return (e = +e) == 1 ? ft : function(t, n) {
    return n - t ? cn(t, n, e) : _e(isNaN(t) ? n : t);
  };
}
function ft(e, t) {
  var n = t - e;
  return n ? sn(e, n) : _e(isNaN(e) ? t : e);
}
const Ye = (function e(t) {
  var n = un(t);
  function r(i, a) {
    var o = n((i = ke(i)).r, (a = ke(a)).r), f = n(i.g, a.g), c = n(i.b, a.b), s = ft(i.opacity, a.opacity);
    return function(l) {
      return i.r = o(l), i.g = f(l), i.b = c(l), i.opacity = s(l), i + "";
    };
  }
  return r.gamma = e, r;
})(1);
function ln(e, t) {
  t || (t = []);
  var n = e ? Math.min(t.length, e.length) : 0, r = t.slice(), i;
  return function(a) {
    for (i = 0; i < n; ++i) r[i] = e[i] * (1 - a) + t[i] * a;
    return r;
  };
}
function dn(e) {
  return ArrayBuffer.isView(e) && !(e instanceof DataView);
}
function hn(e, t) {
  var n = t ? t.length : 0, r = e ? Math.min(n, e.length) : 0, i = new Array(r), a = new Array(n), o;
  for (o = 0; o < r; ++o) i[o] = Ie(e[o], t[o]);
  for (; o < n; ++o) a[o] = t[o];
  return function(f) {
    for (o = 0; o < r; ++o) a[o] = i[o](f);
    return a;
  };
}
function mn(e, t) {
  var n = /* @__PURE__ */ new Date();
  return e = +e, t = +t, function(r) {
    return n.setTime(e * (1 - r) + t * r), n;
  };
}
function ce(e, t) {
  return e = +e, t = +t, function(n) {
    return e * (1 - n) + t * n;
  };
}
function xn(e, t) {
  var n = {}, r = {}, i;
  (e === null || typeof e != "object") && (e = {}), (t === null || typeof t != "object") && (t = {});
  for (i in t)
    i in e ? n[i] = Ie(e[i], t[i]) : r[i] = t[i];
  return function(a) {
    for (i in n) r[i] = n[i](a);
    return r;
  };
}
var $e = /[-+]?(?:\d+\.?\d*|\.?\d+)(?:[eE][-+]?\d+)?/g, Me = new RegExp($e.source, "g");
function gn(e) {
  return function() {
    return e;
  };
}
function yn(e) {
  return function(t) {
    return e(t) + "";
  };
}
function pn(e, t) {
  var n = $e.lastIndex = Me.lastIndex = 0, r, i, a, o = -1, f = [], c = [];
  for (e = e + "", t = t + ""; (r = $e.exec(e)) && (i = Me.exec(t)); )
    (a = i.index) > n && (a = t.slice(n, a), f[o] ? f[o] += a : f[++o] = a), (r = r[0]) === (i = i[0]) ? f[o] ? f[o] += i : f[++o] = i : (f[++o] = null, c.push({ i: o, x: ce(r, i) })), n = Me.lastIndex;
  return n < t.length && (a = t.slice(n), f[o] ? f[o] += a : f[++o] = a), f.length < 2 ? c[0] ? yn(c[0].x) : gn(t) : (t = c.length, function(s) {
    for (var l = 0, u; l < t; ++l) f[(u = c[l]).i] = u.x(s);
    return f.join("");
  });
}
function Ie(e, t) {
  var n = typeof t, r;
  return t == null || n === "boolean" ? _e(t) : (n === "number" ? ce : n === "string" ? (r = U(t)) ? (t = r, Ye) : pn : t instanceof U ? Ye : t instanceof Date ? mn : dn(t) ? ln : Array.isArray(t) ? hn : typeof t.valueOf != "function" && typeof t.toString != "function" || isNaN(t) ? xn : ce)(e, t);
}
function bn(e, t) {
  return e = +e, t = +t, function(n) {
    return Math.round(e * (1 - n) + t * n);
  };
}
function wn(e) {
  return function() {
    return e;
  };
}
function vn(e) {
  return +e;
}
var Xe = [0, 1];
function I(e) {
  return e;
}
function Ee(e, t) {
  return (t -= e = +e) ? function(n) {
    return (n - e) / t;
  } : wn(isNaN(t) ? NaN : 0.5);
}
function Mn(e, t) {
  var n;
  return e > t && (n = e, e = t, t = n), function(r) {
    return Math.max(e, Math.min(t, r));
  };
}
function Nn(e, t, n) {
  var r = e[0], i = e[1], a = t[0], o = t[1];
  return i < r ? (r = Ee(i, r), a = n(o, a)) : (r = Ee(r, i), a = n(a, o)), function(f) {
    return a(r(f));
  };
}
function kn(e, t, n) {
  var r = Math.min(e.length, t.length) - 1, i = new Array(r), a = new Array(r), o = -1;
  for (e[r] < e[0] && (e = e.slice().reverse(), t = t.slice().reverse()); ++o < r; )
    i[o] = Ee(e[o], e[o + 1]), a[o] = n(t[o], t[o + 1]);
  return function(f) {
    var c = Bt(e, f, 1, r) - 1;
    return a[c](i[c](f));
  };
}
function $n(e, t) {
  return t.domain(e.domain()).range(e.range()).interpolate(e.interpolate()).clamp(e.clamp()).unknown(e.unknown());
}
function En() {
  var e = Xe, t = Xe, n = Ie, r, i, a, o = I, f, c, s;
  function l() {
    var d = Math.min(e.length, t.length);
    return o !== I && (o = Mn(e[0], e[d - 1])), f = d > 2 ? kn : Nn, c = s = null, u;
  }
  function u(d) {
    return d == null || isNaN(d = +d) ? a : (c || (c = f(e.map(r), t, n)))(r(o(d)));
  }
  return u.invert = function(d) {
    return o(i((s || (s = f(t, e.map(r), ce)))(d)));
  }, u.domain = function(d) {
    return arguments.length ? (e = Array.from(d, vn), l()) : e.slice();
  }, u.range = function(d) {
    return arguments.length ? (t = Array.from(d), l()) : t.slice();
  }, u.rangeRound = function(d) {
    return t = Array.from(d), n = bn, l();
  }, u.clamp = function(d) {
    return arguments.length ? (o = d ? !0 : I, l()) : o !== I;
  }, u.interpolate = function(d) {
    return arguments.length ? (n = d, l()) : n;
  }, u.unknown = function(d) {
    return arguments.length ? (a = d, u) : a;
  }, function(d, M) {
    return r = d, i = M, l();
  };
}
function Sn() {
  return En()(I, I);
}
function An(e) {
  return Math.abs(e = Math.round(e)) >= 1e21 ? e.toLocaleString("en").replace(/,/g, "") : e.toString(10);
}
function ue(e, t) {
  if (!isFinite(e) || e === 0) return null;
  var n = (e = t ? e.toExponential(t - 1) : e.toExponential()).indexOf("e"), r = e.slice(0, n);
  return [
    r.length > 1 ? r[0] + r.slice(2) : r,
    +e.slice(n + 1)
  ];
}
function T(e) {
  return e = ue(Math.abs(e)), e ? e[1] : NaN;
}
function Ln(e, t) {
  return function(n, r) {
    for (var i = n.length, a = [], o = 0, f = e[0], c = 0; i > 0 && f > 0 && (c + f + 1 > r && (f = Math.max(1, r - c)), a.push(n.substring(i -= f, i + f)), !((c += f + 1) > r)); )
      f = e[o = (o + 1) % e.length];
    return a.reverse().join(t);
  };
}
function _n(e) {
  return function(t) {
    return t.replace(/[0-9]/g, function(n) {
      return e[+n];
    });
  };
}
var In = /^(?:(.)?([<>=^]))?([+\-( ])?([$#])?(0)?(\d+)?(,)?(\.\d+)?(~)?([a-z%])?$/i;
function le(e) {
  if (!(t = In.exec(e))) throw new Error("invalid format: " + e);
  var t;
  return new Re({
    fill: t[1],
    align: t[2],
    sign: t[3],
    symbol: t[4],
    zero: t[5],
    width: t[6],
    comma: t[7],
    precision: t[8] && t[8].slice(1),
    trim: t[9],
    type: t[10]
  });
}
le.prototype = Re.prototype;
function Re(e) {
  this.fill = e.fill === void 0 ? " " : e.fill + "", this.align = e.align === void 0 ? ">" : e.align + "", this.sign = e.sign === void 0 ? "-" : e.sign + "", this.symbol = e.symbol === void 0 ? "" : e.symbol + "", this.zero = !!e.zero, this.width = e.width === void 0 ? void 0 : +e.width, this.comma = !!e.comma, this.precision = e.precision === void 0 ? void 0 : +e.precision, this.trim = !!e.trim, this.type = e.type === void 0 ? "" : e.type + "";
}
Re.prototype.toString = function() {
  return this.fill + this.align + this.sign + this.symbol + (this.zero ? "0" : "") + (this.width === void 0 ? "" : Math.max(1, this.width | 0)) + (this.comma ? "," : "") + (this.precision === void 0 ? "" : "." + Math.max(0, this.precision | 0)) + (this.trim ? "~" : "") + this.type;
};
function Rn(e) {
  e: for (var t = e.length, n = 1, r = -1, i; n < t; ++n)
    switch (e[n]) {
      case ".":
        r = i = n;
        break;
      case "0":
        r === 0 && (r = n), i = n;
        break;
      default:
        if (!+e[n]) break e;
        r > 0 && (r = 0);
        break;
    }
  return r > 0 ? e.slice(0, r) + e.slice(i + 1) : e;
}
var de;
function Pn(e, t) {
  var n = ue(e, t);
  if (!n) return de = void 0, e.toPrecision(t);
  var r = n[0], i = n[1], a = i - (de = Math.max(-8, Math.min(8, Math.floor(i / 3))) * 3) + 1, o = r.length;
  return a === o ? r : a > o ? r + new Array(a - o + 1).join("0") : a > 0 ? r.slice(0, a) + "." + r.slice(a) : "0." + new Array(1 - a).join("0") + ue(e, Math.max(0, t + a - 1))[0];
}
function Ue(e, t) {
  var n = ue(e, t);
  if (!n) return e + "";
  var r = n[0], i = n[1];
  return i < 0 ? "0." + new Array(-i).join("0") + r : r.length > i + 1 ? r.slice(0, i + 1) + "." + r.slice(i + 1) : r + new Array(i - r.length + 2).join("0");
}
const Ve = {
  "%": (e, t) => (e * 100).toFixed(t),
  b: (e) => Math.round(e).toString(2),
  c: (e) => e + "",
  d: An,
  e: (e, t) => e.toExponential(t),
  f: (e, t) => e.toFixed(t),
  g: (e, t) => e.toPrecision(t),
  o: (e) => Math.round(e).toString(8),
  p: (e, t) => Ue(e * 100, t),
  r: Ue,
  s: Pn,
  X: (e) => Math.round(e).toString(16).toUpperCase(),
  x: (e) => Math.round(e).toString(16)
};
function Ke(e) {
  return e;
}
var We = Array.prototype.map, Ze = ["y", "z", "a", "f", "p", "n", "µ", "m", "", "k", "M", "G", "T", "P", "E", "Z", "Y"];
function qn(e) {
  var t = e.grouping === void 0 || e.thousands === void 0 ? Ke : Ln(We.call(e.grouping, Number), e.thousands + ""), n = e.currency === void 0 ? "" : e.currency[0] + "", r = e.currency === void 0 ? "" : e.currency[1] + "", i = e.decimal === void 0 ? "." : e.decimal + "", a = e.numerals === void 0 ? Ke : _n(We.call(e.numerals, String)), o = e.percent === void 0 ? "%" : e.percent + "", f = e.minus === void 0 ? "−" : e.minus + "", c = e.nan === void 0 ? "NaN" : e.nan + "";
  function s(u, d) {
    u = le(u);
    var M = u.fill, O = u.align, w = u.sign, z = u.symbol, Z = u.zero, pe = u.width, be = u.comma, N = u.precision, Pe = u.trim, x = u.type;
    x === "n" ? (be = !0, x = "g") : Ve[x] || (N === void 0 && (N = 12), Pe = !0, x = "g"), (Z || M === "0" && O === "=") && (Z = !0, M = "0", O = "=");
    var vt = (d && d.prefix !== void 0 ? d.prefix : "") + (z === "$" ? n : z === "#" && /[boxX]/.test(x) ? "0" + x.toLowerCase() : ""), Mt = (z === "$" ? r : /[%p]/.test(x) ? o : "") + (d && d.suffix !== void 0 ? d.suffix : ""), qe = Ve[x], Nt = /[defgprs%]/.test(x);
    N = N === void 0 ? 6 : /[gprs]/.test(x) ? Math.max(1, Math.min(21, N)) : Math.max(0, Math.min(20, N));
    function Te(h) {
      var k = vt, g = Mt, L, He, J;
      if (x === "c")
        g = qe(h) + g, h = "";
      else {
        h = +h;
        var Q = h < 0 || 1 / h < 0;
        if (h = isNaN(h) ? c : qe(Math.abs(h), N), Pe && (h = Rn(h)), Q && +h == 0 && w !== "+" && (Q = !1), k = (Q ? w === "(" ? w : f : w === "-" || w === "(" ? "" : w) + k, g = (x === "s" && !isNaN(h) && de !== void 0 ? Ze[8 + de / 3] : "") + g + (Q && w === "(" ? ")" : ""), Nt) {
          for (L = -1, He = h.length; ++L < He; )
            if (J = h.charCodeAt(L), 48 > J || J > 57) {
              g = (J === 46 ? i + h.slice(L + 1) : h.slice(L)) + g, h = h.slice(0, L);
              break;
            }
        }
      }
      be && !Z && (h = t(h, 1 / 0));
      var ee = k.length + h.length + g.length, v = ee < pe ? new Array(pe - ee + 1).join(M) : "";
      switch (be && Z && (h = t(v + h, v.length ? pe - g.length : 1 / 0), v = ""), O) {
        case "<":
          h = k + h + g + v;
          break;
        case "=":
          h = k + v + h + g;
          break;
        case "^":
          h = v.slice(0, ee = v.length >> 1) + k + h + g + v.slice(ee);
          break;
        default:
          h = v + k + h + g;
          break;
      }
      return a(h);
    }
    return Te.toString = function() {
      return u + "";
    }, Te;
  }
  function l(u, d) {
    var M = Math.max(-8, Math.min(8, Math.floor(T(d) / 3))) * 3, O = Math.pow(10, -M), w = s((u = le(u), u.type = "f", u), { suffix: Ze[8 + M / 3] });
    return function(z) {
      return w(O * z);
    };
  }
  return {
    format: s,
    formatPrefix: l
  };
}
var ie, st, ct;
Tn({
  thousands: ",",
  grouping: [3],
  currency: ["$", ""]
});
function Tn(e) {
  return ie = qn(e), st = ie.format, ct = ie.formatPrefix, ie;
}
function Hn(e) {
  return Math.max(0, -T(Math.abs(e)));
}
function On(e, t) {
  return Math.max(0, Math.max(-8, Math.min(8, Math.floor(T(t) / 3))) * 3 - T(Math.abs(e)));
}
function zn(e, t) {
  return e = Math.abs(e), t = Math.abs(t) - e, Math.max(0, T(t) - T(e)) + 1;
}
function Cn(e, t, n, r) {
  var i = Ut(e, t, n), a;
  switch (r = le(r ?? ",f"), r.type) {
    case "s": {
      var o = Math.max(Math.abs(e), Math.abs(t));
      return r.precision == null && !isNaN(a = On(i, o)) && (r.precision = a), ct(r, o);
    }
    case "":
    case "e":
    case "g":
    case "p":
    case "r": {
      r.precision == null && !isNaN(a = zn(i, Math.max(Math.abs(e), Math.abs(t)))) && (r.precision = a - (r.type === "e"));
      break;
    }
    case "f":
    case "%": {
      r.precision == null && !isNaN(a = Hn(i)) && (r.precision = a - (r.type === "%") * 2);
      break;
    }
  }
  return st(r);
}
function jn(e) {
  var t = e.domain;
  return e.ticks = function(n) {
    var r = t();
    return Xt(r[0], r[r.length - 1], n ?? 10);
  }, e.tickFormat = function(n, r) {
    var i = t();
    return Cn(i[0], i[i.length - 1], n ?? 10, r);
  }, e.nice = function(n) {
    n == null && (n = 10);
    var r = t(), i = 0, a = r.length - 1, o = r[i], f = r[a], c, s, l = 10;
    for (f < o && (s = o, o = f, f = s, s = i, i = a, a = s); l-- > 0; ) {
      if (s = Ne(o, f, n), s === c)
        return r[i] = o, r[a] = f, t(r);
      if (s > 0)
        o = Math.floor(o / s) * s, f = Math.ceil(f / s) * s;
      else if (s < 0)
        o = Math.ceil(o * s) / s, f = Math.floor(f * s) / s;
      else
        break;
      c = s;
    }
    return e;
  }, e;
}
function ut() {
  var e = Sn();
  return e.copy = function() {
    return $n(e, ut());
  }, Vt.apply(e, arguments), jn(e);
}
function Fn(e) {
  return --e * e * e + 1;
}
var H = 0, j = 0, C = 0, lt = 1e3, he, F, me = 0, A = 0, ye = 0, V = typeof performance == "object" && performance.now ? performance : Date, dt = typeof window == "object" && window.requestAnimationFrame ? window.requestAnimationFrame.bind(window) : function(e) {
  setTimeout(e, 17);
};
function ht() {
  return A || (dt(Bn), A = V.now() + ye);
}
function Bn() {
  A = 0;
}
function Se() {
  this._call = this._time = this._next = null;
}
Se.prototype = mt.prototype = {
  constructor: Se,
  restart: function(e, t, n) {
    if (typeof e != "function") throw new TypeError("callback is not a function");
    n = (n == null ? ht() : +n) + (t == null ? 0 : +t), !this._next && F !== this && (F ? F._next = this : he = this, F = this), this._call = e, this._time = n, Ae();
  },
  stop: function() {
    this._call && (this._call = null, this._time = 1 / 0, Ae());
  }
};
function mt(e, t, n) {
  var r = new Se();
  return r.restart(e, t, n), r;
}
function Dn() {
  ht(), ++H;
  for (var e = he, t; e; )
    (t = A - e._time) >= 0 && e._call.call(void 0, t), e = e._next;
  --H;
}
function Je() {
  A = (me = V.now()) + ye, H = j = 0;
  try {
    Dn();
  } finally {
    H = 0, Yn(), A = 0;
  }
}
function Gn() {
  var e = V.now(), t = e - me;
  t > lt && (ye -= t, me = e);
}
function Yn() {
  for (var e, t = he, n, r = 1 / 0; t; )
    t._call ? (r > t._time && (r = t._time), e = t, t = t._next) : (n = t._next, t._next = null, t = e ? e._next = n : he = n);
  F = e, Ae(r);
}
function Ae(e) {
  if (!H) {
    j && (j = clearTimeout(j));
    var t = e - A;
    t > 24 ? (e < 1 / 0 && (j = setTimeout(Je, e - V.now() - ye)), C && (C = clearInterval(C))) : (C || (me = V.now(), C = setInterval(Gn, lt)), H = 1, dt(Je));
  }
}
const q = /* @__PURE__ */ new Set();
let D = null;
function xt() {
  D || q.size === 0 || (D = mt((e) => {
    q.forEach((t) => {
      try {
        t(e);
      } catch (n) {
        console.error("[effects] tick subscriber threw; removing it:", n), q.delete(t);
      }
    });
  }));
}
function gt() {
  D && (D.stop(), D = null);
}
function Xn(e) {
  return q.add(e), xt(), () => {
    q.delete(e), q.size === 0 && gt();
  };
}
typeof document < "u" && document.addEventListener("visibilitychange", () => {
  document.hidden ? gt() : xt();
});
const Qe = 0.15, K = /* @__PURE__ */ new Set(), y = { x: -9999, y: -9999, sx: -9999, sy: -9999 };
let G = null, xe = !1;
function yt(e) {
  y.sx === -9999 && (y.sx = e.clientX, y.sy = e.clientY), y.x = e.clientX, y.y = e.clientY;
}
function pt() {
  K.size === 0 && (xe && (window.removeEventListener("mousemove", yt), xe = !1), G && (G(), G = null));
}
function Un() {
  y.sx += (y.x - y.sx) * Qe, y.sy += (y.y - y.sy) * Qe, K.forEach((e) => {
    try {
      e(y);
    } catch (t) {
      console.error("[effects] pointer subscriber threw; removing it:", t), K.delete(e), pt();
    }
  });
}
function bt(e) {
  return K.add(e), xe || (window.addEventListener("mousemove", yt), xe = !0), G || (G = Xn(Un)), () => {
    K.delete(e), pt();
  };
}
const Vn = 90;
function Kn(e) {
  if (ge() === "full")
    try {
      const t = Array.from(e.querySelectorAll(".bulb"));
      if (t.length === 0) return;
      const n = ut().domain([Vn, 0]).range([0, 1]).clamp(!0);
      let r = null;
      const i = () => {
        r || (r = bt((a) => {
          t.forEach((o) => {
            const f = o.getBoundingClientRect(), c = a.sx - (f.left + f.width / 2), s = a.sy - (f.top + f.height / 2), l = Fn(n(Math.hypot(c, s)));
            l > 0.01 ? (o.style.transform = `scale(${1 + 0.4 * l})`, o.style.boxShadow = `0 0 ${6 + 12 * l}px #fff4c0, 0 0 ${12 + 22 * l}px rgba(201, 168, 76, ${0.3 + 0.5 * l})`) : o.style.transform && (o.style.transform = "", o.style.boxShadow = "");
          });
        }));
      };
      e.classList.contains("hero--live") ? i() : e.addEventListener("neon:live", i, { once: !0 });
    } catch (t) {
      console.error("[effects] cursor bulbs disabled:", t);
    }
}
function Wn(e = document) {
  e.querySelectorAll("[data-cursor-bulbs]").forEach((t) => {
    t.dataset.cursorBulbsInit || (t.dataset.cursorBulbsInit = "1", Kn(t));
  });
}
const Zn = 4;
function Jn(e, t = ":scope > article, :scope > a") {
  if (ge() === "full")
    try {
      e.classList.add("fx-spotlight-grid");
      const n = document.createElement("div");
      n.className = "fx-spotlight", n.setAttribute("aria-hidden", "true"), e.appendChild(n);
      let r = !1;
      const i = () => e.querySelectorAll(t).forEach((a) => {
        a.classList.remove("fx-card--focus", "fx-card--dim"), a.style.transform = "";
      });
      bt((a) => {
        const o = e.getBoundingClientRect(), f = a.sx >= o.left && a.sx <= o.right && a.sy >= o.top && a.sy <= o.bottom;
        if (e.classList.toggle("fx-spotlight-grid--active", f), !f) {
          r && (i(), r = !1);
          return;
        }
        r = !0, n.style.transform = `translate(${a.sx - o.left}px, ${a.sy - o.top}px)`, e.querySelectorAll(t).forEach((c) => {
          const s = c.getBoundingClientRect(), l = a.x >= s.left && a.x <= s.right && a.y >= s.top && a.y <= s.bottom;
          if (c.classList.toggle("fx-card--focus", l), c.classList.toggle("fx-card--dim", !l), l) {
            const u = s.left + s.width / 2, d = (a.sx - u) / (s.width / 2) * Zn;
            c.style.transform = `translateY(-6px) perspective(800px) rotateY(${d}deg)`;
          } else
            c.style.transform = "";
        });
      });
    } catch (n) {
      console.error("[effects] card spotlight disabled:", n);
    }
}
function wt(e = document) {
  e.querySelectorAll("[data-spotlight]").forEach((t) => {
    t.dataset.spotlightInit || (t.dataset.spotlightInit = "1", Jn(t));
  });
}
function et() {
  nt(document), Ot(document), Wn(document), wt(document);
}
document.readyState !== "loading" ? et() : document.addEventListener("DOMContentLoaded", et);
document.body.addEventListener("htmx:afterSwap", (e) => {
  nt(e.target), wt(e.target);
});
