/**
 * 牆 Derrubar a parede — o passo de build do mini-app. (FORMA, 2026-09-04)
 *
 * PORQUE ISTO EXISTE
 * ------------------
 * Até hoje o `/app` mandava um COMPILADOR para o telemóvel do jogador. O
 * `index.html` carregava `@babel/standalone` (3.137.752 bytes) e, **a cada
 * abertura**, compilava 1,79 MB de JSX cru no aparelho antes de desenhar um
 * pixel.
 *
 * MEDIDO a 2026-09-04, com `agent-browser` contra `scripts/_dev_serve_miniapp.py`
 * (servidor local, latência de rede ~0, desktop de 16 cores):
 *
 *     first-paint ................  396 ms   (ecrã vazio)
 *     first-contentful-paint ..... 1988 ms
 *     Babel.transform SOZINHO .... 1026 ms   (ui 105 · tabs 891 · app 30)
 *
 * Ou seja: **mais de metade do tempo até o jogador ver conteúdo era o
 * compilador a trabalhar no aparelho dele** — e isso num desktop. Um telemóvel
 * médio é 4-6× mais lento em single-thread. A rede tem cache; a compilação
 * não tem: aquele segundo (ou aqueles cinco) paga-se em TODAS as aberturas,
 * para sempre.
 *
 * Isto é a aritmética que decide a ordem do lote: não se põe arte, animação
 * nem biblioteca nenhuma em cima disto. Primeiro derruba-se a parede.
 *
 * O QUE ESTE SCRIPT FAZ — e o que deliberadamente NÃO faz
 * -------------------------------------------------------
 * FAZ: transforma o JSX dos três ficheiros com esbuild e concatena-os **pela
 * mesma ordem** num só ficheiro, `miniapp/dist/bundle.js`.
 *
 * NÃO FAZ **bundling de módulos**, e isso não é preguiça — é correcção. Os três
 * ficheiros de hoje são injectados como `<script>` normais e partilham o
 * **escopo global do script-tag**: `ui.js` declara `var LANG`, `var STRINGS`,
 * `t()`, `Card`… e `tabs.js`/`app.js` leem-nos sem importar nada. É por isso
 * que o `MINIAPP_PARITY.md §0.5` manda usar `var` (não `const`/`let`) no
 * top-level. Um bundler de módulos dava a cada ficheiro o seu escopo e partia
 * as ~3.000 referências cruzadas de uma vez. Transformar + concatenar preserva
 * a semântica EXACTA.
 *
 * NÃO FAZ **downlevel de sintaxe** (`target: esnext`). O Babel corria com
 * `presets: ["react"]` e mais nada — ou seja, só JSX. Baixar o alvo aqui
 * mudaria o output de formas que ninguém pediu nem mediu.
 *
 * NÃO FAZ **minificação**. Podia — mas minificar renomeia locais e muda muito
 * mais do que JSX, e a regra desta casa com 248 jogadores vivos é mudar UMA
 * coisa de cada vez e poder prová-la. O ganho grande é a CPU e os 3,14 MB do
 * Babel, não os bytes do nosso código (que o servidor já comprime). Minificar
 * fica escrito como próximo passo, com o número medido primeiro.
 *
 * ⚠️ O BUNDLE É UMA OPTIMIZAÇÃO, NUNCA UM REQUISITO.
 * O `index.html` pede o bundle; se ele não existir (404), cai sozinho no
 * caminho velho do Babel. É de propósito, e é a diferença entre "o deploy não
 * correu o build" e "tela branca para 248 pessoas". Não há flag: uma flag é
 * per-world e lê-se do servidor, e o arranque acontece **antes** da primeira
 * chamada à API — pedir permissão para arrancar depressa custaria uma ida ao
 * servidor, que é exactamente o que se está a tentar poupar.
 *
 * USO
 * ---
 *     node scripts/build_miniapp.mjs [raiz-do-miniapp]
 *
 * Sem argumento assume `<repo>/miniapp`. O Docker passa `/miniapp` porque na
 * stage 1 as fontes vivem lá.
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..");

// esbuild vem do `website/node_modules` (dependência do Vite, já instalada pelo
// `npm ci` da stage 1 do Dockerfile). Resolver a partir de lá evita uma segunda
// árvore de node_modules só para isto.
//
// ⚠️ Duas disposições REAIS, e as duas têm de funcionar:
//   • repo local  — script em `<repo>/scripts/`, esbuild em `<repo>/website/node_modules`
//   • Docker      — script em `/build/`, esbuild em `/build/node_modules`
// A primeira versão deste ficheiro só sabia a de cima e em Docker caía num
// `import()` implícito. Funcionava por acaso; agora é por desenho, e se
// nenhuma resolver, o erro DIZ onde procurou em vez de rebentar críptico.
const ESBUILD_CANDIDATES = [
  join(REPO, "website", "package.json"),   // repo local
  join(HERE, "package.json"),              // Docker: /build/package.json
];
let esbuild = null;
const tried = [];
for (const anchor of ESBUILD_CANDIDATES) {
  try {
    esbuild = createRequire(anchor)("esbuild");
    break;
  } catch (e) {
    tried.push(`${anchor} (${e.code || e.message})`);
  }
}
if (!esbuild) {
  try {
    const m = await import("esbuild");
    esbuild = m.default ?? m;
  } catch (e) {
    tried.push(`import("esbuild") (${e.code || e.message})`);
  }
}
if (!esbuild) {
  console.error("[build_miniapp] esbuild nao encontrado. Procurei em:");
  for (const x of tried) console.error("  - " + x);
  console.error("[build_miniapp] (no repo: `cd website && npm ci`)");
  process.exit(1);
}

// ⚠️ A ORDEM É A DO `index.html` E NÃO PODE MUDAR.
// `tabs.js` lê símbolos declarados em `ui.js`; `app.js` lê os dois. Trocar a
// ordem é um `ReferenceError` no arranque — e um que só aparece em runtime.
const FILES = ["components/ui.js", "components/tabs.js", "components/app.js"];

const MINIAPP = resolve(process.argv[2] || join(REPO, "miniapp"));
const OUT_DIR = join(MINIAPP, "dist");
const OUT_FILE = join(OUT_DIR, "bundle.js");

function main() {
  const parts = [];
  let bytesIn = 0;
  const report = [];

  for (const rel of FILES) {
    const abs = join(MINIAPP, rel);
    if (!existsSync(abs)) {
      console.error(`[build_miniapp] FALTA ${rel} — o bundle seria inútil.`);
      process.exit(1);
    }
    const src = readFileSync(abs, "utf8");
    bytesIn += src.length;
    let out;
    try {
      out = esbuild.transformSync(src, {
        loader: "jsx",
        // `React.createElement` — o mesmo factory que o `presets:["react"]` do
        // Babel usava. O React vem do UMD global, não de um import.
        jsx: "transform",
        jsxFactory: "React.createElement",
        jsxFragment: "React.Fragment",
        // Sem downlevel: só JSX sai, tudo o resto passa como está escrito.
        target: "esnext",
        sourcefile: rel,
      });
    } catch (err) {
      // Um erro de sintaxe TEM de parar o build. Deixá-lo passar produzia um
      // bundle partido que o cliente carregaria com toda a confiança — pior do
      // que não haver bundle nenhum, porque o fallback nunca dispararia.
      console.error(`[build_miniapp] ${rel} não compila:\n${err.message || err}`);
      process.exit(1);
    }
    for (const w of out.warnings || []) {
      console.warn(`[build_miniapp] aviso em ${rel}: ${w.text}`);
    }
    // Um `//# sourceURL` por ficheiro faz o stack trace do browser continuar a
    // dizer "tabs.js:1234" em vez de uma linha de um ficheiro de 1,8 MB.
    parts.push(`\n//# sourceURL=/miniapp/${rel}\n${out.code}`);
    report.push({ rel, in: src.length, out: out.code.length });
  }

  // ⚠️ Cada ficheiro fica no MESMO escopo global, tal como três `<script>`
  // separados. Nada de IIFE a embrulhar: isso esconderia os `var` top-level
  // uns dos outros e partiria tudo.
  const banner =
    "/* Nivrael mini-app — GERADO por scripts/build_miniapp.mjs. NAO EDITAR.\n" +
    "   Fonte: miniapp/components/{ui,tabs,app}.js — e' la' que se muda o jogo.\n" +
    `   Gerado em ${new Date().toISOString()} */\n`;

  const code = banner + parts.join("\n");
  mkdirSync(OUT_DIR, { recursive: true });
  writeFileSync(OUT_FILE, code, "utf8");

  console.log("[build_miniapp] escrito", OUT_FILE);
  for (const r of report) {
    console.log(`  ${r.rel.padEnd(22)} ${String(r.in).padStart(9)} -> ${String(r.out).padStart(9)}`);
  }
  console.log(`  ${"TOTAL".padEnd(22)} ${String(bytesIn).padStart(9)} -> ${String(code.length).padStart(9)}`);
  console.log("[build_miniapp] o cliente deixa de descarregar @babel/standalone (3.137.752 bytes)");
  console.log("[build_miniapp] e deixa de compilar ~1,79 MB de JSX em cada abertura (~1026ms medidos em desktop).");
}

main();
