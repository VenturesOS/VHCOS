/**
 * bg-visibility-shim.js — VHC Talent OS v6.2.2
 * =============================================
 * Runs in the PAGE's world (world: "MAIN") at document_start, before any
 * of Naukri's own scripts. Purpose: make background-tab capture behave
 * exactly like foreground capture.
 *
 * Why: Resdex gates its rendering on Page Visibility — in a hidden tab it
 * (a) skips mounting the contact section, and (b) schedules UI paints via
 * requestAnimationFrame, which Chrome never fires for hidden tabs. Result:
 * "View Contact" either doesn't exist or its reveal never reaches the DOM,
 * so background captures came back without a phone number.
 *
 * What this does — to the PAGE ONLY:
 *   1. document.hidden → false, visibilityState → 'visible' (plus webkit
 *      aliases), document.hasFocus() → true.
 *   2. Swallows 'visibilitychange' so the app never reacts to being hidden.
 *   3. Swallows window 'blur' only while the tab is natively hidden.
 *   4. requestAnimationFrame falls back to setTimeout(cb, 16) while the
 *      tab is natively hidden, so rAF-scheduled renders still execute.
 *      (Chrome clamps hidden-tab timers to ~1s ticks — slower, but they
 *      RUN, which is all the DOM needs; we scrape markup, not pixels.)
 *
 * What it does NOT touch: the extension's content script runs in the
 * ISOLATED world with its own DOM wrappers, so `document.hidden` there
 * still reports the TRUTH — capture logic keeps making correct
 * background-tab decisions while the page is deceived.
 *
 * Shim rAF handles are NEGATIVE integers; native handles are positive.
 * cancelAnimationFrame routes on sign, so the two can never collide.
 */
(() => {
  'use strict';
  if (window.__vhcVisShim) return;
  window.__vhcVisShim = '6.2.2';

  // ── keep a truthful "am I really hidden?" before we lie about it ──
  let nativeHiddenGet = null;
  try {
    const d = Object.getOwnPropertyDescriptor(Document.prototype, 'hidden');
    if (d && d.get) nativeHiddenGet = d.get;
  } catch (_) {}
  const isNativelyHidden = () => {
    try { return nativeHiddenGet ? !!nativeHiddenGet.call(document) : false; }
    catch (_) { return false; }
  };

  // ── 1. visibility + focus spoof ──
  const define = (prop, value) => {
    try {
      Object.defineProperty(Document.prototype, prop, {
        get() { return value; }, configurable: true,
      });
    } catch (_) {}
  };
  define('hidden', false);
  define('visibilityState', 'visible');
  define('webkitHidden', false);
  define('webkitVisibilityState', 'visible');
  try { document.hasFocus = () => true; } catch (_) {}

  // ── 2. the page never hears about visibility changes ──
  const swallow = (e) => { try { e.stopImmediatePropagation(); } catch (_) {} };
  for (const type of ['visibilitychange', 'webkitvisibilitychange']) {
    window.addEventListener(type, swallow, true);
    document.addEventListener(type, swallow, true);
  }
  // 3. blur: swallow only when it comes from the tab being hidden —
  //    real in-page blurs (input fields etc.) must keep working.
  window.addEventListener('blur', (e) => {
    if (e.target === window && isNativelyHidden()) swallow(e);
  }, true);

  // ── 4. rAF keeps ticking while natively hidden ──
  const nativeRAF = window.requestAnimationFrame.bind(window);
  const nativeCAF = window.cancelAnimationFrame.bind(window);
  let shimSeq = 1;
  const shimTimers = new Map();

  window.requestAnimationFrame = function (cb) {
    if (!isNativelyHidden()) return nativeRAF(cb);
    const id = -(shimSeq++);
    const t = setTimeout(() => {
      shimTimers.delete(id);
      try { cb(performance.now()); } catch (_) {}
    }, 16);
    shimTimers.set(id, t);
    return id;
  };
  window.cancelAnimationFrame = function (id) {
    if (typeof id === 'number' && id < 0) {
      const t = shimTimers.get(id);
      if (t !== undefined) { clearTimeout(t); shimTimers.delete(id); }
      return;
    }
    return nativeCAF(id);
  };

  // ── 5. IntersectionObserver force-fire while natively hidden ──
  // Chrome computes intersections during rendering steps, which are
  // skipped entirely for hidden tabs — so IO-gated lazy components (the
  // CV preview among them) never mount, no matter how much we scroll.
  // While natively hidden, every observed target additionally receives
  // one forced "fully intersecting" callback shortly after observe().
  // Native behavior continues untouched in parallel, so foreground
  // semantics are identical. Gated to profile/preview pages so search-
  // page infinite scrollers are never poked.
  try {
    if (/preview|profile|resdex/i.test(location.href) && window.IntersectionObserver) {
      const NativeIO = window.IntersectionObserver;
      const ForcedIO = class extends NativeIO {
        constructor(callback, options) {
          super(callback, options);
          this.__vhcCb = callback;
          this.__vhcForced = new WeakSet();
        }
        observe(target) {
          super.observe(target);
          if (!target || !isNativelyHidden() || this.__vhcForced.has(target)) return;
          this.__vhcForced.add(target);
          setTimeout(() => {
            try {
              const rect = target.getBoundingClientRect
                ? target.getBoundingClientRect()
                : { top: 0, left: 0, bottom: 1, right: 1, width: 1, height: 1, x: 0, y: 0 };
              this.__vhcCb([{
                isIntersecting: true,
                intersectionRatio: 1,
                target,
                boundingClientRect: rect,
                intersectionRect: rect,
                rootBounds: null,
                time: performance.now(),
              }], this);
            } catch (_) {}
          }, 60 + Math.floor(Math.random() * 140));
        }
      };
      window.IntersectionObserver = ForcedIO;
    }
  } catch (_) {}

  try {
    console.log('[VHC SHIM v6.2.2] Page visibility spoof active',
                '(natively hidden:', isNativelyHidden() + ')');
  } catch (_) {}
})();
