/* ----------------------------------------------------------------------
   DeltaTrack — server-side compare flow

   Pick a start PDF and an end PDF, POST them to /api/compare?output=html,
   and open the standalone HTML report in a new browser tab. Nothing is
   uploaded until the user clicks Compare; nothing is stored after the
   response comes back.
   ---------------------------------------------------------------------- */
(function () {
  const MAX_BYTES = 150 * 1024 * 1024; // keep in sync with server MAX_UPLOAD_BYTES
  const PDF_SIG = '%PDF';

  const $ = (id) => document.getElementById(id);

  const files = { start: null, end: null };

  // Selected upload format ('pdf' | 'xml'); drives validation + the API param.
  const selectedFormat = () =>
    (document.querySelector('input[name="format"]:checked') || {}).value || 'pdf';

  // --- Slot wiring (browse + drag/drop) ------------------------------------

  function wireSlot(which) {
    const slot = $(`${which}-slot`);
    const input = $(`${which}-input`);
    const nameEl = $(`${which}-name`);

    const accept = (file) => {
      files[which] = file || null;
      nameEl.textContent = file ? file.name : '';
      slot.classList.toggle('has-file', !!file);
      clearMessages();
      updateButton();
    };

    slot.addEventListener('click', () => input.click());
    slot.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
    });
    input.addEventListener('change', () => accept(input.files[0]));

    ['dragenter', 'dragover'].forEach((ev) =>
      slot.addEventListener(ev, (e) => { e.preventDefault(); slot.classList.add('is-dragover'); })
    );
    ['dragleave', 'drop'].forEach((ev) =>
      slot.addEventListener(ev, (e) => { e.preventDefault(); slot.classList.remove('is-dragover'); })
    );
    slot.addEventListener('drop', (e) => {
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) accept(file);
    });
  }

  function updateButton() {
    $('compare-btn').disabled = !(files.start && files.end);
  }

  // --- Client-side pre-checks (server re-validates regardless) --------------

  async function validate(file, label, fmt) {
    if (file.size === 0) return `${label} is empty.`;
    if (file.size > MAX_BYTES) return `${label} is larger than 150 MB.`;
    if (fmt === 'xml') {
      const head = (await file.slice(0, 64).text()).replace(/^﻿/, '').trimStart();
      if (head[0] !== '<') return `${label} doesn't look like XML.`;
    } else {
      const head = await file.slice(0, 4).text();
      if (head !== PDF_SIG) return `${label} doesn't look like a PDF.`;
    }
    return null;
  }

  // --- Submit --------------------------------------------------------------

  // Open a blank tab synchronously on user click so the browser treats it as
  // allowed. Do NOT pass "noopener" here — that makes window.open return null
  // even when the tab opens, which breaks document.write below.
  function openReportTab() {
    return window.open('about:blank', '_blank');
  }

  function writeReportTab(tab, html) {
    tab.document.open();
    tab.document.write(html);
    tab.document.close();
    tab.opener = null;
  }

  async function onCompare() {
    clearMessages();
    const fmt = selectedFormat();
    const kind = fmt.toUpperCase();
    const errs = [
      await validate(files.start, `Start ${kind}`, fmt),
      await validate(files.end, `End ${kind}`, fmt),
    ].filter(Boolean);
    if (errs.length) { showError(errs.join(' ')); return; }

    const tab = openReportTab();
    if (!tab) {
      showError('Pop-up blocked. Allow pop-ups for this site to view the report.');
      return;
    }

    setLoading(true);
    const body = new FormData();
    body.append('start_file', files.start);
    body.append('end_file', files.end);

    try {
      const res = await fetch(`/api/compare?output=html&format=${fmt}`, { method: 'POST', body });
      if (!res.ok) {
        let detail = `Request failed (HTTP ${res.status}).`;
        try { const j = await res.json(); if (j && j.detail) detail = j.detail; } catch (_) {}
        throw new Error(detail);
      }
      const html = await res.text();
      writeReportTab(tab, html);
      showSuccess('Report opened in a new tab. You can compare another pair here.');
    } catch (err) {
      if (tab) tab.close();
      showError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  function setLoading(on) {
    $('compare-btn').disabled = on || !(files.start && files.end);
    $('compare-btn').textContent = on ? 'Comparing…' : 'Compare';
  }

  function showError(msg) {
    const el = $('upload-error');
    el.textContent = msg;
    el.hidden = false;
    $('upload-success').hidden = true;
  }

  function showSuccess(msg) {
    const el = $('upload-success');
    el.textContent = msg;
    el.hidden = false;
    $('upload-error').hidden = true;
  }

  function clearMessages() {
    $('upload-error').hidden = true;
    $('upload-success').hidden = true;
  }

  // --- Format toggle -------------------------------------------------------
  // Switching type clears any chosen files (a PDF is invalid under XML and vice
  // versa) and re-points the native file picker's accept filter + the note.

  function applyFormat() {
    const fmt = selectedFormat();
    const accept = fmt === 'xml' ? 'application/xml,text/xml,.xml' : 'application/pdf,.pdf';
    ['start', 'end'].forEach((which) => {
      const input = $(`${which}-input`);
      input.value = '';
      input.setAttribute('accept', accept);
      files[which] = null;
      $(`${which}-name`).textContent = '';
      $(`${which}-slot`).classList.remove('has-file');
    });
    $('upload-note').textContent = `${fmt.toUpperCase()} · up to 150 MB each · report opens in a new tab`;
    clearMessages();
    updateButton();
  }

  // --- Init ----------------------------------------------------------------

  wireSlot('start');
  wireSlot('end');
  document
    .querySelectorAll('input[name="format"]')
    .forEach((el) => el.addEventListener('change', applyFormat));
  applyFormat();
  updateButton();
  $('compare-btn').addEventListener('click', onCompare);
})();
