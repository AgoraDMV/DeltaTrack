/* ----------------------------------------------------------------------
   DeltaTrack — server-side compare flow

   The real version of the prototype's mocked "Add a bill": pick a start PDF
   and an end PDF, POST them to /api/compare, and hand the canonical diff JSON
   back to DTRenderer for display. Nothing is uploaded until the user clicks
   Compare; nothing is stored after the response comes back.
   ---------------------------------------------------------------------- */
(function () {
  const MAX_BYTES = 150 * 1024 * 1024; // keep in sync with server MAX_UPLOAD_BYTES
  const PDF_SIG = '%PDF';

  const $ = (id) => document.getElementById(id);

  const files = { start: null, end: null };

  // --- Slot wiring (browse + drag/drop) ------------------------------------

  function wireSlot(which) {
    const slot = $(`${which}-slot`);
    const input = $(`${which}-input`);
    const nameEl = $(`${which}-name`);

    const accept = (file) => {
      files[which] = file || null;
      nameEl.textContent = file ? file.name : '';
      slot.classList.toggle('has-file', !!file);
      clearError();
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

  async function validate(file, label) {
    if (file.size === 0) return `${label} is empty.`;
    if (file.size > MAX_BYTES) return `${label} is larger than 150 MB.`;
    const head = await file.slice(0, 4).text();
    if (head !== PDF_SIG) return `${label} doesn't look like a PDF.`;
    return null;
  }

  // --- Submit --------------------------------------------------------------

  async function onCompare() {
    clearError();
    const errs = [
      await validate(files.start, 'Start PDF'),
      await validate(files.end, 'End PDF'),
    ].filter(Boolean);
    if (errs.length) { showError(errs.join(' ')); return; }

    setLoading(true);
    const body = new FormData();
    body.append('start_pdf', files.start);
    body.append('end_pdf', files.end);

    try {
      const res = await fetch('/api/compare', { method: 'POST', body });
      if (!res.ok) {
        let detail = `Request failed (HTTP ${res.status}).`;
        try { const j = await res.json(); if (j && j.detail) detail = j.detail; } catch (_) {}
        throw new Error(detail);
      }
      const canonical = await res.json();
      showResult(canonical);
    } catch (err) {
      showError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  // --- View transitions ----------------------------------------------------

  function setLoading(on) {
    $('compare-btn').disabled = on || !(files.start && files.end);
    $('compare-btn').textContent = on ? 'Comparing…' : 'Compare';
  }

  function showResult(canonical) {
    $('upload-panel').hidden = true;
    $('result-section').hidden = false;
    document.querySelector('.view-toggle').hidden = false;
    window.DTRenderer.render(canonical);
    window.scrollTo({ top: 0 });
  }

  function resetToUpload() {
    $('result-section').hidden = true;
    document.querySelector('.view-toggle').hidden = true;
    $('bill-summary').hidden = true;
    $('upload-panel').hidden = false;
    window.DTRenderer.reset();
  }

  function showError(msg) {
    const el = $('upload-error');
    el.textContent = msg;
    el.hidden = false;
  }

  function clearError() {
    $('upload-error').hidden = true;
  }

  // --- Example mode (no upload, no server call) ----------------------------
  // Landing page links here with ?example=1 to show a real bundled diff so
  // visitors can see the output before uploading anything.

  async function loadExample() {
    try {
      const res = await fetch('sample/example.json');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showResult(await res.json());
    } catch (err) {
      showError(`Couldn't load the sample diff: ${String(err.message || err)}`);
    }
  }

  // --- Init ----------------------------------------------------------------

  wireSlot('start');
  wireSlot('end');
  updateButton();
  $('compare-btn').addEventListener('click', onCompare);
  $('reset-btn').addEventListener('click', resetToUpload);

  if (new URLSearchParams(location.search).has('example')) loadExample();
})();
