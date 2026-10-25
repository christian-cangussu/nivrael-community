// WEB-C 兩面 — o PONTO DE CORTE das duas superficies, executado a serio.
//
// Nao ha build para o mini-app, logo nao ha como correr isto de Python. Este
// harness extrai `isWebSurface`/`isDesktopSurface` do ui.js REAL (nao uma
// copia — uma copia divergiria no primeiro sprint) e corre-as contra oito
// superficies simuladas. Chamado por `scripts/_test_web_c_superficies.py`.
//
// O caso que justifica o ficheiro: TELEGRAM DESKTOP a 1600px tem de continuar
// a ser TELEMOVEL. Um corte por `window.innerWidth` daria desktop e partiria
// a janela encaixada no cliente do Telegram.
// Extrai isWebSurface/isDesktopSurface do ui.js REAL e corre-os contra
// superficies simuladas. Nao e uma copia da logica — e a logica.
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..");
const src = fs.readFileSync(path.join(ROOT, "miniapp/components/ui.js"), "utf8");
const start = src.indexOf("function isWebSurface()");
const end = src.indexOf("function useDesktopSurface()");
if (start < 0 || end < 0) { console.log("FAIL: nao achei as funcoes"); process.exit(1); }
const body = src.slice(start, end);

function run(surface) {
  const sandbox = { tg: surface.tg, window: surface.window };
  const f = new Function("tg", "window", body + "\nreturn {web:isWebSurface(), desk:isDesktopSurface()};");
  return f(sandbox.tg, sandbox.window);
}
const win = (w, fine) => ({ innerWidth: w, matchMedia: (q) => ({ matches: q.includes("pointer: fine") ? fine : false }) });

const cases = [
  ["Telegram telemovel  (initData, 400px)",  {tg:{initData:"x"}, window:win(400,false)},  false],
  ["Telegram DESKTOP    (initData, 1600px)", {tg:{initData:"x"}, window:win(1600,true)},  false],
  ["browser telemovel   (sem initData,400)", {tg:{initData:""},  window:win(400,false)},  false],
  ["browser tablet fino? (sem, 1100 grosso)",{tg:{initData:""},  window:win(1100,false)}, false],
  ["browser DESKTOP     (sem, 1600 fino)",   {tg:{initData:""},  window:win(1600,true)},  true],
  ["browser 1024 exacto (sem, fino)",        {tg:{initData:""},  window:win(1024,true)},  true],
  ["browser 1023        (sem, fino)",        {tg:{initData:""},  window:win(1023,true)},  false],
  ["sem tg de todo      (1600 fino)",        {tg:undefined,      window:win(1600,true)},  true],
];
let bad = 0;
for (const [nome, s, esperado] of cases) {
  let got;
  try { got = run(s).desk; } catch (e) { got = "ERRO:" + e.message; }
  const ok = got === esperado;
  if (!ok) bad++;
  console.log((ok ? "  ok  " : "  XX  ") + nome + " -> desktop=" + got + " (esperado " + esperado + ")");
}
process.exit(bad ? 1 : 0);
