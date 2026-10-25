// 星 2.1 O CORPO QUE ACENDE — as três LEITURAS, executadas a sério.
//
// Porque existe: ler a fonte prova que o código está lá; não prova que ele lê
// bem. Este harness extrai do `tabs.js` REAL (nunca uma cópia — uma cópia
// diverge no primeiro sprint, a lição do `_test_web_c_cutpoint.js`) as âncoras,
// o mapa dos canais e as três funções puras (`corpoLerMortal`,
// `corpoLerTransf`, `corpoLerMer`) e corre-as contra:
//
//   1. cargas produzidas pelos MOTORES do servidor (`project_body_for_display`,
//      a forma do `api_body_tempering_status`, `project_meridians`), geradas
//      pela suíte Python e passadas por stdin — a lição de 06/09: comparar com
//      os DADOS do dono, não só com o que eu acho que ele manda;
//   2. cargas ROTAS escritas à mão: a forma genérica do arnês (`ok:true` e
//      mais nada — "o mock fabrica sucesso" em 247 de 265 endpoints), a
//      recusa `ok:false`, a lista parcial, a ordem baralhada.
//
// O que justifica o ficheiro, numa frase do Astra: *"Um `0 / 12` só aparece se
// for um zero confirmado."* Sem leitura, a função devolve `null` — nunca zero.
// Chamado por `scripts/_test_web_c_superficies.py` §25.
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..");
const src = fs.readFileSync(path.join(ROOT, "miniapp/components/tabs.js"), "utf8");

const start = src.indexOf("    var CORPO_PARES = [");
const end = src.indexOf("    // Os meridianos só se pedem num mundo que os tem.");
if (start < 0 || end < 0 || end <= start) {
  console.log("FAIL: nao achei o bloco das leituras do Corpo no tabs.js");
  process.exit(1);
}
const body = src.slice(start, end);
// `t`/`safeT` devolvem a PRÓPRIA chave: o teste prova também que o nome de
// cada etapa vem da chave CERTA do servidor, e não só a contagem.
const f = new Function("t", "safeT", "ondaNomeLimpo", body +
  "\nreturn { CORPO_ANCORAS, CORPO_PARES, CORPO_MER_LUGAR, corpoVariante, corpoLugaresDe," +
  " corpoLerMortal, corpoLerTransf, corpoLerMer };");
const K = f((k, p) => (p ? k + ":" + JSON.stringify(p) : k),
            (k, p, fb) => (k ? k : (fb || "")),
            (s) => String(s == null ? "" : s));

let bad = 0;
function chk(cond, msg) {
  console.log((cond ? "ok   " : "FAIL ") + msg);
  if (!cond) bad++;
}
const conta = (pts, e) => pts.filter((p) => p.estado === e).length;

let dados = {};
try { dados = JSON.parse(fs.readFileSync(0, "utf8") || "{}"); } catch (e) { dados = {}; }

// ── 0. as âncoras: três variantes, 7 na costura, 6 pares espelhados ────────
["male", "female", "back"].forEach((v) => {
  const a = K.CORPO_ANCORAS[v];
  chk(a && a.seam.length === 7 && a.pares.length === 6, `âncoras ${v}: 7 na costura e 6 pares`);
  const todas = a.seam.concat(a.pares.map((p) => [p[0], p[2]]), a.pares.map((p) => [p[1], p[2]]));
  chk(todas.every((p) => p[0] > 0 && p[0] < 100 && p[1] > 0 && p[1] < 100),
      `âncoras ${v}: todas dentro da pintura (0..100%)`);
  chk(a.pares.every((p) => Math.abs(p[0] + p[1] - 100) < 0.01),
      `âncoras ${v}: os pares são ESPELHADOS no eixo do corpo`);
  chk(a.seam.every((p, i) => i === 0 || p[1] < a.seam[i - 1][1]),
      `âncoras ${v}: a costura SOBE da cintura à testa`);
  chk(K.corpoLugaresDe("mortal", v).length === 7 && K.corpoLugaresDe("transf", v).length === 12,
      `lugares ${v}: 7 no Refino, 12 nas Transformações/Meridianos`);
});
chk(K.corpoVariante("male") === "male" && K.corpoVariante("female") === "female"
    && K.corpoVariante(null) === "back" && K.corpoVariante("x") === "back",
    "variante: masculino, feminino, e 背影 de costas para quem não escolheu");

// ── 1. o mapa dos canais é o do MOTOR ─────────────────────────────────────
const MOTOR = dados.canais_do_motor || [];
chk(MOTOR.length === 12, `o motor tem 12 canais (${MOTOR.length})`);
chk(Object.keys(K.CORPO_MER_LUGAR).length === 12
    && MOTOR.every((k, i) => {
      const l = K.CORPO_MER_LUGAR[k];
      return l && l[0] === Math.floor(i / 2) && l[1] === i % 2;
    }),
    "o mapa dos canais é EXACTAMENTE o do motor, par a par (肺/大肠 · 胃/脾 · …)");

// ── 2. Refino Mortal, pelos dados do motor ────────────────────────────────
(dados.mortal || []).forEach((c) => {
  const l = K.corpoLerMortal(c.bc, null);
  chk(l && l.L === c.bc.mortal_level && l.M === c.bc.max_level && l.pontos.length === c.bc.max_level,
      `mortal ${c.rotulo}: ${l && l.L} / ${l && l.M}`);
  chk(l && conta(l.pontos, "got") === c.bc.mortal_level,
      `mortal ${c.rotulo}: acende ${c.bc.mortal_level} — nem mais, nem menos`);
  const prox = l && l.pontos[c.bc.mortal_level];
  if (c.bc.mortal_level < c.bc.max_level) {
    const esperado = (c.bc.is_apex || c.bc.at_realm_cap) ? "locked" : "next";
    chk(prox && prox.estado === esperado,
        `mortal ${c.rotulo}: a etapa seguinte está "${esperado}" (${prox && prox.estado})`);
  }
  chk(l && l.pontos.every((p, i) => p.nome === c.bc.tier_keys[i]),
      `mortal ${c.rotulo}: cada ponto tem o nome da chave do servidor, pela ORDEM do servidor`);
});
chk((dados.mortal || []).length >= 8, `mortal: casos do motor recebidos (${(dados.mortal || []).length})`);

// o número muda com a CONFIRMAÇÃO, só para cima e só até ao máximo
{
  const bc = (dados.mortal || [])[2] && (dados.mortal || [])[2].bc;
  if (bc) {
    chk(K.corpoLerMortal(bc, bc.mortal_level + 1).L === bc.mortal_level + 1,
        "mortal: a confirmação do servidor sobe o número sem esperar o refresh");
    chk(K.corpoLerMortal(bc, 99).L === bc.mortal_level, "mortal: confirmação ACIMA do máximo é ignorada");
    chk(K.corpoLerMortal(bc, 0).L === bc.mortal_level, "mortal: confirmação ABAIXO do actual é ignorada");
    const b5 = Object.assign({}, bc, { max_level: 5, tier_keys: bc.tier_keys.slice(0, 5), mortal_level: 1 });
    chk(K.corpoLerMortal(b5, null).pontos.length === 5, "mortal: o MÁXIMO do payload manda (5 pontos, não 7)");
  }
}
chk(K.corpoLerMortal(null, null) === null, "mortal: sem `body_cultivation` → sem leitura (null, não zero)");
chk(K.corpoLerMortal({ tier_key: "body_tier_pele" }, null) === null,
    "mortal: sem `max_level`/`mortal_level` → sem leitura");

// ── 3. Transformações, pela forma do `api_body_tempering_status` ─────────
(dados.transf || []).forEach((c) => {
  const l = K.corpoLerTransf(c.d, null);
  chk(l && l.L === c.d.current_level && l.M === c.d.max_level && conta(l.pontos, "got") === c.d.current_level,
      `transf ${c.rotulo}: ${l && l.L} / ${l && l.M}, acende ${c.d.current_level}`);
  chk(l && l.pontos.every((p, i) => p.nome === c.d.levels[i].name_key),
      `transf ${c.rotulo}: nomes pelas chaves do motor`);
  if (c.d.current_level < c.d.max_level) {
    const nx = l.pontos[c.d.current_level];
    const tranca = !c.d.unlocked || (c.d.next && /need_(celestial_)?realm$/.test(c.d.next.blocked_reason_key || ""));
    chk(nx.estado === (tranca ? "locked" : "next"),
        `transf ${c.rotulo}: o próximo nível está "${tranca ? "locked" : "next"}" (${nx.estado})`);
  }
});
chk((dados.transf || []).length >= 3, `transf: casos do motor recebidos (${(dados.transf || []).length})`);
chk(K.corpoLerTransf({ ok: true, items: [], list: [], data: {} }, null) === null,
    "transf: a forma GENÉRICA do arnês (`ok:true` e mais nada) NÃO vira 0 / 12");
chk(K.corpoLerTransf({ ok: false, reason: "x" }, null) === null, "transf: `ok:false` → sem leitura");
chk(K.corpoLerTransf(null, null) === null, "transf: sem resposta → sem leitura");

// ── 4. Meridianos, pelo `project_meridians` do motor ──────────────────────
(dados.mer || []).forEach((c) => {
  const l = K.corpoLerMer(c.d, null);
  const abertos = c.d.channels.filter((x) => x.state === "open").length;
  chk(l && l.mapaOk && l.L === c.d.opened_count && conta(l.pontos, "got") === abertos,
      `mer ${c.rotulo}: ${l && l.L} / ${l && l.M}, acende ${abertos}`);
  const slots = l ? l.pontos.map((p) => p.slot) : [];
  chk(new Set(slots).size === 12 && slots.every((s) => s >= 0 && s < 12),
      `mer ${c.rotulo}: 12 canais em 12 lugares distintos`);
  if (c.d.ritual) {
    chk(l.pontos.find((p) => p.id === c.d.ritual.channel).estado === "ritual",
        `mer ${c.rotulo}: o canal em ritual está EM CURSO, não aceso`);
  }
  // a ordem da resposta não desloca conquistas
  const bar = Object.assign({}, c.d, { channels: c.d.channels.slice().reverse() });
  const lb = K.corpoLerMer(bar, null);
  chk(lb && lb.pontos.every((p) => p.slot === l.pontos.find((q) => q.id === p.id).slot
                                   && p.estado === l.pontos.find((q) => q.id === p.id).estado),
      `mer ${c.rotulo}: baralhar a ordem dos canais NÃO muda nenhum lugar nem estado`);
});
chk((dados.mer || []).length >= 3, `mer: casos do motor recebidos (${(dados.mer || []).length})`);
{
  const m = (dados.mer || []).find((c) => c.d.ritual);
  if (m) {
    const l = K.corpoLerMer(m.d, m.d.ritual.channel);
    chk(l.pontos.find((p) => p.id === m.d.ritual.channel).estado === "got" && l.L === m.d.opened_count + 1,
        "mer: o canal CONFIRMADO aberto acende e conta +1 antes do refresh");
    const parc = Object.assign({}, m.d, { channels: m.d.channels.slice(0, 6) });
    const lp = K.corpoLerMer(parc, null);
    chk(lp && !lp.mapaOk && lp.L === m.d.opened_count,
        "mer: lista PARCIAL com contador → o mapa não se desenha (lista textual) e o número é o do servidor");
    const semContador = Object.assign({}, parc);
    delete semContador.opened_count;
    chk(K.corpoLerMer(semContador, null) === null,
        "mer: lista parcial SEM contador → sem leitura (contar os abertos da metade inventava um número)");
    const estranho = Object.assign({}, m.d, { channels: m.d.channels.map((x, i) => i === 0 ? Object.assign({}, x, { key: "canal_novo" }) : x) });
    chk(!K.corpoLerMer(estranho, null).mapaOk, "mer: uma chave DESCONHECIDA não entra no mapa à força");
  }
}
chk(K.corpoLerMer({ ok: true, items: [], list: [], data: {} }, null) === null,
    "mer: a forma GENÉRICA do arnês NÃO vira 0 / 12");
chk(K.corpoLerMer({ ok: false, reason: "mer_locked" }, null) === null, "mer: `mer_locked` → sem leitura");

console.log(bad ? `FAIL ${bad}` : "ok   todas as leituras do Corpo");
process.exit(bad ? 1 : 0);
