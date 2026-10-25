// 牌 A CARTA — o LOMBO CONTADO, executado a serio.
//
// Porque existe: a raridade da carta nao e uma cor, e uma MEDIDA — "3 de 5",
// "5 de 7". Ler a fonte prova que o codigo esta la; nao prova que ele CONTA
// bem. Este harness extrai `NIV_RANK_SCALES` + `nivRank` do `ui.js` REAL (nao
// uma copia — uma copia divergia no primeiro sprint, a licao do
// `_test_web_c_cutpoint.js`) e corre-os contra os valores verdadeiros das tres
// escalas. Chamado por `scripts/_test_web_c_superficies.py`.
//
// O caso que justifica o ficheiro: um valor DESCONHECIDO tem de devolver
// `null`, nunca `{i:0}`. Desenhar 1 de 5 para um grau que nao se reconhece
// afirma "isto e do grau mais baixo" — e uma mentira desenhada, da mesma
// familia da barra que fingia contagem decrescente no cume.
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..");
const src = fs.readFileSync(path.join(ROOT, "miniapp/components/ui.js"), "utf8");

const start = src.indexOf("var NIV_RANK_SCALES = {");
const end = src.indexOf("// A arte servida pelo jogo.");
if (start < 0 || end < 0) { console.log("FAIL: nao achei NIV_RANK_SCALES/nivRank"); process.exit(1); }
const body = src.slice(start, end);

// `t` devolve a PROPRIA key: assim o teste tambem prova o wiring das keys
// (`technique_grade_*`, `beast_rank_*`, `alch_grade`) e nao so a contagem.
const f = new Function("t", body + "\nreturn { nivRank, nivTier, NIV_TIER_CUTS };");
const _api = f((k, p) => (p ? k + ":" + JSON.stringify(p) : k));
const nivRank = _api.nivRank;
const nivTier = _api.nivTier;

let bad = 0;
function chk(cond, msg) {
  console.log((cond ? "ok   " : "FAIL ") + msg);
  if (!cond) bad++;
}

// ── 1. tecnica: 5 degraus, e o valor vem em minusculas do servidor ─────────
const TEC = ["common", "refined", "perfected", "transcendent", "celestial"];
TEC.forEach((g, i) => {
  const r = nivRank("technique", g);
  chk(r && r.i === i && r.n === 5 && r.label === "technique_grade_" + g,
      `tecnica ${g} -> ${i + 1} de 5 (${r && r.label})`);
});

// ── 2. besta: 7 degraus, e o valor vem CAPITALIZADO da base ────────────────
// (`config.BEAST_RANKS = ["Common", ...]` — se `nivRank` nao normalizasse a
// caixa, TODA besta ficava sem lombo, silenciosamente.)
const BST = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Divine"];
BST.forEach((g, i) => {
  const r = nivRank("beast", g);
  chk(r && r.i === i && r.n === 7 && r.label === "beast_rank_" + g.toLowerCase(),
      `besta ${g} -> ${i + 1} de 7 (${r && r.label})`);
});

// ── 3. pilula: a escala NUMERICA, 1..5 ─────────────────────────────────────
for (let d = 1; d <= 5; d++) {
  const r = nivRank("pill", d);
  chk(r && r.i === d - 1 && r.n === 5, `pilula dif.${d} -> ${d} de 5`);
}
chk(nivRank("pill", 9).i === 4, "pilula acima da escala satura no TOPO, nunca estoura");

// ── 3b. ARTEFACTO: NOVE degraus, e a UNICA escala que comeca em ZERO ───────
// (`config.ARTIFACT_GRADES` 0..8 — Mortal..Celestial. O prompt do lote dizia
// que o artefacto tinha QUATRO degraus; esses quatro sao a qualidade de forja,
// que o motor infere post-hoc e o refino apaga. Ver `NIV_RANK_SCALES`.)
// ⚠️ O caso que so a escala com `base:0` acerta: grau 0 tem de acender 1 de 9,
// nunca devolver null. "Grau desconhecido" e "grau mais baixo" sao coisas
// diferentes e a carta nao as pode confundir.
for (let g = 0; g <= 8; g++) {
  const r = nivRank("artifact", g);
  chk(r && r.i === g && r.n === 9 && r.label === "art_grade_" + g,
      `artefacto G${g} -> ${g + 1} de 9 (${r && r.label})`);
}
chk(nivRank("artifact", 0) !== null, "artefacto G0 tem lombo (1 de 9), NAO e null");
chk(nivRank("artifact", 12) && nivRank("artifact", 12).i === 8
    && nivRank("artifact", 12).label === "art_grade_8",
    "artefacto acima da escala satura no TOPO e rotula o degrau GRAMPEADO");
chk(nivRank("artifact", -1) === null, "artefacto abaixo da escala -> null");

// ── 3c. as outras tres escalas do lote ─────────────────────────────────────
const LAW = ["common", "uncommon", "rare", "epic", "legendary"];
LAW.forEach((g, i) => {
  const r = nivRank("dao_law", g);
  chk(r && r.i === i && r.n === 5 && r.label === "law_rank_" + g,
      `lei do Dao ${g} -> ${i + 1} de 5`);
});
// ⚠️ Na armadilha `mythic` esta ABAIXO de `legendary` — ao contrario da besta.
// Nao e gralha: e `TRAP_QUALITY_ORDER` do `core/beast_engine.py`. A carta segue
// o motor de CADA conteudo, e e por isso que ha oito vocabularios.
const TRAP = ["normal", "common", "rare", "epic", "mythic", "legendary"];
TRAP.forEach((g, i) => {
  const r = nivRank("trap", g);
  chk(r && r.i === i && r.n === 6 && r.label === "trap_rank_" + g,
      `armadilha ${g} -> ${i + 1} de 6`);
});
chk(nivRank("trap", "mythic").i < nivRank("trap", "legendary").i,
    "armadilha: mythic ABAIXO de legendary (o motor manda, nao a intuicao)");
chk(nivRank("beast", "Mythic").i > nivRank("beast", "Legendary").i,
    "besta: mythic ACIMA de legendary — as duas escalas discordam, e ambas estao certas");
const GACHA = ["common", "rare", "epic", "legendary"];
GACHA.forEach((g, i) => {
  const r = nivRank("gacha", g);
  chk(r && r.i === i && r.n === 4 && r.label === "gacha_rank_" + g,
      `gacha ${g} -> ${i + 1} de 4`);
});

// ── 4. o silencio: nada de lombo errado ────────────────────────────────────
chk(nivRank("technique", "godlike") === null, "grau desconhecido -> null (sem lombo)");
chk(nivRank("beast", "Ancient") === null, "posto desconhecido -> null");
chk(nivRank("technique", null) === null, "null -> null");
chk(nivRank("technique", "") === null, "string vazia -> null");
chk(nivRank("technique", undefined) === null, "undefined -> null");
chk(nivRank("armadilha", "rare") === null, "escala nao registada -> null");
chk(nivRank("artifact", null) === null, "artefacto null -> null");
chk(nivRank("artifact", "x") === null, "artefacto nao-numerico -> null");
chk(nivRank("dao_law", "godlike") === null, "lei desconhecida -> null");
chk(nivRank("trap", "cosmic") === null, "armadilha desconhecida -> null");
chk(nivRank("pill", 0) === null, "pilula grau 0 -> null (a escada comeca em 1)");
chk(nivRank("pill", "x") === null, "pilula nao-numerica -> null");

// ── 5. duas escalas de comprimentos diferentes NUNCA colidem ───────────────
// E a razao de o lombo existir: o "Rare" de uma besta e 3/7 e o "perfected" de
// uma arte e 3/5. Sao o mesmo indice e NAO sao a mesma raridade.
const rb = nivRank("beast", "Rare"), rt = nivRank("technique", "perfected");
chk(rb.i === rt.i && rb.n !== rt.n,
    `mesmo indice (${rb.i}), escalas diferentes (${rb.n} vs ${rt.n}) — o lombo di-lo, uma cor nao`);

// ── 6. 器 OS TRES PATAMARES (2026-09-10) — CORRIDOS, nao lidos ────────────
//
// Ler a fonte prova que os cortes estao la; nao prova ONDE eles caem em cada
// uma das oito escalas. E e' isso que decide se o topo continua a ser topo.
//
// A regra: `p = i/(n-1)`; celeste >= .90 (o degrau do topo, em qualquer
// escala), notavel >= .60. TRES patamares, nunca nove (Lei §3), e derivados da
// POSICAO — nunca de uma lista de nomes, que envelhece em silencio.
const TIER_EXPECT = {
  // escala de 5: so' o 5o e celeste, so' o 4o e notavel
  technique: ["common", "common", "common", "notable", "celestial"],
  // escala de 7: `divine` celeste, `legendary`+`mythic` notaveis
  beast:     ["common", "common", "common", "common", "notable", "notable", "celestial"],
  // escala de 5 numerica (1..5)
  pill:      ["common", "common", "common", "notable", "celestial"],
  // ⚠️ escala de NOVE, e a unica que comeca em zero: G8 celeste, G5-G7 notaveis
  artifact:  ["common", "common", "common", "common", "common",
              "notable", "notable", "notable", "celestial"],
  dao_law:   ["common", "common", "common", "notable", "celestial"],
  trap:      ["common", "common", "common", "notable", "notable", "celestial"],
  gacha:     ["common", "common", "notable", "celestial"],
};
const TIER_VALUES = {
  technique: TEC,
  beast: BST,
  pill: [1, 2, 3, 4, 5],
  artifact: [0, 1, 2, 3, 4, 5, 6, 7, 8],
  dao_law: LAW,
  trap: TRAP,
  gacha: GACHA,
};
Object.keys(TIER_EXPECT).forEach(kind => {
  const vals = TIER_VALUES[kind];
  const got = vals.map(v => nivTier(nivRank(kind, v)));
  chk(JSON.stringify(got) === JSON.stringify(TIER_EXPECT[kind]),
      `patamar ${kind}: ${got.join("/")}`);
  // ⚠️ Em TODA escala, celeste e' exactamente UM degrau — o de cima. Se um dia
  // alguem baixar o corte, duas escalas passam a ter dois topos e esta linha
  // fica vermelha antes de a mochila ficar toda a brilhar.
  const nCel = got.filter(x => x === "celestial").length;
  chk(nCel === 1 && got[got.length - 1] === "celestial",
      `patamar ${kind}: UM so' degrau celeste, e e' o de cima (${nCel})`);
  chk(got[0] === "common", `patamar ${kind}: o degrau de baixo e' comum`);
});

// O silencio herda: sem posto reconhecido nao ha' ornamento nenhum. Ornamentar
// o que nao se sabe medir e' afirmar uma raridade que ninguem verificou — a
// mesma razao por que um grau desconhecido nao desenha lombo.
chk(nivTier(nivRank("technique", "godlike")) === "common",
    "patamar: grau desconhecido -> comum (nunca se ornamenta o que nao se mede)");
chk(nivTier(null) === "common", "patamar: null -> comum");
chk(nivTier(undefined) === "common", "patamar: undefined -> comum");
chk(nivTier({ i: 0, n: 1 }) === "common",
    "patamar: escala de UM degrau -> comum (sem divisao por zero)");
chk(nivTier({ i: 0, n: 0 }) === "common", "patamar: escala vazia -> comum");

// ⚠️ Duas escalas de comprimentos DIFERENTES nao colidem no patamar, tal como
// nao colidem no lombo. `Rare` de besta e 3/7 e `perfected` de arte e 3/5 —
// mesmo indice, e o patamar tem de continuar a nao os confundir.
chk(nivTier(nivRank("beast", "Rare")) === "common"
    && nivTier(nivRank("technique", "perfected")) === "common",
    "patamar: mesmo indice em escalas diferentes continua a nao mentir");
// ...e a prova simetrica: o 4o degrau de 5 e notavel, o 4o de 7 ainda e comum.
chk(nivTier(nivRank("technique", "transcendent")) === "notable"
    && nivTier(nivRank("beast", "Epic")) === "common",
    "patamar: 4 de 5 e' notavel, 4 de 7 ainda nao — a escala e' que manda");

console.log(bad ? `\n${bad} FALHAS` : "\ntodos verdes");
process.exit(bad ? 1 : 0);
