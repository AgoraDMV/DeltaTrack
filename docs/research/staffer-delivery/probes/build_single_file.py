"""Build ONE self-contained .html carrying Pyodide + the DeltaTrack engine.

Tests the combination that would otherwise be assumed impossible: Option A
(Pyodide) delivered as Option E (a single file a staffer double-clicks). The
`file://` probe showed fetch/Worker/module-import are blocked from origin `null`,
but `fetch("data:...")` and `import(blob:...)` are NOT -- so every asset Pyodide
would normally fetch is inlined as base64 and served by a fetch shim.

Usage:  uv run python spike/build_single_file.py
Output: spike/single-file/deltatrack-standalone.html
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYO = HERE / "static-app" / "pyodide"
OUT = HERE / "single-file" / "deltatrack-standalone.html"

# Pyodide fetches these three at boot; engine.zip is DeltaTrack itself.
ASSETS = {
    "pyodide.asm.wasm": PYO / "pyodide.asm.wasm",
    "python_stdlib.zip": PYO / "python_stdlib.zip",
    "pyodide-lock.json": PYO / "pyodide-lock.json",
    "engine.zip": HERE / "static-app" / "engine.zip",
}


def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode("ascii")


assets_js = ",\n".join(f'  "{name}": "{b64(path)}"' for name, path in ASSETS.items())
# The two JS files are imported as blob: modules rather than fetched.
pyodide_mjs = (PYO / "pyodide.mjs").read_text(encoding="utf-8")
pyodide_asm_mjs = (PYO / "pyodide.asm.mjs").read_text(encoding="utf-8")

html = """<!doctype html>
<meta charset="utf-8" />
<title>DeltaTrack (standalone)</title>
<style>
 body{font:15px/1.6 system-ui,sans-serif;max-width:56rem;margin:2rem auto;padding:0 1rem}
 #log{background:#111;color:#d8d8d8;padding:1rem;border-radius:6px;white-space:pre-wrap;
      font:12.5px/1.45 ui-monospace,Menlo,monospace;min-height:10rem}
 .ok{color:#3ad07a}.bad{color:#ff6b6b}
</style>
<h1>DeltaTrack &mdash; standalone single file</h1>
<p>Everything runs on this machine. No server, no upload, no install.</p>
<p><label>Old XML <input type="file" id="f1" accept=".xml"></label>
   <label>New XML <input type="file" id="f2" accept=".xml"></label>
   <button id="go" disabled>Compare</button></p>
<div id="log">booting…</div>

<script id="assets" type="application/json">
{__ASSETS__}
</script>

<script type="module">
const logEl=document.getElementById("log"); const t0=performance.now();
// textContent on a built node, not innerHTML: log messages carry user-chosen file names
// and nothing here needs markup (CodeQL js/xss-through-dom).
const log=(m,c="")=>{const s=document.createElement("span");if(c)s.className=c;
  s.textContent=`[${((performance.now()-t0)/1000).toFixed(2)}s] ${m}`;logEl.append("\\n",s);};
logEl.textContent="";
log(`protocol ${location.protocol} | origin ${window.origin}`);

// --- decode inlined assets -------------------------------------------------
const RAW=JSON.parse(document.getElementById("assets").textContent);
const BYTES={};
for(const [k,v] of Object.entries(RAW)){
  const bin=atob(v); const arr=new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
  BYTES[k]=arr;
}
log(`inlined assets decoded: ${Object.entries(BYTES).map(([k,v])=>k+" "+(v.length/1e6).toFixed(1)+"MB").join(", ")}`);

// --- fetch shim: serve Pyodide's boot assets from memory --------------------
// Pyodide requests `${indexURL}<name>`; from file:// a real fetch is blocked, so
// every request whose basename we hold is answered locally instead.
const realFetch=globalThis.fetch.bind(globalThis);
globalThis.__fetchLog=[];
globalThis.fetch=async (input,init)=>{
  const url=typeof input==="string"?input:(input&&input.url)||String(input);
  const name=url.split("/").pop().split("?")[0];
  const hit=!!BYTES[name];
  globalThis.__fetchLog.push((hit?"HIT  ":"MISS ")+url.slice(0,120));
  if(hit){
    const type=name.endsWith(".wasm")?"application/wasm"
      :name.endsWith(".json")?"application/json":"application/octet-stream";
    return new Response(BYTES[name],{status:200,headers:{"Content-Type":type}});
  }
  return realFetch(input,init);
};
// Emscripten may also reach for XHR; route it to the same in-memory map.
const RealXHR=globalThis.XMLHttpRequest;
globalThis.XMLHttpRequest=function(){
  const x=new RealXHR(); const open=x.open.bind(x);
  x.open=function(m,u,...r){ globalThis.__fetchLog.push("XHR  "+String(u).slice(0,120)); return open(m,u,...r); };
  return x;
};
// Emscripten prefers instantiateStreaming; our synthetic Response is fine for it,
// but keep a byte fallback in case the Content-Type path is rejected.
const realIS=WebAssembly.instantiateStreaming;
WebAssembly.instantiateStreaming=async (src,imports)=>{
  try{ return await realIS(src,imports); }
  catch(e){ const r=await src; return WebAssembly.instantiate(await r.arrayBuffer(),imports); }
};

// --- import Pyodide's JS as blob: modules (file:// blocks same-dir modules) --
const asBlobURL=(src)=>URL.createObjectURL(new Blob([src],{type:"text/javascript"}));
const ASM_URL=asBlobURL(document.getElementById("pyodide-asm-src").textContent);
// pyodide.mjs resolves its sibling asm module relative to itself; point it at ours.
let mainSrc=document.getElementById("pyodide-main-src").textContent;
mainSrc=mainSrc.replace(/["'`][^"'`]*pyodide\\.asm\\.mjs["'`]/g, JSON.stringify(ASM_URL));

let pyodide=null;
try{
  const tB=performance.now();
  const mod=await import(asBlobURL(mainSrc));
  pyodide=await mod.loadPyodide({indexURL:"./"});
  log(`Pyodide booted from inlined bytes: ${(performance.now()-tB).toFixed(0)} ms`,"ok");
  const tE=performance.now();
  pyodide.unpackArchive(BYTES["engine.zip"],"zip",{extractDir:"/engine"});
  await pyodide.runPythonAsync(`
import sys; sys.path.insert(0,"/engine")
from deltatrack.compare.xml import compare_xml_html
`);
  log(`DeltaTrack engine imported: ${(performance.now()-tE).toFixed(0)} ms`,"ok");
  document.getElementById("go").disabled=false;
  log("READY","ok");
}catch(e){ log(`FAILED: ${e.name}: ${e.message}`,"bad"); console.error(e); }

document.getElementById("go").onclick=async()=>{
  const a=document.getElementById("f1").files[0], b=document.getElementById("f2").files[0];
  if(!a||!b){log("pick two files","bad");return;}
  const t=performance.now();
  pyodide.globals.set("_b1",new Uint8Array(await a.arrayBuffer()));
  pyodide.globals.set("_b2",new Uint8Array(await b.arrayBuffer()));
  const html=await pyodide.runPythonAsync(
    `compare_xml_html(bytes(_b1.to_py()),bytes(_b2.to_py()),start_label="v1",end_label="v2")`);
  log(`diff + render: ${(performance.now()-t).toFixed(0)} ms -> report ${(html.length/1024).toFixed(0)} KB`,"ok");
  globalThis.__lastReport=html;  // spike-only: lets the Playwright probe verify byte parity
  const link=document.createElement("a");
  link.href=URL.createObjectURL(new Blob([html],{type:"text/html"}));
  link.download="deltatrack-report.html"; link.textContent="save the report";
  logEl.append(document.createElement("br"),link);
};
</script>
"""

html = html.replace("{__ASSETS__}", "{\n" + assets_js + "\n}")
# Carry the two JS sources as non-executing script blocks.
html += f'<script id="pyodide-main-src" type="text/plain">{pyodide_mjs}</script>\n'
html += f'<script id="pyodide-asm-src" type="text/plain">{pyodide_asm_mjs}</script>\n'

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding="utf-8")
print(f"wrote {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB)")
print("asset sizes:", json.dumps({k: f"{v.stat().st_size / 1e6:.2f} MB" for k, v in ASSETS.items()}, indent=2))
