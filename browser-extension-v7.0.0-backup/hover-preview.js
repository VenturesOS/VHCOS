// ═══════════════════════════════════════════════════════════════════════════
// VHC Talent OS — Hover Preview for "Already in Database" badges (v6.1.0)
// ---------------------------------------------------------------------------
// Hovering a .vhc-existing-badge shows a compact card with the stored
// candidate's contact details, salary expectation, notice period, and a
// match % against the recruiter's active mandate. Data comes through the
// background worker (getCandidatePreview) so the auth token never enters
// the page context. Click-to-copy on phone/email; card stays open while
// the pointer is inside it; Esc / scroll / outside-click dismiss.
// Loaded after content.js via manifest content_scripts.
// ═══════════════════════════════════════════════════════════════════════════
(() => {
  'use strict';
  if (window.__vhcHoverPreviewLoaded) return;
  window.__vhcHoverPreviewLoaded = true;

  const EXT_VERSION = (() => {
    try { return chrome.runtime.getManifest().version; } catch (_) { return '?'; }
  })();
  console.log(`[VHC v${EXT_VERSION}] hover-preview ready`);

  const SHOW_DELAY = 280;   // ms hover intent before showing
  const HIDE_GRACE = 240;   // ms allowed to travel badge → card
  const CARD_W = 340;

  let card = null;
  let showTimer = null;
  let hideTimer = null;
  let currentBadge = null;
  let requestSeq = 0;       // ignore stale async responses

  // ── tiny utils ───────────────────────────────────────────────────────────
  const esc = (s) => String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  const fmtDate = (iso) => {
    if (!iso) return null;
    const d = new Date(iso);
    return isNaN(d) ? null
      : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  };

  const ringColor = (score) =>
    score >= 70 ? '#059669' : score >= 40 ? '#d97706' : '#dc2626';

  // ── card lifecycle ───────────────────────────────────────────────────────
  function ensureCard() {
    if (card) return card;
    card = document.createElement('div');
    card.id = 'vhc-hp-card';
    card.setAttribute('role', 'tooltip');
    card.addEventListener('mouseenter', () => clearTimeout(hideTimer));
    card.addEventListener('mouseleave', scheduleHide);
    card.addEventListener('click', onCardClick);
    document.body.appendChild(card);
    return card;
  }

  function place(badge) {
    if (!card || !badge) return;
    const r = badge.getBoundingClientRect();
    const ch = card.offsetHeight || 220;
    let left = Math.min(Math.max(8, r.left), window.innerWidth - CARD_W - 8);
    let top = r.bottom + 8;
    if (top + ch > window.innerHeight - 8) top = Math.max(8, r.top - ch - 8);
    card.style.left = `${left}px`;
    card.style.top = `${top}px`;
  }

  function hideNow() {
    clearTimeout(showTimer);
    clearTimeout(hideTimer);
    if (card) {
      card.classList.remove('vhc-hp-visible');
      card.innerHTML = '';
    }
    currentBadge = null;
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hideNow, HIDE_GRACE);
  }

  // ── renderers ────────────────────────────────────────────────────────────
  function renderLoading() {
    return `
      <div class="vhc-hp-head">
        <div class="vhc-hp-skel vhc-hp-skel-title"></div>
        <div class="vhc-hp-skel vhc-hp-skel-ring"></div>
      </div>
      <div class="vhc-hp-skel vhc-hp-skel-line"></div>
      <div class="vhc-hp-skel vhc-hp-skel-line"></div>
      <div class="vhc-hp-skel vhc-hp-skel-line vhc-hp-skel-short"></div>`;
  }

  function renderError(kind, detail) {
    const msg = kind === 'auth'
      ? 'Login required — open the VHC extension popup and sign in.'
      : kind === 'network'
        ? 'Network error reaching VHC — check connection / VPN.'
        : kind === 'ext_reload'
          ? 'Extension was updated — refresh this Naukri tab once.'
          : 'Could not load preview.';
    const code = detail ? `<div class="vhc-hp-errcode">${esc(detail)}</div>` : '';
    return `<div class="vhc-hp-error">${esc(msg)}${code}<button class="vhc-hp-retry" data-vhc-retry="1" type="button">Retry</button><div class="vhc-hp-errcode">v${esc(EXT_VERSION)}</div></div>`;
  }

  function ring(score) {
    const C = 2 * Math.PI * 17;
    const off = C * (1 - Math.max(0, Math.min(100, score)) / 100);
    const col = ringColor(score);
    return `
      <div class="vhc-hp-ring" title="Match vs active mandate">
        <svg width="46" height="46" viewBox="0 0 46 46" aria-hidden="true">
          <circle cx="23" cy="23" r="17" fill="none" stroke="#e5e7eb" stroke-width="5"/>
          <circle cx="23" cy="23" r="17" fill="none" stroke="${col}" stroke-width="5"
                  stroke-linecap="round" stroke-dasharray="${C.toFixed(1)}"
                  stroke-dashoffset="${off.toFixed(1)}"
                  transform="rotate(-90 23 23)"/>
        </svg>
        <span class="vhc-hp-ring-num" style="color:${col}">${score}<em>%</em></span>
      </div>`;
  }

  function row(icon, label, value, copyable) {
    if (!value) return '';
    const val = esc(value);
    const copyBtn = copyable
      ? `<button class="vhc-hp-copy" data-vhc-copy="${val}" title="Copy ${esc(label)}">⧉</button>`
      : '';
    return `
      <div class="vhc-hp-row">
        <span class="vhc-hp-ic" aria-hidden="true">${icon}</span>
        <span class="vhc-hp-val" title="${val}">${val}</span>
        ${copyBtn}
      </div>`;
  }

  const FACTORS = [
    ['skills', 'Skills'], ['experience', 'Experience'],
    ['salary', 'Salary'], ['location', 'Location'], ['notice', 'Notice'],
  ];

  function renderData(data, badgeHref) {
    const c = data.candidate || {};
    const fit = data.fit || null;

    const salary = (c.current_salary || c.expected_salary)
      ? `${esc(c.current_salary || '—')} → <b>${esc(c.expected_salary || '—')}</b>`
      : null;

    const factorDots = fit && fit.factors ? `
      <div class="vhc-hp-factors">
        ${FACTORS.map(([key, name]) => {
          const f = fit.factors[key];
          if (!f) return '';
          return `<span class="vhc-hp-dot vhc-hp-dot-${f.color}" title="${esc(name)}: ${esc(f.label || '')}">${name[0]}</span>`;
        }).join('')}
      </div>` : '';

    const chips = fit && (fit.matched_skills?.length || fit.missing_skills?.length) ? `
      <div class="vhc-hp-chips">
        ${(fit.matched_skills || []).map(s => `<span class="vhc-hp-chip vhc-hp-chip-ok">${esc(s)}</span>`).join('')}
        ${(fit.missing_skills || []).map(s => `<span class="vhc-hp-chip vhc-hp-chip-miss">${esc(s)}</span>`).join('')}
      </div>` : '';

    const fitBlock = fit && fit.score != null
      ? ring(fit.score)
      : `<span class="vhc-hp-nomandate" title="Pick a mandate in the extension popup to see match %">Select a<br>mandate</span>`;

    const mandateLine = fit
      ? `<div class="vhc-hp-mandate" title="${esc(fit.mandate_title || '')}">vs ${esc(fit.mandate_title || 'mandate')}${fit.mandate_code ? ` (${esc(fit.mandate_code)})` : ''}</div>`
      : data.fit_error === 'preview_endpoint_missing'
        ? '<div class="vhc-hp-mandate vhc-hp-mandate-warn" title="Deploy backend Phase 8 (extension_preview.py) to enable match scoring">Match % pending backend update</div>'
        : data.fit_error === 'mandate_not_found'
          ? '<div class="vhc-hp-mandate vhc-hp-mandate-warn">Active mandate no longer exists</div>'
          : '';

    const sub = [c.designation, c.employer].filter(Boolean).join(' @ ');
    const updated = fmtDate(c.updated_at);

    return `
      <div class="vhc-hp-head">
        <div class="vhc-hp-idblock">
          <div class="vhc-hp-name" title="${esc(c.name || '')}">${esc(c.name || 'Candidate')}</div>
          ${sub ? `<div class="vhc-hp-sub" title="${esc(sub)}">${esc(sub)}</div>` : ''}
        </div>
        ${fitBlock}
      </div>
      ${mandateLine}
      ${row('📞', 'phone', c.phone, true)}
      ${row('✉️', 'email', c.email, true)}
      ${salary ? `<div class="vhc-hp-row"><span class="vhc-hp-ic">💰</span><span class="vhc-hp-val">${salary}</span></div>` : ''}
      ${row('⏳', 'notice period', c.notice_period)}
      ${row('📍', 'location', c.location)}
      ${row('💼', 'experience', c.experience_years != null ? `${c.experience_years} yrs experience` : null)}
      ${factorDots}
      ${chips}
      <div class="vhc-hp-foot">
        <span class="vhc-hp-updated">${updated ? `Updated ${esc(updated)} · ` : ''}<span class="vhc-hp-ver">v${esc(EXT_VERSION)}</span></span>
        <a class="vhc-hp-open" href="${esc(badgeHref || '#')}" target="_blank" rel="noopener noreferrer">Open in VHC ↗</a>
      </div>`;
  }

  // ── interactions ─────────────────────────────────────────────────────────
  function onCardClick(e) {
    const retry = e.target.closest('[data-vhc-retry]');
    if (retry) {
      e.preventDefault();
      e.stopPropagation();
      if (currentBadge) showFor(currentBadge);
      return;
    }
    const btn = e.target.closest('[data-vhc-copy]');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const text = btn.getAttribute('data-vhc-copy') || '';
    const done = () => {
      const old = btn.textContent;
      btn.textContent = '✓';
      btn.classList.add('vhc-hp-copied');
      setTimeout(() => { btn.textContent = old; btn.classList.remove('vhc-hp-copied'); }, 1200);
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else {
      fallbackCopy(text, done);
    }
  }

  function fallbackCopy(text, done) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (_) {}
    ta.remove();
    done();
  }

  function showFor(badge) {
    currentBadge = badge;
    const candidateId = badge.dataset.vhcCandidateId;
    if (!candidateId) {
      const el0 = ensureCard();
      el0.innerHTML = renderError('generic', 'missing_candidate_id');
      el0.classList.add('vhc-hp-visible');
      place(badge);
      return;
    }

    const el = ensureCard();
    el.innerHTML = renderLoading();
    el.classList.add('vhc-hp-visible');
    place(badge);

    const seq = ++requestSeq;
    let responded = false;
    const finish = (html) => {
      if (seq !== requestSeq || currentBadge !== badge) return; // stale
      responded = true;
      el.innerHTML = html;
      place(badge);
    };

    try {
      chrome.runtime.sendMessage(
        { action: 'getCandidatePreview', candidate_id: candidateId },
        (res) => {
          if (chrome.runtime.lastError) return finish(renderError('ext_reload', chrome.runtime.lastError.message));
          if (!res || res.success === false) {
            const err = res?.error || 'no_response';
            const kind = err === 'auth' ? 'auth' : err === 'network' ? 'network' : 'generic';
            const detail = [err, res?.api].filter(Boolean).join(' · ');
            return finish(renderError(kind, kind === 'auth' ? null : detail));
          }
          finish(renderData(res.data || res, badge.getAttribute('href')));
        }
      );
    } catch (_) {
      finish(renderError('ext_reload'));
    }
    // Safety: if the worker never answers (rare SW restart race), show retry.
    setTimeout(() => { if (!responded) finish(renderError('generic', 'timeout')); }, 6000);
  }

  // Delegated hover — badges are injected dynamically, so listen globally.
  document.addEventListener('mouseover', (e) => {
    const badge = e.target?.closest?.('.vhc-existing-badge');
    if (!badge) return;
    // Kill the native browser tooltip (badge.title) — it was overlapping
    // the card. The card carries the same info and more.
    if (badge.hasAttribute('title')) {
      badge.dataset.vhcNativeTitle = badge.getAttribute('title');
      badge.removeAttribute('title');
    }
    clearTimeout(hideTimer);
    if (badge === currentBadge && card?.classList.contains('vhc-hp-visible')) return;
    clearTimeout(showTimer);
    showTimer = setTimeout(() => showFor(badge), SHOW_DELAY);
  }, true);

  document.addEventListener('mouseout', (e) => {
    const badge = e.target?.closest?.('.vhc-existing-badge');
    if (!badge) return;
    clearTimeout(showTimer);
    scheduleHide();
  }, true);

  // Keyboard access: focusing the badge (Tab) shows the card too.
  document.addEventListener('focusin', (e) => {
    const badge = e.target?.closest?.('.vhc-existing-badge');
    if (badge) showFor(badge);
  }, true);
  document.addEventListener('focusout', (e) => {
    if (e.target?.closest?.('.vhc-existing-badge')) scheduleHide();
  }, true);

  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideNow(); }, true);
  window.addEventListener('scroll', hideNow, { passive: true, capture: true });
  document.addEventListener('mousedown', (e) => {
    if (card && !card.contains(e.target) && !e.target.closest?.('.vhc-existing-badge')) hideNow();
  }, true);
})();
