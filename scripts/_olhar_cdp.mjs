// 眼 OLHAR SEM O agent-browser — Chrome headless + CDP em Node 24 (WebSocket nativo).
//
// Existe porque o `agent-browser` travou no lancador DUAS vezes seguidas
// (P6 27/09: 21 Chrome orfaos; P7 29/09: 11). Este driver fez o P7 inteiro:
// cliques, medicoes relativas a' seccao, capturas e o hash do DOM da
// OFF-identidade. Quem o chama e' o `scripts/_olhar.py` (monta o plano).
//
// Uso directo: node scripts/_olhar_cdp.mjs plano.json
// plano = { url, w, h, boot?, passos: [ {wait:ms} | {eval:"js", nome?} |
//           {click:"js que devolve o elemento", depois?:ms} | {shot:"x.png", inteira?} ] }
//
// ⚠️ O Chrome e' o do agent-browser (o mais novo em ~/.agent-browser/browsers),
// com perfil PROPRIO na pasta de saida — nunca o Chrome do owner.
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

function acharChrome() {
  const base = path.join(process.env.USERPROFILE || process.env.HOME || ".", ".agent-browser", "browsers");
  const dirs = fs.existsSync(base) ? fs.readdirSync(base).filter(d => d.startsWith("chrome-")).sort() : [];
  for (const d of dirs.reverse()) {
    const exe = path.join(base, d, process.platform === "win32" ? "chrome.exe" : "chrome");
    if (fs.existsSync(exe)) return exe;
  }
  throw new Error("nenhum Chrome em " + base);
}
const CHROME = process.env.NV_CHROME || acharChrome();
const PORT = 9333;
const SCR = process.env.NV_OLHAR_OUT || path.join(process.env.TEMP || "/tmp", "nivrael_olhar");
fs.mkdirSync(SCR, { recursive: true });
const plano = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

async function versao() {
  try { const r = await fetch(`http://127.0.0.1:${PORT}/json/version`); return await r.json(); }
  catch { return null; }
}

async function garantirChrome() {
  if (await versao()) return;
  const prof = path.join(SCR, "chrome-prof");
  const p = spawn(CHROME, [
    "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${prof}`,
    "--no-first-run", "--no-default-browser-check", "--disable-gpu",
    "--hide-scrollbars", "about:blank",
  ], { detached: true, stdio: "ignore" });
  p.unref();
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 250));
    if (await versao()) return;
  }
  throw new Error("chrome nao respondeu");
}

async function novaAba() {
  const r = await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" });
  return await r.json();
}

function ligar(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pend = new Map();
  const ouvintes = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pend.has(m.id)) {
      const { res, rej } = pend.get(m.id); pend.delete(m.id);
      m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
    } else if (m.method) {
      ouvintes.forEach(f => f(m));
    }
  };
  const aberto = new Promise(r => { ws.onopen = r; });
  return {
    aberto,
    ws,
    send(method, params = {}) {
      const i = ++id;
      ws.send(JSON.stringify({ id: i, method, params }));
      return new Promise((res, rej) => pend.set(i, { res, rej }));
    },
    on(f) { ouvintes.push(f); },
  };
}

await garantirChrome();
const aba = await novaAba();
const c = ligar(aba.webSocketDebuggerUrl);
await c.aberto;
const erros = [];
c.on(m => {
  if (m.method === "Runtime.exceptionThrown") erros.push(m.params.exceptionDetails.text + " " + (m.params.exceptionDetails.exception?.description || "").slice(0, 200));
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error")
    erros.push("console.error: " + m.params.args.map(a => a.value ?? a.description ?? "").join(" ").slice(0, 300));
});
await c.send("Runtime.enable");
await c.send("Page.enable");
await c.send("Emulation.setDeviceMetricsOverride", {
  width: plano.w, height: plano.h, deviceScaleFactor: 1, mobile: plano.w < 800,
});
await c.send("Page.navigate", { url: plano.url });
await new Promise(r => setTimeout(r, plano.boot ?? 3500));

const saida = [];
for (const p of plano.passos) {
  if (p.wait) await new Promise(r => setTimeout(r, p.wait));
  // 05/10 - mudar a janela a meio do plano: a mesma cena medida em varias
  // larguras sem refazer os toques (o React re-desenha no resize).
  if (p.viewport) {
    await c.send("Emulation.setDeviceMetricsOverride", {
      width: p.viewport[0], height: p.viewport[1], deviceScaleFactor: 1, mobile: p.viewport[0] < 800,
    });
    await new Promise(r => setTimeout(r, p.depois ?? 700));
    saida.push({ passo: p.nome || "vp", v: p.viewport.join("x") });
  }
  if (p.eval || p.click) {
    const expr = p.click
      ? `(() => { const el = (${p.click}); if (!el) return "NAO ACHEI"; el.scrollIntoView({block:"center"}); el.click(); return "clicado"; })()`
      : p.eval;
    const r = await c.send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    const v = r.exceptionDetails ? ("EXC " + r.exceptionDetails.text + " " + (r.exceptionDetails.exception?.description || "")) : r.result.value;
    saida.push({ passo: p.nome || (p.click ? "click" : "eval"), v });
    if (p.depois) await new Promise(r2 => setTimeout(r2, p.depois));
  }
  if (p.shot) {
    const r = await c.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: !!p.inteira });
    fs.writeFileSync(p.shot, Buffer.from(r.data, "base64"));
    saida.push({ passo: "shot", v: p.shot });
  }
}
console.log(JSON.stringify({ saida, erros }, null, 1));
await fetch(`http://127.0.0.1:${PORT}/json/close/${aba.id}`);
process.exit(0);
