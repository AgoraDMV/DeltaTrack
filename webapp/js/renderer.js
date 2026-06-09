/* ----------------------------------------------------------------------
   DeltaTrack — canonical diff renderer (vanilla JS, no framework)

   Lifted from the prototype (prototype/app.js), trimmed to a pure renderer:
   the sample library, "add bill"/"export" mocks, and sample fetching are
   gone. It renders one canonical diff JSON document (schema v1.2) — whatever
   the /api/compare endpoint returns — into two views:

     - changes: per-change tracked-changes blocks (default)
     - full:    full bill text with the canonical change set projected inline
                using each change's full_text_span.

   Public API:
     window.DTRenderer.render(canonical)   // show a diff
     window.DTRenderer.reset()             // clear back to empty

   The view toggle (.view-toggle__btn) and filter radios (input[name=filter])
   are wired here so switching re-renders the diff already in memory.
   ---------------------------------------------------------------------- */
(function () {
  const state = {
    currentDiff: null,
    view: 'changes',
    filter: 'all',
  };

  const $ = (id) => document.getElementById(id);

  // --- Public entry points -------------------------------------------------

  function render(canonical) {
    state.currentDiff = canonical;
    renderTopBar();
    renderContent();
  }

  function reset() {
    state.currentDiff = null;
    const content = $('content');
    if (content) content.innerHTML = '';
  }

  // --- Top bar -------------------------------------------------------------

  function renderTopBar() {
    const d = state.currentDiff;
    const billTitle = $('bill-title');
    const billVersions = $('bill-versions');
    if (!d || !billTitle || !billVersions) return;
    const billId = `${(d.bill.type || '').toUpperCase()} ${d.bill.number || ''}`.trim();
    const congress = d.bill.congress ? ` (${d.bill.congress}th Cong.)` : '';
    billTitle.textContent = billId ? `${billId}${congress}` : 'Uploaded documents';
    const v1 = d.versions.v1.label || 'v1';
    const v2 = d.versions.v2.label || 'v2';
    const src = (d.versions.v1.source || '').toUpperCase();
    billVersions.textContent = `${v1}  →  ${v2}${src ? `   ·   ${src} pipeline` : ''}`;
    const summaryEl = $('bill-summary');
    if (summaryEl) summaryEl.hidden = false;
  }

  // --- Content -------------------------------------------------------------

  function renderContent() {
    const d = state.currentDiff;
    const content = $('content');
    if (!d || !content) return;

    let html = renderSummaryBar(d.summary);

    if (state.view === 'full') {
      if (!d.full_text) {
        html += '<div class="empty-state">Full-bill view not available for these documents (no <code>full_text</code> in the diff).</div>';
        content.innerHTML = html;
        return;
      }
      html += renderFullBillView(d);
      content.innerHTML = html;
      return;
    }

    const filtered = applyFilter(d.changes);
    if (filtered.length === 0) {
      html += '<div class="empty-state">No changes match the current filter.</div>';
      content.innerHTML = html;
      return;
    }
    html += renderChanges(filtered);
    content.innerHTML = html;
  }

  function renderSummaryBar(summary) {
    const order = ['added', 'removed', 'modified', 'moved'];
    const pills = order
      .filter((k) => (summary || {})[k])
      .map(
        (k) => `
          <span class="summary-pill summary-pill--${k}">
            <span class="summary-pill__count">${summary[k]}</span>
            <span>${k}</span>
          </span>`
      )
      .join('');
    return `<div class="summary-bar">${pills}</div>`;
  }

  function applyFilter(changes) {
    if (state.filter === 'all') return changes;
    if (state.filter === 'financial') {
      return changes.filter((c) => (c.amounts || []).length > 0);
    }
    // structural: anything other than a pure prose modification
    return changes.filter((c) => c.change_type !== 'modified');
  }

  // --- Per-change blocks (default view) ------------------------------------

  function renderChanges(changes) {
    return `<div class="change-list">${changes.map(renderChangeBlock).join('')}</div>`;
  }

  function renderChangeBlock(c) {
    const head = renderChangeHead(c);
    let body;
    if (c.change_type === 'added') {
      body = `<ins class="diff-add">${escapeHtml(c.text.new || '')}</ins>`;
    } else if (c.change_type === 'removed') {
      body = `<del class="diff-del">${escapeHtml(c.text.old || '')}</del>`;
    } else if (c.change_type === 'moved' && c.move && c.move.body_unchanged) {
      body = `<em class="muted">(body text unchanged)</em>`;
    } else {
      body = renderWordDiff(c.text.old || '', c.text.new || '');
    }
    return `<article class="change-block change-block--${c.change_type}" id="${c.id}">
      <header class="change-block__head">${head}</header>
      ${renderMoveCallout(c)}
      <div class="change-block__body">${body}</div>
      ${renderAmounts(c)}
    </article>`;
  }

  function renderChangeHead(c) {
    const path = (c.path.v2 || c.path.v1 || []).map(escapeHtml).join(' &gt; ');
    const location = c.location && (c.location.v2 || c.location.v1);
    const loc = location ? ` · <span class="loc">${escapeHtml(formatRange(location))}</span>` : '';
    const sectionNum = c.section_number ? `<span class="section-num">§${escapeHtml(c.section_number)}</span> ` : '';
    const tag = `<span class="change-tag change-tag--${c.change_type}">${c.change_type.toUpperCase()}</span>`;
    return `${tag} ${sectionNum}${path || '<em>(unknown)</em>'}${loc}`;
  }

  function renderMoveCallout(c) {
    if (!c.move) return '';
    if (c.move.kind === 'renumbered') {
      const tail = c.move.body_unchanged ? ' · body text unchanged' : '';
      return `<div class="move-callout">Renumbered: <code>${escapeHtml(c.move.old_label)}</code> → <code>${escapeHtml(c.move.new_label)}</code>${tail}</div>`;
    }
    const v1 = (c.path.v1 || []).map(escapeHtml).join(' &gt; ');
    const v2 = (c.path.v2 || []).map(escapeHtml).join(' &gt; ');
    return `<div class="move-callout">Moved: ${v1} → ${v2}</div>`;
  }

  function renderAmounts(c) {
    if (!c.amounts || c.amounts.length === 0) return '';
    const rows = c.amounts.map((a) => {
      const delta = a.new - a.old;
      const sign = delta > 0 ? '+' : '';
      const pct = a.old !== 0 ? ` (${sign}${((delta / a.old) * 100).toFixed(1)}%)` : '';
      return `<div class="amount-row">
        <span class="amount-row__old">${formatDollars(a.old)}</span>
        <span class="amount-row__arrow">→</span>
        <span class="amount-row__new">${formatDollars(a.new)}</span>
        <span class="amount-row__delta">${sign}${formatDollars(delta)}${pct}</span>
      </div>`;
    }).join('');
    return `<div class="amounts"><div class="amounts__title">Financial</div>${rows}</div>`;
  }

  function formatRange(r) {
    const start = r.start_line == null ? `p.${r.start_page}` : `p.${r.start_page} L${r.start_line}`;
    const end = r.end_line == null ? `p.${r.end_page}` : `p.${r.end_page} L${r.end_line}`;
    return start === end ? start : `${start} – ${end}`;
  }

  function formatDollars(n) {
    return '$' + n.toLocaleString('en-US');
  }

  // --- Full-bill tracked-changes view --------------------------------------

  function renderFullBillView(canonical) {
    const v2Text = canonical.full_text.v2;
    const v1Text = canonical.full_text.v1;

    const v2Changes = [];
    const removed = [];
    let unplaced = 0;
    for (const c of canonical.changes) {
      const span = c.full_text_span;
      if (span && span.v2) {
        v2Changes.push(c);
      } else if (c.change_type === 'removed' && span && span.v1) {
        removed.push(c);
      } else {
        unplaced++;
      }
    }
    v2Changes.sort((a, b) => a.full_text_span.v2.start - b.full_text_span.v2.start);

    const parts = [];
    let cursor = 0;
    let placed = 0;
    for (const c of v2Changes) {
      const { start, end } = c.full_text_span.v2;
      if (start < cursor) continue; // overlap; first one wins
      if (start > cursor) parts.push(escapeHtml(v2Text.slice(cursor, start)));
      parts.push(renderV2Mark(c, v2Text.slice(start, end)));
      cursor = end;
      placed++;
    }
    if (cursor < v2Text.length) parts.push(escapeHtml(v2Text.slice(cursor)));

    const meta = renderFullBillMeta({
      total: canonical.changes.length,
      placed,
      removed: removed.length,
      unplaced,
    });
    const removedAppendix = removed.length ? renderRemovedAppendix(removed, v1Text) : '';

    return `${meta}<div class="full-bill">${parts.join('')}</div>${removedAppendix}`;
  }

  function renderV2Mark(change, v2Slice) {
    const id = `attr-${change.id}`;
    switch (change.change_type) {
      case 'added':
        return `<ins class="diff-add" id="${id}" data-change="${change.id}">${escapeHtml(v2Slice)}</ins>`;
      case 'modified': {
        const oldText = change.text.old || '';
        return (
          `<del class="diff-del" data-change="${change.id}">${escapeHtml(oldText)}</del>` +
          `<ins class="diff-add" id="${id}" data-change="${change.id}">${escapeHtml(v2Slice)}</ins>`
        );
      }
      case 'moved': {
        const note = change.move && change.move.kind === 'renumbered'
          ? `moved here (renumbered ${escapeHtml(change.move.old_label)} → ${escapeHtml(change.move.new_label)})`
          : 'moved here';
        return `<span class="moved-mark" id="${id}" data-change="${change.id}" title="${note}">${escapeHtml(v2Slice)}</span>`;
      }
      default:
        return `<del class="diff-del" data-change="${change.id}">${escapeHtml(v2Slice)}</del>`;
    }
  }

  function renderFullBillMeta({ total, placed, removed, unplaced }) {
    const bits = [`${placed} of ${total} changes shown inline`];
    if (removed > 0) bits.push(`${removed} removed below`);
    if (unplaced > 0) bits.push(`${unplaced} unplaced (see Changes tab)`);
    return `<div class="full-bill-meta">${bits.join(' · ')}</div>`;
  }

  function renderRemovedAppendix(removed, v1Text) {
    const blocks = removed
      .map((c) => {
        const { start, end } = c.full_text_span.v1;
        const text = v1Text.slice(start, end);
        const path = (c.path.v1 || []).map(escapeHtml).join(' &gt; ');
        const heading = path || '<em>(unknown location)</em>';
        return `<article class="removed-block" id="attr-${c.id}">
          <div class="removed-block__head">${heading}</div>
          <del class="diff-del">${escapeHtml(text)}</del>
        </article>`;
      })
      .join('');
    return `<section class="removed-appendix">
      <h3 class="removed-appendix__title">Removed in end version</h3>
      <p class="removed-appendix__note">These sections existed in the start version and have no corresponding location in the end version.</p>
      ${blocks}
    </section>`;
  }

  // Word-level LCS used by the per-change view to mark inline edits.
  function renderWordDiff(oldText, newText) {
    return renderTokenDiff(tokenize(oldText), tokenize(newText));
  }

  function renderTokenDiff(a, b) {
    const ops = lcsDiff(a, b);
    let out = '';
    let buf = { type: null, text: '' };
    const flush = () => {
      if (!buf.text) return;
      if (buf.type === 'eq') out += escapeHtml(buf.text);
      else if (buf.type === 'add') out += `<ins class="diff-add">${escapeHtml(buf.text)}</ins>`;
      else if (buf.type === 'del') out += `<del class="diff-del">${escapeHtml(buf.text)}</del>`;
      buf = { type: null, text: '' };
    };
    for (const op of ops) {
      if (op.type !== buf.type) { flush(); buf.type = op.type; }
      buf.text += op.text;
    }
    flush();
    return out;
  }

  function tokenize(text) {
    return text.match(/\s+|[^\s]+/g) || [];
  }

  function lcsDiff(a, b) {
    const m = a.length, n = b.length;
    const dp = new Array(m + 1);
    for (let i = 0; i <= m; i++) dp[i] = new Int32Array(n + 1);
    for (let i = m - 1; i >= 0; i--) {
      for (let j = n - 1; j >= 0; j--) {
        dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    const ops = [];
    let i = 0, j = 0;
    while (i < m && j < n) {
      if (a[i] === b[j]) { ops.push({ type: 'eq', text: a[i] }); i++; j++; }
      else if (dp[i + 1][j] >= dp[i][j + 1]) { ops.push({ type: 'del', text: a[i] }); i++; }
      else { ops.push({ type: 'add', text: b[j] }); j++; }
    }
    while (i < m) ops.push({ type: 'del', text: a[i++] });
    while (j < n) ops.push({ type: 'add', text: b[j++] });
    return ops;
  }

  // --- Utils ---------------------------------------------------------------

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // --- Controls (view toggle + filter) -------------------------------------

  function setupControls() {
    document.querySelectorAll('.view-toggle__btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.view-toggle__btn').forEach((b) => {
          b.classList.toggle('is-active', b === btn);
          b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
        });
        state.view = btn.dataset.view;
        renderContent();
      });
    });
    document.querySelectorAll('input[name="filter"]').forEach((input) => {
      input.addEventListener('change', () => {
        state.filter = input.value;
        renderContent();
      });
    });
  }

  document.addEventListener('DOMContentLoaded', setupControls);

  window.DTRenderer = { render, reset };
})();
