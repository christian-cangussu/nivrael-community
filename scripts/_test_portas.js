// 門 P6 — AS PORTAS, executadas a sério.
//
// Porque existe: ler a fonte prova que `portasDoHub(` está escrito num sítio;
// não prova que a regra do marco escolhe a porta certa. Este harness extrai do
// `ui.js` e do `tabs.js` REAIS (nunca uma cópia — uma cópia diverge no primeiro
// sprint) o `HUB_DEFS`, o `portaDe`, o `portasDoHub`, o `EU_PORTAS` e o
// `euPortasVisiveis`, e corre-os contra:
//
//   1. os `nav_gates` que o `core/portas.py` REAL produz para cada reino e cada
//      combinação de flags — gerados pela suíte Python e passados por stdin (a
//      lição de 06/09: comparar com os DADOS do dono, não com números meus);
//   2. cargas ROTAS escritas à mão: sem `nav_gates`, `open:null`, `kind`
//      desconhecido, a onda desligada com o campo presente.
//
// A frase que justifica o ficheiro é do Astra: *"nunca opção (c) para um
// bloqueio conhecido"* — e *"estado desconhecido mostra verificação/erro, sem
// fingir desbloqueio"*. Chamado por `scripts/_test_web_c_superficies.py` §29.
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..");
const ui = fs.readFileSync(path.join(ROOT, "miniapp/components/ui.js"), "utf8");
const tabs = fs.readFileSync(path.join(ROOT, "miniapp/components/tabs.js"), "utf8");

function fatia(src, de, ate, nome) {
  const a = src.indexOf(de);
  const b = src.indexOf(ate, a + de.length);
  if (a < 0 || b < 0) {
    console.log("FAIL: nao achei o bloco " + nome);
    process.exit(1);
  }
  return src.slice(a, b);
}

const hubSrc = fatia(ui, "    var HUB_DEFS = [", "\n    ];\n", "HUB_DEFS") + "\n    ];\n";
const donoSrc = fatia(ui, "    function portasOn(player) {", "    var PORTA_CAMINHOS = {", "portasOn..portasDoHub");
const euSrc = fatia(tabs, "    var EU_PORTAS = [", "    function HubEuScreen(", "EU_PORTAS..euPortasVisiveis");

let ONDA = true;
const tk = (k, p) => (p ? k + ":" + JSON.stringify(p) : k);
const K = new Function("ondaCultOn", "t",
  hubSrc + donoSrc + euSrc +
  "\nreturn { HUB_DEFS, portasOn, portaDe, portasDoHub, EU_PORTAS, euPortasVisiveis };")(
  () => ONDA, tk);

let bad = 0;
function chk(cond, msg) {
  console.log((cond ? "ok   " : "FAIL ") + msg);
  if (!cond) bad++;
}

let dados = {};
try { dados = JSON.parse(fs.readFileSync(0, "utf8") || "{}"); } catch (e) { dados = {}; }
const casos = dados.casos || {};
const MIN = dados.min || {};

const hubKeys = (hk) => {
  const h = K.HUB_DEFS.find((x) => x.key === hk);
  return h ? h.group.filter((k) => !k.endsWith("_screen") && k !== "home") : [];
};
const EU = hubKeys("hub_eu");
const MUNDO = hubKeys("hub_mundo");
const jog = (gates, extra) => Object.assign({ nav_gates: gates, prestige_level: 0 }, extra || {});
const est = (p, k) => K.portaDe(p, k).estado;
const naLista = (r, k) => r.lista.some((x) => x.key === k);
const distante = (r, k) => r.distantes.some((x) => x.key === k);

// ── 0. o que se mede tem de existir ─────────────────────────────────────────
chk(Object.keys(casos).length >= 20,
    `as cargas vem do core/portas.py REAL (${Object.keys(casos).length} casos)`);
chk(EU.includes("body_tempering") && EU.includes("celestial") && MUNDO.includes("faction"),
    "o HUB_DEFS real poe o Corpo e a Celestial no Eu e a Faccao no Mundo");

// ── 1. cada reino × cada mundo, contra o SERVIDOR ──────────────────────────
// Para cada carga produzida pelo dono: a porta abre no cliente SE E SO' SE o
// servidor disse `open:true`; trancada leva o numero do servidor; e o marco
// de cada hub e' a trancada de menor requisito.
Object.keys(casos).forEach((nome) => {
  const c = casos[nome];
  const p = jog(c.gates);
  Object.keys(c.gates).forEach((k) => {
    const g = c.gates[k];
    const e = est(p, k);
    if (g.open === true) chk(e === "aberta", `${nome}: ${k} aberta no servidor ⇒ aberta no cliente`);
    else if (g.open === false) {
      const pd = K.portaDe(p, k);
      chk(e === "trancada" && pd.precisa === g.need && pd.tem === g.have,
          `${nome}: ${k} trancada ⇒ trancada, com o numero do SERVIDOR (${g.need})`);
    }
  });
  [["Eu", EU], ["Mundo", MUNDO]].forEach(([hn, keys]) => {
    const r = K.portasDoHub(p, keys, null);
    const tr = keys.filter((k) => est(p, k) === "trancada");
    // nunca uma porta desaparece por inteiro: ou esta' na lista ou na consulta
    chk(keys.every((k) => naLista(r, k) !== distante(r, k)),
        `${nome}/${hn}: cada destino esta' na lista OU nos distantes, nunca nos dois nem em nenhum`);
    // toda aberta fica na lista (a navegacao corrente nao perde portas abertas)
    chk(keys.filter((k) => est(p, k) === "aberta").every((k) => naLista(r, k)),
        `${nome}/${hn}: toda porta aberta fica na lista`);
    if (tr.length) {
      const marco = Math.min(...tr.map((k) => K.portaDe(p, k).precisa));
      chk(tr.every((k) => naLista(r, k) === (K.portaDe(p, k).precisa === marco)),
          `${nome}/${hn}: so' o proximo marco (Reino ${marco}) fica a' vista, os outros vao para «Desbloqueios»`);
    } else {
      chk(r.distantes.length === 0, `${nome}/${hn}: sem trancadas, «Desbloqueios» vazio`);
    }
  });
});

// ── 2. os casos que a regra do Astra nomeia ────────────────────────────────
const r0 = casos["r0|-"];
if (r0) {
  const p = jog(r0.gates);
  const eu = K.portasDoHub(p, EU, null);
  chk(naLista(eu, "body_tempering") && distante(eu, "celestial"),
      "R0 sem Refino Mortal: o Corpo (R" + MIN.body + ") e' o marco do Eu, a Celestial (R" + MIN.celestial + ") vai para a consulta");
  // *"alcancado por atalho continua identificavel"*
  const aqui = K.portasDoHub(p, EU, "celestial");
  chk(naLista(aqui, "celestial"), "a porta onde o jogador ESTA' (atalho) fica identificavel na lista");
  // *"antes acessivel"*: um renascido ja' esteve do outro lado
  const ren = K.portasDoHub(jog(r0.gates, { prestige_level: 1 }), EU, null);
  chk(naLista(ren, "celestial") && naLista(ren, "body_tempering") && !ren.distantes.length,
      "um RENASCIDO ve todas as trancadas do hub (antes acessiveis), nada escondido na consulta");
  // empate agrupa
  const emp = jog({ faction: { open: false, kind: "realm", need: 3, have: 0 },
                    celestial: { open: false, kind: "realm", need: 3, have: 0 } });
  const re = K.portasDoHub(emp, ["faction", "celestial", "guild"], null);
  chk(naLista(re, "faction") && naLista(re, "celestial"),
      "requisitos EMPATADOS ficam agrupados no mesmo marco");
}
const s2 = casos["r1|cultivo_corpo_r0"];
if (s2) {
  const eu = K.portasDoHub(jog(s2.gates), EU, null);
  chk(est(jog(s2.gates), "body_tempering") === "aberta" && naLista(eu, "celestial") && !eu.distantes.length,
      "mundo com o Refino Mortal (o s2): o Corpo abre em R1 e a Celestial passa a ser o marco");
}

// ── 3. as cargas ROTAS — nunca a opcao (c) ─────────────────────────────────
const tr = { open: false, kind: "realm", need: 3, have: 0 };
chk(est(jog({ faction: { open: null } }), "faction") === "incerta",
    "`open:null` (o servidor nao conseguiu calcular) ⇒ INCERTA, nunca aberta");
chk(est(jog({ faction: { open: false, kind: "quest" } }), "faction") === "incerta",
    "um `kind` que o cliente nao sabe dizer ⇒ incerta, nunca aberta nem um numero inventado");
chk(est(jog({ faction: { open: false, kind: "realm" } }), "faction") === "incerta",
    "trancada sem `need` ⇒ incerta (nao ha' numero para mostrar)");
chk(est(jog({ faction: {} }), "faction") === "incerta", "uma porta vazia ⇒ incerta");
chk(K.portasDoHub(jog({ faction: { open: null } }), MUNDO, null).lista.some((x) => x.key === "faction"),
    "a incerta fica na LISTA (identificavel), nunca na consulta");
chk(est({ prestige_level: 0 }, "faction") === "aberta",
    "sem `nav_gates` (servidor antigo / onda OFF no servidor) ⇒ o que se ve hoje");
chk(est(null, "faction") === "aberta", "sem jogador ⇒ aberta (nada a desenhar)");
ONDA = false;
chk(est(jog({ faction: tr }), "faction") === "aberta"
    && K.portasDoHub(jog({ faction: tr }), MUNDO, null).distantes.length === 0,
    "OFF-identidade: com a onda desligada TODA porta e' aberta, mesmo com o campo presente");
ONDA = true;

// ── 4. a maçaneta nomeia o mesmo conjunto do selector ───────────────────────
if (r0) {
  const p = jog(r0.gates);
  const eu = K.euPortasVisiveis(p, K.EU_PORTAS);
  const vis = eu.visiveis.map((x) => x.key);
  chk(eu.nomes.length === eu.visiveis.length,
      "maçaneta: nomeia EXACTAMENTE as portas do selector (nem mais, nem menos)");
  chk(!vis.includes("tab_celestial") && eu.distantes.some((x) => x.key === "celestial"),
      "maçaneta: a Celestial distante nao aparece nem se conta; esta' na consulta");
  const nTr = eu.visiveis.filter((x) => eu.porta(x).estado !== "aberta").length;
  chk(nTr >= 1 && eu.nomes.slice(-nTr).every((n) => n === "tab_body_tempering"),
      "maçaneta: as trancadas vao para o FIM — nenhuma entre os tres nomes a' vista");
  chk(eu.nomes.slice(0, 3).every((n) => n !== "tab_body_tempering"),
      "maçaneta: os tres nomes a' vista abrem todos (a opcao (c), em texto, morta)");
}

console.log(bad ? `\n${bad} FAIL` : "\ntodas verdes");
process.exit(bad ? 1 : 0);
