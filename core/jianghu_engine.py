"""MV-8 — O JIĀNGHÚ 江湖 ("Rios e Lagos"): o mundo passa a QUERER coisas.

Mundo Vivo v2, pilar P4 (`GameDesign/MUNDO_VIVO_V2_CRIMSON.md §3-P4`). O mundo já
tinha LUGAR (MV-1), MOVIMENTO (MV-2), MEMÓRIA (MV-3), CORPO (MV-4), QUESTS que só
existem quando o mundo as torna verdadeiras (MV-5), REPUTAÇÃO e um RIVAL (MV-6) e
OFÍCIO (MV-7) — mas os `npc_cultivators` continuavam estátuas com stats: não
queriam nada, não iam a lado nenhum, não anunciavam nada e nunca vinham atrás de
ninguém. Este engine paga a metade do mandato que o owner gritou em CAPS:
*"AÇÃO E REAÇÃO + CÂMBIOS. MUNDO SE MOVE, EXISTE DE VERDADE."*

O DESENHO (§2.4 da pesquisa — F.E.A.R. GOAP + The Sims smart objects):
    a inteligência PERCEBIDA vem de o NPC **ANUNCIAR** o plano, não do planner.
    Logo: um planner deliberadamente burro (utilidade ponderada + argmax, o
    MESMO molde de `world_pulse_engine.score_actions`) sobre um QUADRO de
    oportunidades DERIVADO do mundo vivo — e o anúncio do NPC é, literalmente,
    a mesma linha de `world_chronicle` que o jogador lê. Simulação e interface
    saem da MESMA tabela.

AS RESTRIÇÕES QUE MANDAM (recon 2026-08-04 + verificação pré-código 2026-08-05):

  1. **O elenco é SÓ `origin='seed'`.** A "restrição-mãe" herdada do MV-6 ("a row
     do NPC nunca é mutada") é falsa na letra e verdadeira onde importa: rows
     `origin='echo'` têm name/realm/continent_key/sect_id/karma/power/loadout/
     status RE-ASSINADOS a cada 6h por `snapshot_player_to_npc._assign` (o match
     é por `source_hash`), enquanto as rows `origin='seed'` têm `source_hash NULL`
     e NENHUM job as reescreve. Escrever um plano num echo é escrever na areia —
     e pior, de forma NÃO-determinística (o snapshot só varre os 20 jogadores mais
     recentes, então a escrita sobrevive ou não conforme a atividade alheia).
     Prod confirma que estado mutado em seed PERSISTE: o s2 tem 18 seeds
     'ascended' há dias.

  2. **ZERO migration.** O plano não precisa de tabela: o goal é uma FUNÇÃO PURA
     semeada por `(world_key, npc_id, tick_epoch)` que resolve DENTRO do próprio
     tick. Não há "plano pendente" a persistir — há um ATO e a sua consequência
     (o `continent_key` movido + a linha de Chronicle). O que precisa sobreviver
     ao tick vive em `npc_cultivators.loadout` (JSONB, seed-only) e em
     `region_states.payload` (com MERGE — o padrão já provado 2×).

  3. **O `world_key` entra em TODA semente.** `world_pulse_engine` semeia com
     `(sect_id, tick_epoch)` sem o mundo — e o resultado medido é que main e s2
     contaram a MESMA história por 7 dias (fortify 135, raid_rival 30, recruit 26
     em AMBAS). Um "mundo vivo" que é idêntico em todo servidor não é vivo.

  4. **Orçamento NARRATIVO, não de CPU.** O Postgres varre os 94 NPCs em 0,52 ms;
     o teto real é a Chronicle, que recebe ~30 linhas/dia e cuja superfície mais
     vista mostra **4**. Por isso: K atores por continente por tick (não "todos"),
     e um orçamento de ANÚNCIOS separado e menor que o de ações — a maioria dos
     atos muda estado em SILÊNCIO e só é revelada a quem está lá.

  5. **Por continente, nunca global.** A população é grosseiramente concentrada
     (Línghé 49 dos 94 ativos; Mòyǔ 8). Um teto global faria o jiānghú acontecer
     todo em Línghé — o mesmo defeito que o TEC-4 teve de corrigir com drift.

Leis: §1 (nada de void silencioso — todo ato anunciado tem fecho) · §2 (é vendeta
e notícia que corre, não "NPC schedule") · §3 (4 goals profundos, não 20 rasos) ·
§5 (flag OFF em TODO mundo; OFF ⇒ zero query, payload byte-idêntico).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
# `time as _time` é a convenção da casa (`scheduler.py` já importa assim); um
# `import time` cru criaria um nome duplicado quando este engine for lido lado
# a lado com o scheduler. O MV-8 é o PRIMEIRO passo O(N) a entrar no batimento
# e o pulse não tinha NENHUMA instrumentação de tempo — daí o monotonic().
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from core.continent_engine import CONTINENT_KEYS, is_valid_continent
from database.models import NpcCultivator

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Flag + knobs (engine, não DB — env-overridable; padrão RST_*/STORYLET_*)
# ══════════════════════════════════════════════════════════════════════════

def jianghu_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (molde literal de `reputacao_on`). Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("jianghu", world_key))
    except Exception:
        return False


# Quantos NPCs agem por continente por tick. O limite NÃO é o Postgres (94 rows
# em 0,52 ms) — é a Chronicle. Por CONTINENTE para Mòyǔ (8 NPCs) ter tanto
# jiānghú quanto Línghé (49).
JH_ACTORS_PER_CONTINENT = int(os.getenv("JH_ACTORS_PER_CONTINENT", "3"))
# Quantos dos atos viram LINHA na Chronicle. Menor que o de ações de propósito:
# hoje entram ~30 linhas/dia e a tira da Praça mostra 4 — 2/tick = 8/dia mantém
# o NPC em ~21% do log e deixa as 9 casas legíveis. NUNCA 1-por-NPC-por-tick
# (seriam 376/dia contra 30 — o mundo sumiria atrás do próprio ruído).
JH_ANNOUNCE_PER_TICK = int(os.getenv("JH_ANNOUNCE_PER_TICK", "2"))
# Um NPC que acabou de agir descansa (espalha o palco em vez de um só repetir —
# molde do `WORLD_PULSE_MAJOR_COOLDOWN_HOURS` das 9 casas).
JH_ACTOR_COOLDOWN_HOURS = float(os.getenv("JH_ACTOR_COOLDOWN_HOURS", "18"))
# Ruído semeado da decisão (mantém os batimentos variados e reproduzíveis).
JH_NOISE = float(os.getenv("JH_NOISE", "0.15"))
# TETO da influência do Quadro sobre a decisão. O anúncio do lugar INCLINA, nunca
# DITA: sem este teto, uma única oportunidade forte (um Meteoro, uma Maré) fazia
# 100% dos NPCs do mundo marcharem para o mesmo continente no mesmo tick — o
# mundo inteiro em fila indiana, que é precisamente o "cron job com nomes
# chineses" que este engine existe para não ser. Com o teto, a ALMA continua a
# mandar e o mundo só desempata.
JH_OFFER_MAX = float(os.getenv("JH_OFFER_MAX", "0.22"))

# ── Pesos do QUADRO (o que cada lugar ANUNCIA) — puros, somados em `offers_for`
# A linha PERMANENTE: TODO continente tem material nativo (REGIONAL_BONUS_LOOT).
# É ela que impede o Quadro de Mòyǔ de nascer VAZIO — sem ela, um continente
# sem evento/gruta/contrato não teria motivo nenhum e a Lei §1 quebraria pelo
# lado do mundo (um lugar onde nada acontece nunca é escolhido, para sempre).
JH_OFFER_NATIVE = float(os.getenv("JH_OFFER_NATIVE", "0.06"))
JH_OFFER_EVENT = float(os.getenv("JH_OFFER_EVENT", "0.10"))      # Maré/Meteoro (MV-2)
JH_OFFER_CAVE = float(os.getenv("JH_OFFER_CAVE", "0.10"))        # Gruta do Legado (TEC-4)
JH_OFFER_UNREST = float(os.getenv("JH_OFFER_UNREST", "0.08"))    # tensa/sitiada/ocupada
JH_OFFER_FESTIVAL = float(os.getenv("JH_OFFER_FESTIVAL", "0.05"))
JH_OFFER_BOUNTY = float(os.getenv("JH_OFFER_BOUNTY", "0.08"))    # por contrato URGENTE (≤2)
JH_OFFER_VENDETA = float(os.getenv("JH_OFFER_VENDETA", "0.06"))  # por rival de CAMINHO local (≤2)

# ⚠️ LEI DE FERRO DO QUADRO, aprendida na simulação de 7 dias: **num mundo
# parado, TODOS os quatro anúncios têm de valer ZERO.** A 1ª versão media
# `contrato` pelo ESTOQUE de contratos (o board se reabastece até 4 por
# continente — supply permanente) e `vendeta` pela POPULAÇÃO (sempre > 1). O
# resultado medido em 28 batidas × 30 seeds: **214 atos, ZERO marchas e ZERO
# caçadas** — a 🚩 Bandeira e a emboscada nasceriam como conteúdo MORTO, cada
# uma por um bônus estrutural de +0,12 a +0,16 que os outros dois goals nunca
# recebiam. É o defeito do "64% fortify" do World Pulse, invertido.
# A correção: o Quadro mede ESCASSEZ/URGÊNCIA, nunca estoque —
#   marchar  → o quanto o MELHOR lugar de fora supera este (0 num mundo plano)
#   cacar    → a desordem AQUI (0 num mundo em paz)
#   contrato → só os contratos perto de APODRECER (a urgência, não a pilha)
#   vendeta  → só os rivais de CAMINHO daqui (0 num continente homogêneo)
# Com isso o mundo parado devolve o volante à ALMA — que é a única coisa que
# o §2.4 diz que tem de mandar.
JH_CONTRACT_URGENT_H = float(os.getenv("JH_CONTRACT_URGENT_H", "12"))
# O anúncio do goal `cacar`: quantas CABEÇAS MARCADAS há neste continente.
# É o "smart object" mais literal da onda — o LUGAR anuncia "aqui há gente que
# vale a pena caçar", e o NPC só compara isso com a própria alma. Sem este
# sinal o `cacar` ficava estruturalmente em último para todo NPC COM CASA
# (medido: `vendeta` = 0.39 + 0.34·agressão vs `cacar` = 0.22 + 0.50·agressão
# ⇒ a vendeta ganha para QUALQUER agressão ≤ 1.06, ou seja, sempre) — e como
# ~75% dos seeds nascem com casa, a emboscada nasceria **sem caçadores**, isto
# é, morta. Com ele, quem caça é quem tem quem caçar: se ninguém no continente
# tem a cabeça a prêmio, ninguém sai à procura (e a Lei §1 fecha sozinha).
JH_OFFER_MARKED = float(os.getenv("JH_OFFER_MARKED", "0.10"))
# Gravidade de casa: um irmão de seita JÁ no destino puxa o próximo. É esta
# força — e só ela — que faz três bandeiras da mesma casa se juntarem num
# continente estrangeiro, ou seja, é ela que CAUSA a 🚩 Bandeira (§1.8 do
# spec-mãe: os NPCs querem coisas → eles se mudam → o mapa muda de cor).
JH_OFFER_HOUSE_GRAVITY = float(os.getenv("JH_OFFER_HOUSE_GRAVITY", "0.05"))
# CONTRAPESO da gravidade — medido numa simulação de 30 dias: só com a
# gravidade, a onda vira um funil (5 casas diferentes empilhadas no MESMO
# continente, Línghé e Mòyǔ esvaziando) porque a ocupação AUMENTA a desordem,
# a desordem aumenta o valor do lugar, e o lugar puxa mais gente — um ratchet
# sem nada empurrando de volta. Um lugar já cheio vale MENOS: no jiānghú
# procura-se onde ainda se pode ser alguém.
JH_OFFER_CROWDING = float(os.getenv("JH_OFFER_CROWDING", "0.015"))

# DRIFT do destino da marcha (a lição do TEC-4, re-medida no recon do MV-8):
# Mòyǔ tem **0 claims e 0 raids em 30d nas 2 DBs**. Escolher o destino SÓ pela
# oportunidade deixaria o continente demoníaco — o que mais pede a Bandeira —
# eternamente inocupável. Nesta fração dos casos o destino sai por sorteio
# ponderado ao INVERSO da população, e o lugar esquecido volta ao mapa.
JH_MARCH_DRIFT = float(os.getenv("JH_MARCH_DRIFT", "0.30"))

# Quanto tempo um caçador (goal `cacar`) fica marcado. É a JANELA em que a
# emboscada pode acontecer naquele continente — e a mesma janela que o chip
# "há quem te procure" mostra no mapa de viagem (UMA verdade).
JH_HUNT_HOURS = float(os.getenv("JH_HUNT_HOURS", "24"))

# A escala do feudo (`loadout["jh_scale"]`) — o DENTE da vendeta. Clamp DURO:
# ±3 degraus × 4% = ±12% de dano de golpe, estritamente strike-only (o lever
# `combat_profile['faction_dmg']`, o mesmo harness-validado do
# NPC_CULTIVATOR_POWER_SCALE). NUNCA toca eff_hp/mitigação — e é DISCLOSED no
# cartão do NPC (Lei §1: um oponente mais forte tem de ser visível ANTES).
JH_SCALE_MAX = int(os.getenv("JH_SCALE_MAX", "3"))
JH_SCALE_STEP = float(os.getenv("JH_SCALE_STEP", "0.04"))

# A BANDEIRA: quantos NPCs da MESMA casa num continente ESTRANGEIRO hasteiam a
# bandeira. Medido contra a população real (main 30 seeds / s2 26 seeds ativos,
# ~3,3 por casa): 4 seria inalcançável em main, 3 é uma convergência que a
# gravidade de casa produz em poucos dias. Exigir continente ESTRANGEIRO mata o
# rótulo estático ("Abyssal ocupa Mòyǔ para sempre").
JH_OCC_MIN_PRESENCE = int(os.getenv("JH_OCC_MIN_PRESENCE", "3"))

# ── A EMBOSCADA (§1.6 do spec-mãe) ─────────────────────────────────────────
# NUNCA um duelo forçado: um ENCONTRO com escolha (⚔️ / 💰 / 🏃). Os canos, na
# ordem do volume real medido: explore (814 lutas/30d) > praça > viagem (1
# viagem/7d — por isso o cano seco é o mais generoso).
JH_AMBUSH_EXPLORE_CHANCE = float(os.getenv("JH_AMBUSH_EXPLORE_CHANCE", "0.06"))
JH_AMBUSH_PLAZA_CHANCE = float(os.getenv("JH_AMBUSH_PLAZA_CHANCE", "0.10"))
JH_AMBUSH_TRAVEL_CHANCE = float(os.getenv("JH_AMBUSH_TRAVEL_CHANCE", "0.20"))
# Pacer PRÓPRIO obrigatório: o explore NÃO tem cooldown (EXPLORE_COOLDOWN_SECONDS=0)
# e uma chance solta viraria um corredor de emboscadas.
JH_AMBUSH_COOLDOWN_H = float(os.getenv("JH_AMBUSH_COOLDOWN_H", "20"))
# 🏃 Quem FOGE volta a ser procurado em METADE do tempo. É o custo REAL do
# ramo do eixo "tempo" — a estrada sozinha não cobra nada quando a emboscada
# chega logo depois de uma viagem (o `last_travel_at` acabou de ser carimbado).
JH_FLEE_RETURN_FACTOR = float(os.getenv("JH_FLEE_RETURN_FACTOR", "0.5"))
# O público — um OU declarado, porque karma sozinho alcança 6 pessoas em prod
# (9 de 239 têm karma ≤ −100; 179 têm karma exatamente 0). O ATO conta tanto
# quanto o estoque: 19 jogadores distintos tiveram evento de karma negativo em
# 30d (`combat_execute` 223, `exploration_fork` 3004).
JH_MARK_KARMA = int(os.getenv("JH_MARK_KARMA", "-100"))
JH_MARK_DAYS = int(os.getenv("JH_MARK_DAYS", "7"))
JH_MARK_REP = int(os.getenv("JH_MARK_REP", "-25"))
# Os eventos de karma que CONTAM como "o ato" (o estoque é o outro ramo).
JH_MARK_EVENTS: tuple[str, ...] = ("combat_execute", "exploration_fork")

# A fonte de duelo da emboscada. ⚠️ `duel_sessions.pve_source` é VARCHAR(24) —
# "jianghu_ambush" = 14 chars. Uma fonte AUSENTE do dispatcher de
# `settle_pve_duel` é recompensa MORTA e silenciosa (`unknown_source`).
JH_AMBUSH_SOURCE = "jianghu_ambush"


# ══════════════════════════════════════════════════════════════════════════
# A ALMA DERIVADA — o que `npc_cultivators` tem que `world_sects` não tem
# ══════════════════════════════════════════════════════════════════════════
# `score_actions` (as 9 casas) lê 5 escalares contínuos 0..1 gravados em colunas
# dedicadas de `world_sects`. `npc_cultivators` NÃO tem alma nenhuma — tem
# `path` (categórico), `karma` (int) e `sect_id` (string). Sem derivar escalares
# primeiro, o `util` dict não tem em que multiplicar. Esta é a ponte.

JH_SOUL_SCALARS: tuple[str, ...] = ("ambition", "honor", "aggression", "loyalty")

# Viés por caminho (Lei §2: o Justo não embosca, o Demoníaco não serve de graça).
_PATH_SOUL: dict[str, dict[str, float]] = {
    "righteous": {"ambition": 0.45, "honor": 0.85, "aggression": 0.35, "loyalty": 0.80},
    "demonic":   {"ambition": 0.85, "honor": 0.15, "aggression": 0.85, "loyalty": 0.30},
    "rogue":     {"ambition": 0.65, "honor": 0.45, "aggression": 0.60, "loyalty": 0.20},
}
_PATH_SOUL_DEFAULT: dict[str, float] = {
    "ambition": 0.50, "honor": 0.50, "aggression": 0.50, "loyalty": 0.50,
}


def _clamp_karma(value: Any) -> int:
    """Karma dentro dos limites canónicos ANTES de virar escalar.

    ⚠️ Obrigatório: a produção tem karma **−1200**, abaixo do `KARMA_MIN` de
    −1000 (dado do recon). Sem o clamp, `honor` sairia NEGATIVO e o argmax
    passaria a escolher por um eixo fora da escala — um bug que só apareceria
    no NPC mais extremo do mundo, que é justamente o mais visível.
    """
    try:
        from core.karma_engine import KARMA_MIN, KARMA_MAX
        lo, hi = int(KARMA_MIN), int(KARMA_MAX)
    except Exception:
        lo, hi = -1000, 1000
    try:
        return max(lo, min(hi, int(value or 0)))
    except (TypeError, ValueError):
        return 0


def soul_from_npc(npc: Any) -> dict[str, float]:
    """Deriva os 4 escalares 0..1 de um NPC a partir de `path`/`karma`/`sect_id`.

    PURA (sem DB, sem relógio) — dry-run-simulável, exatamente como
    `world_pulse_engine.soul_from_row`. O karma modula o eixo `honor` de forma
    contínua (−1000 → 0.0 · 0 → 0.5 · +1000 → 1.0) e puxa `aggression` no
    sentido inverso; pertencer a uma casa sobe `loyalty` (quem não tem casa não
    tem a quem servir — e é por isso que o errante embosca mais).
    """
    base = dict(_PATH_SOUL.get(getattr(npc, "path", None) or "", _PATH_SOUL_DEFAULT))
    karma = _clamp_karma(getattr(npc, "karma", 0))
    k01 = (karma + 1000.0) / 2000.0          # 0.0 .. 1.0

    soul = dict(base)
    # O karma é a evidência mais forte da alma: pesa mais que o rótulo do caminho.
    soul["honor"] = max(0.0, min(1.0, 0.35 * base["honor"] + 0.65 * k01))
    soul["aggression"] = max(0.0, min(1.0, 0.60 * base["aggression"] + 0.40 * (1.0 - k01)))
    soul["loyalty"] = max(0.0, min(1.0, base["loyalty"] + (0.20 if getattr(npc, "sect_id", None) else -0.20)))
    soul["ambition"] = max(0.0, min(1.0, base["ambition"]))
    return soul


# ══════════════════════════════════════════════════════════════════════════
# O MENU DE GOALS — dados puros (utilidade + narração), molde PULSE_ACTIONS
# ══════════════════════════════════════════════════════════════════════════
# Lei §3: QUATRO profundos. Cada um TEM de produzir consequência mecânica
# legível — nada que só escreva texto (isso é flavor caro, não mundo vivo).
#
#   marchar   → escreve `continent_key` numa row seed ⇒ praça, exploração,
#               contagem de viagem, giver de storylet e `pick_encounter_npc`
#               seguem o sujeito DE GRAÇA, sem UM leitor novo. É a jogada que
#               compra mais efeito por menos código de todo o MV-8.
#   cacar     → marca o NPC como caçador de um continente (a emboscada lê isto).
#   contrato  → o NPC leva o contrato que ninguém reclamou (ver nota do §1.3).
#   vendeta   → NPC × NPC: a notícia que NÃO é sobre você (é isto que faz o
#               mundo parecer que existe sem o jogador — Lei §2).
JH_GOALS: dict[str, dict[str, Any]] = {
    "marchar": {
        "icon": "🚩", "importance": 2, "moves": True,
        "text_key": "jh_chron_marchar",
        # Base BAIXA de propósito: marchar sem motivo é andar em círculos. Quem
        # decide é o QUADRO — se nenhum lugar anuncia oportunidade, o NPC fica.
        # (Com base alta, `marchar` levava ~80% de tudo e a vendeta caía para 2%:
        # o mesmo defeito do World Pulse, que é 64% `fortify`.)
        # ⚠️ Recalibrado de 0.18 → 0.24 na parte 2, e o motivo importa: o 0.18
        # foi afinado contra um Quadro em que `contrato` e `vendeta` recebiam
        # bônus PERMANENTE (estoque de contratos / população). Com esse defeito
        # pago, o mesmo 0.18 passou a render **2 marchas em 7 dias** — a 🚩
        # Bandeira e a geografia viva do goal 2 nasceriam praticamente mortas.
        "util": {"base": 0.24, "ambition": 0.40, "loyalty": 0.14},
    },
    "cacar": {
        "icon": "🗡️", "importance": 2, "moves": False,
        "text_key": "jh_chron_cacar",
        "util": {"base": 0.22, "aggression": 0.50},
    },
    "contrato": {
        "icon": "📜", "importance": 1, "moves": False,
        "text_key": "jh_chron_contrato",
        "util": {"base": 0.26, "ambition": 0.26, "honor": 0.24},
    },
    "vendeta": {
        "icon": "🩸", "importance": 2, "moves": False,
        "text_key": "jh_chron_vendeta",
        # Piso deliberadamente competitivo: é a notícia que NÃO é sobre o
        # jogador, e é ela que faz o mundo parecer existir sem ele (Lei §2).
        # Um jiānghú onde ninguém tem contas a acertar com ninguém é um mapa.
        "util": {"base": 0.30, "aggression": 0.34, "loyalty": 0.18},
    },
}

# Ordem estável de iteração ⇒ desempate determinístico no argmax (molde
# PULSE_ACTION_ORDER).
JH_GOAL_ORDER: tuple[str, ...] = ("marchar", "cacar", "contrato", "vendeta")


def goal_icon(goal: str | None) -> str:
    return JH_GOALS.get(goal or "", {}).get("icon", "🏮")


def goal_label_key(goal: str | None) -> str:
    """i18n key do rótulo do goal (disclosure server-resolved — molde
    `world_pulse_engine.action_label_key`)."""
    return f"jh_goal_{goal}" if goal in JH_GOALS else "jh_goal_idle"


# ══════════════════════════════════════════════════════════════════════════
# O PLANNER — PURO (sem DB, sem relógio), dry-run-simulável
# ══════════════════════════════════════════════════════════════════════════

def score_goals(soul: dict[str, float], offers: dict[str, float],
                rng: random.Random) -> dict[str, float]:
    """Utilidade ponderada por goal: Σ(peso × escalar da alma) + base + o valor
    que o QUADRO anuncia para aquele goal + ruído semeado.

    É aqui que os "smart objects" do §2.4 entram: o NPC não sabe nada sobre o
    mundo — ele só compara o que os LUGARES anunciam contra a própria alma.
    Pura: mesmo (soul, offers, estado do rng) ⇒ mesmos scores.
    """
    scores: dict[str, float] = {}
    for key in JH_GOAL_ORDER:
        spec = JH_GOALS[key]
        util = spec["util"]
        val = float(util.get("base", 0.0))
        for scalar in JH_SOUL_SCALARS:
            w = util.get(scalar)
            if w:
                val += float(w) * float(soul.get(scalar, 0.5))
        # O anúncio do lugar, TETADO (ver JH_OFFER_MAX). Ausente ⇒ 0.0: um goal
        # sem oportunidade no mundo perde para um que tem — mas nenhuma
        # oportunidade, por maior que seja, apaga a alma do sujeito.
        val += min(JH_OFFER_MAX, max(0.0, float(offers.get(key, 0.0) or 0.0)))
        val += rng.uniform(0.0, JH_NOISE)
        scores[key] = val
    return scores


def _argmax(scores: dict[str, float], allowed: set[str] | None = None) -> str | None:
    """Maior score (restrito a ``allowed`` se dado). Empate resolvido por
    JH_GOAL_ORDER — determinismo (molde `world_pulse_engine._argmax`)."""
    best: str | None = None
    best_val = float("-inf")
    for key in JH_GOAL_ORDER:
        if key not in scores:
            continue
        if allowed is not None and key not in allowed:
            continue
        if scores[key] > best_val:
            best_val = scores[key]
            best = key
    return best


def pick_goal(soul: dict[str, float], offers: dict[str, float],
              rng: random.Random, *, allowed: set[str] | None = None) -> str | None:
    """O goal deste NPC neste tick. Devolve None quando NENHUM goal é possível
    (o mundo não anuncia nada que ele queira) — e None é uma resposta legítima:
    um mundo em que todo NPC age todo tick é um mundo de autómatos, não um
    jiānghú. Pura."""
    scores = score_goals(soul, offers, rng)
    return _argmax(scores, allowed=allowed)


def tick_epoch(now: datetime, interval_seconds: float) -> int:
    """Molde literal de `world_pulse_engine._tick_epoch`."""
    return int(now.timestamp() // max(1.0, interval_seconds))


def seed_for(world_key: str, npc_id: int, epoch: int, salt: str = "") -> str:
    """A semente do RNG — **com o `world_key` dentro**.

    O World Pulse semeia com `(sect_id, tick_epoch)` e o custo está medido: main
    e s2 produziram contagens IDÊNTICAS de cada ação em 7 dias. Um jiānghú que é
    igual em todo servidor não é um mundo vivo, é um roteiro. Todo RNG deste
    engine passa por aqui.
    """
    return f"jianghu:{world_key}:{npc_id}:{epoch}:{salt}"


def current_world_key() -> str:
    """O mundo atual, lido da ContextVar do router multi-servidor.

    ⚠️ Lê a ContextVar `current_world` DIRETO. Não existe função pública
    `current_world_key` em `database.db` — o resolvedor de lá é o privado
    `_resolve_world_key`, e um import do nome errado cairia no `except` abaixo e
    devolveria "main" PARA SEMPRE, matando em silêncio a semente por mundo (a
    coisa exata que este engine existe para não repetir do World Pulse).
    Fail-safe → 'main'.
    """
    try:
        from database.db import current_world, MAIN_WORLD_KEY
        return str(current_world.get() or MAIN_WORLD_KEY)
    except Exception:
        return "main"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Any) -> datetime | None:
    """Coerção naive→UTC (molde `region_state_engine._aware`). Aceita string
    ISO porque tudo o que este engine persiste vive em JSONB."""
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except (TypeError, ValueError):
            return None
    if not isinstance(dt, datetime):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _set_loadout(npc: Any, **updates: Any) -> None:
    """Escreve chaves `jh_*` no `loadout` de uma row **seed**.

    ⚠️ DOIS motivos para reatribuir um dict NOVO em vez de mutar:
      1. **Não existe `MutableDict` neste projeto** — a coluna é um JSONB puro,
         e mutar in-place NÃO marca o atributo como sujo: o commit passaria em
         silêncio sem gravar nada (o bug mais caro possível, porque o log diria
         que o ato aconteceu).
      2. Todo valor tem de ser JSON-serializável. Um `datetime` aqui estoura o
         INSERT do PRÓXIMO duelo daquele NPC (o `loadout` é copiado inteiro
         para `duel_sessions.fighter_b`), e não neste tick — um erro que só
         apareceria horas depois, longe da causa. Por isso as datas são sempre
         `.isoformat()`.
    """
    lo = dict(getattr(npc, "loadout", None) or {})
    for key, val in updates.items():
        if val is None:
            lo.pop(key, None)
        else:
            lo[key] = val
    npc.loadout = lo


# ══════════════════════════════════════════════════════════════════════════
# P1 — O QUADRO: `board_ctx` (prefetch) + `offers_for` (PURA)
# ══════════════════════════════════════════════════════════════════════════
# Os "smart objects" do §2.4: o NPC não sabe nada sobre o mundo — ele compara
# o que os LUGARES anunciam contra a própria alma. O Quadro é DERIVADO de
# leitores que já existem; ZERO tabela, ZERO row nova.

async def board_ctx(session, *, now: datetime) -> dict[str, Any]:
    """Prefetch ÚNICO do mundo por batimento (molde `_prefetch_world_ctx`).

    ⚠️ **Cada leitor de irmão vai dentro do gate DELE.** `_active_events`
    (MV-2) e `_active_cave` (TEC-4) **não têm gate próprio** — chamá-las com a
    flag do irmão OFF custa query de graça e quebra o contrato "OFF ⇒ zero
    query" que o teste prova com `ExplodingSession`. O molde correto é o
    `storylet_engine._prefetch_world_ctx`, que envolve o leitor em
    `if director_on():`.

    Defensivo em cada bloco: um irmão que falhe deixa o Quadro mais pobre,
    nunca derruba o batimento.
    """
    from core.dungeon_regions import REGIONAL_BONUS_LOOT
    from core.world_sects_engine import WORLD_SECT_KEYS, get_native_continent_for_sect

    ctx: dict[str, Any] = {
        "now": now,
        # A linha PERMANENTE, sem flag nenhuma: todo continente tem material
        # nativo. É a base que impede um Quadro vazio (Lei §1).
        "native": {k: bool(REGIONAL_BONUS_LOOT.get(k)) for k in CONTINENT_KEYS},
        "events": {k: 0 for k in CONTINENT_KEYS},
        "caves": {k: False for k in CONTINENT_KEYS},
        "states": {k: "prospera" for k in CONTINENT_KEYS},
        "bounties": {k: [] for k in CONTINENT_KEYS},
        "urgent": {k: 0 for k in CONTINENT_KEYS},   # contratos perto de apodrecer
        "urgent_ids": {k: [] for k in CONTINENT_KEYS},
        "marked": {k: 0 for k in CONTINENT_KEYS},   # cabeças a prêmio por continente
        "seeds": {k: 0 for k in CONTINENT_KEYS},
        "house_seeds": {},          # (sect_id, continent) -> n
        "path_seeds": {},           # (path, continent) -> n
        "houses": {k: [] for k in CONTINENT_KEYS},
    }

    # Casas SEDIADAS — puro (lore estático), zero query.
    for sect_id in WORLD_SECT_KEYS:
        home = get_native_continent_for_sect(sect_id)
        if home in ctx["houses"]:
            ctx["houses"][home].append(sect_id)

    # MV-2 — eventos do Director. GATE DO IRMÃO (E2).
    try:
        from core.tiandao_engine import director_on
        if director_on():
            from core.tiandao_engine import _active_events
            for ev in await _active_events(session, now):
                if ev.continent_key in ctx["events"]:
                    ctx["events"][ev.continent_key] += 1
    except Exception:
        logger.debug("board_ctx: director events failed", exc_info=True)

    # TEC-4 — Gruta do Legado aberta. GATE DO IRMÃO (E2).
    try:
        from core.legacy_cave_engine import legacy_caves_on
        if legacy_caves_on():
            from core.legacy_cave_engine import _active_cave
            cave = await _active_cave(session, now)
            if cave is not None and cave.continent_key in ctx["caves"]:
                ctx["caves"][cave.continent_key] = True
    except Exception:
        logger.debug("board_ctx: legacy cave failed", exc_info=True)

    # MV-3 — estado regional. SELECT **direto** na tabela, nunca pelos helpers
    # do MV-3: eles curto-circuitam com a flag DELES e devolveriam 'prospera'
    # para tudo, cegando o Quadro num mundo que TEM estados (precedente:
    # profession_engine lê region_states.payload direto pelo mesmo motivo).
    # Com `estados_regionais` OFF a tabela simplesmente está vazia.
    try:
        from database.models import RegionState
        rows = (await session.execute(select(RegionState))).scalars().all()
        for row in rows:
            if row.continent_key in ctx["states"]:
                ctx["states"][row.continent_key] = str(row.state or "prospera")
    except Exception:
        logger.debug("board_ctx: region states failed", exc_info=True)

    # Contratos ABERTOS por continente. ⚠️ `posted_by IS NOT NULL` fica de
    # FORA: um contrato pago por um jogador com pedras NÃO-REEMBOLSÁVEIS não
    # pode ser apagado pelo mundo (Lei §4) — o próprio `claim_bounty` protege
    # esse depósito com um guard.
    try:
        from database.models import Bounty
        rows = (await session.execute(
            select(Bounty).where(
                Bounty.status == "open",
                Bounty.posted_by.is_(None),
                (Bounty.expires_at.is_(None)) | (Bounty.expires_at > now),
            )
        )).scalars().all()
        urgent_cut = now + timedelta(hours=JH_CONTRACT_URGENT_H)
        for row in rows:
            if row.continent_key in ctx["bounties"]:
                ctx["bounties"][row.continent_key].append(int(row.id))
                exp = _aware(row.expires_at)
                # A URGÊNCIA é o que o Quadro anuncia — não a pilha. "O NPC
                # leva o contrato que VOCÊ deixou apodrecer" (spec-mãe §1.4).
                if exp is not None and exp <= urgent_cut:
                    ctx["urgent"][row.continent_key] += 1
                    ctx["urgent_ids"][row.continent_key].append(int(row.id))
    except Exception:
        logger.debug("board_ctx: bounties failed", exc_info=True)

    # As CABEÇAS MARCADAS por continente — o anúncio do goal `cacar`. Mesmo OU
    # declarado da emboscada (o estoque de karma OU o ATO recente), porque um
    # gate só-karma alcança 9 pessoas de 239 em prod. Duas queries curtas em vez
    # de um JOIN: o conjunto de "atos recentes" é minúsculo (19 jogadores em 30d).
    try:
        from database.models import KarmaLog, Player
        from sqlalchemy import func as _f
        rows = (await session.execute(
            select(Player.current_continent, _f.count())
            .where(Player.karma <= JH_MARK_KARMA)
            .group_by(Player.current_continent)
        )).all()
        marked_ids: set[int] = set()
        for cont, n in rows:
            if cont in ctx["marked"]:
                ctx["marked"][cont] += int(n)
        recent = (await session.execute(
            select(KarmaLog.player_id).where(
                KarmaLog.event_type.in_(JH_MARK_EVENTS),
                KarmaLog.delta < 0,
                KarmaLog.created_at >= now - timedelta(days=JH_MARK_DAYS),
            ).distinct()
        )).scalars().all()
        marked_ids = {int(i) for i in recent if i}
        if marked_ids:
            rows2 = (await session.execute(
                select(Player.current_continent, _f.count())
                .where(Player.telegram_id.in_(list(marked_ids)),
                       Player.karma > JH_MARK_KARMA)   # os do 1º ramo já contaram
                .group_by(Player.current_continent)
            )).all()
            for cont, n in rows2:
                if cont in ctx["marked"]:
                    ctx["marked"][cont] += int(n)
    except Exception:
        logger.debug("board_ctx: marked heads failed", exc_info=True)

    # População do ELENCO (só seeds — `source_hash IS NULL`), por continente e
    # por (casa, continente). Serve três coisas de uma query: a oportunidade de
    # vendeta, a gravidade de casa da marcha e a presença da 🚩 Bandeira.
    try:
        from sqlalchemy import func
        rows = (await session.execute(
            select(NpcCultivator.continent_key, NpcCultivator.sect_id,
                   NpcCultivator.path, func.count())
            .where(
                NpcCultivator.status == "active",
                NpcCultivator.source_hash.is_(None),
            )
            .group_by(NpcCultivator.continent_key, NpcCultivator.sect_id,
                      NpcCultivator.path)
        )).all()
        for cont, sect_id, path, n in rows:
            if cont in ctx["seeds"]:
                ctx["seeds"][cont] += int(n)
                if sect_id:
                    key_h = (str(sect_id), str(cont))
                    ctx["house_seeds"][key_h] = int(ctx["house_seeds"].get(key_h, 0)) + int(n)
                if path:
                    key_p = (str(path), str(cont))
                    ctx["path_seeds"][key_p] = int(ctx["path_seeds"].get(key_p, 0)) + int(n)
    except Exception:
        logger.debug("board_ctx: seed population failed", exc_info=True)

    return ctx


def _place_value(ctx: dict[str, Any], continent: str) -> float:
    """Quanto UM lugar vale para quem procura oportunidade. PURA.

    ⚠️ `ocupada` NÃO conta como desordem atraente. Contava na 1ª versão, e a
    simulação de 30 dias mostrou o ratchet: ocupar aumentava a desordem, a
    desordem aumentava o valor do lugar, e o lugar puxava mais gente — cinco
    casas empilhadas num único continente enquanto Línghé e Mòyǔ esvaziavam.
    Uma bandeira estrangeira não é uma oportunidade: é a reivindicação de
    OUTRA casa. (Para quem já está lá, a ocupação continua a contar como
    desordem no goal `cacar` — isso é local, não é atração de destino.)
    """
    val = JH_OFFER_NATIVE if ctx["native"].get(continent) else 0.0
    val += JH_OFFER_EVENT * min(2, int(ctx["events"].get(continent, 0) or 0))
    if ctx["caves"].get(continent):
        val += JH_OFFER_CAVE
    state = ctx["states"].get(continent) or "prospera"
    if state in ("tensa", "sitiada"):
        val += JH_OFFER_UNREST
    elif state == "festival":
        val += JH_OFFER_FESTIVAL
    return val


def _destination_value(ctx: dict[str, Any], cand: str, sect_id: str | None) -> float:
    """O quanto UM destino vale para quem pensa em marchar. PURA.

    UMA verdade partilhada por `offers_for` (que decide SE vale a pena marchar)
    e por `march_target` (que decide PARA ONDE): se as duas divergissem, o NPC
    poderia querer partir por causa de um lugar e acabar noutro — e o anúncio
    da Crônica mentiria sobre o próprio motivo.
    """
    val = _place_value(ctx, cand)
    if sect_id:
        val += JH_OFFER_HOUSE_GRAVITY * min(
            2, int(ctx["house_seeds"].get((sect_id, cand), 0) or 0))
    val -= JH_OFFER_CROWDING * min(5, int(ctx["seeds"].get(cand, 0) or 0))
    return val


# Quem tem contas a acertar com quem (Lei §2 — o Justo e o Demoníaco cruzam
# lâminas; dois errantes no mesmo bar não têm dívida nenhuma).
_PATH_FOES: dict[str, tuple[str, ...]] = {
    "righteous": ("demonic",),
    "demonic": ("righteous",),
    "rogue": ("demonic",),
}


def offers_for(ctx: dict[str, Any], continent: str, *, sect_id: str | None = None,
               npc_id: int | None = None, path: str | None = None) -> dict[str, float]:
    """O que o mundo ANUNCIA para um NPC que está em ``continent``. **PURA** —
    consome só o `ctx` prefetchado, zero I/O; alimenta o `score_goals` que já
    existe.

    ⚠️ **Num mundo parado os QUATRO valores são 0.0**, por construção (ver a
    "lei de ferro do Quadro" nos knobs): o anúncio existe para o mundo
    DESEMPATAR, e um goal com supply permanente rouba o volante da alma.
    """
    # ⚠️ Os dois lados da comparação usam a MESMA régua (`_destination_value`),
    # gravidade e lotação incluídas. Medir "aqui" com uma régua e "lá" com
    # outra deu, na simulação, uma penalidade fixa de até −0,15 para toda
    # marcha ⇒ **zero marchas em 7 dias**. É a mesma classe de defeito do
    # `display=roll`: comparar dois números que não são a mesma conta.
    local = _destination_value(ctx, continent, sect_id)
    best_away = max((_destination_value(ctx, other, sect_id)
                     for other in CONTINENT_KEYS if other != continent),
                    default=0.0)

    state = ctx["states"].get(continent) or "prospera"
    unrest = JH_OFFER_UNREST if state in ("tensa", "sitiada", "ocupada") else 0.0
    unrest += JH_OFFER_EVENT * min(1, int(ctx["events"].get(continent, 0) or 0))
    # Ninguém sai à caça de ninguém: caça-se QUEM tem a cabeça a prêmio AQUI.
    unrest += JH_OFFER_MARKED * min(2, int(ctx.get("marked", {}).get(continent, 0) or 0))

    # A vendeta precisa de um DESAFETO — não de um vizinho qualquer. Num
    # continente homogêneo (Mòyǔ é todo demoníaco) ninguém tem contas a acertar,
    # e o anúncio vale 0: quem decide ali é a alma.
    foes = 0
    if path:
        for foe_path in _PATH_FOES.get(str(path), ()):
            foes += int(ctx.get("path_seeds", {}).get((foe_path, continent), 0) or 0)

    return {
        # Marchar só vale a DIFERENÇA: se aqui já é o melhor lugar do mundo,
        # marchar é andar em círculos (e o `base` baixo do goal cuida do resto).
        "marchar": max(0.0, best_away - local),
        "cacar": unrest,
        "contrato": JH_OFFER_BOUNTY * min(2, int(ctx.get("urgent", {}).get(continent, 0) or 0)),
        "vendeta": JH_OFFER_VENDETA * min(2, foes),
    }


def march_target(ctx: dict[str, Any], continent: str, sect_id: str | None,
                 rng: random.Random) -> str | None:
    """Para ONDE ele marcha. PURA (o rng é semeado por `(mundo, npc, epoch)`).

    `JH_MARCH_DRIFT` dos casos sai por sorteio ponderado ao INVERSO da
    população — sem isso o destino seria sempre o continente mais rico e Mòyǔ
    (8 NPCs, 0 claims/0 raids em 30d) nunca receberia ninguém. É literalmente a
    mesma correção que o TEC-4 teve de fazer no drift das casas.
    """
    others = [c for c in CONTINENT_KEYS if c != continent]
    if not others:
        return None
    if rng.random() < JH_MARCH_DRIFT:
        # Peso = 1 / (1 + população de seeds). O esquecido pesa mais.
        weights = [1.0 / (1.0 + float(ctx["seeds"].get(c, 0) or 0)) for c in others]
        total = sum(weights) or 1.0
        roll = rng.random() * total
        acc = 0.0
        for cand, w in zip(others, weights):
            acc += w
            if roll <= acc:
                return cand
        return others[-1]
    # Oportunidade: o melhor destino — a MESMA conta que `offers_for` usou para
    # decidir que valia a pena partir (`_destination_value`).
    best, best_val = None, float("-inf")
    for cand in others:
        val = _destination_value(ctx, cand, sect_id)
        if val > best_val:
            best, best_val = cand, val
    return best


# ══════════════════════════════════════════════════════════════════════════
# P3 — OS QUATRO ATOS (cada um resolve DENTRO do próprio tick)
# ══════════════════════════════════════════════════════════════════════════
# Não existe "plano pendente": existe um ATO e a sua consequência. Por isso
# não há tabela de planos, nem sweep de planos órfãos, nem plano eternamente
# 'active'. O que sobrevive ao tick mora onde já há casa.

async def _act_marchar(session, npc: Any, ctx: dict[str, Any], rng: random.Random,
                       now: datetime) -> dict[str, Any] | None:
    """🚩 Ele MUDA DE CONTINENTE de verdade.

    É a jogada que compra mais efeito por menos código de todo o MV-8: a
    praça, a exploração, a contagem de viagem, o giver de storylet e o
    `pick_encounter_npc` leem `continent_key` e seguem o sujeito **sem UM
    leitor novo**. E é ela que causa a 🚩 Bandeira.
    """
    origin = str(npc.continent_key or "")
    target = march_target(ctx, origin, npc.sect_id, rng)
    if not target or target == origin or not is_valid_continent(target):
        return None
    npc.continent_key = target
    # O Quadro em memória acompanha, senão dois marchadores do mesmo tick
    # decidiriam sobre uma foto velha do mundo.
    if origin in ctx["seeds"]:
        ctx["seeds"][origin] = max(0, ctx["seeds"][origin] - 1)
    if target in ctx["seeds"]:
        ctx["seeds"][target] += 1
    if npc.sect_id:
        key_o, key_t = (str(npc.sect_id), origin), (str(npc.sect_id), target)
        ctx["house_seeds"][key_o] = max(0, int(ctx["house_seeds"].get(key_o, 0)) - 1)
        ctx["house_seeds"][key_t] = int(ctx["house_seeds"].get(key_t, 0)) + 1
    return {
        "target": target,
        # ⚠️ A linha é "{npc} deixou {continent} e marcha rumo a {to_continent}":
        # o `continent_key` da row é a ORIGEM (é de lá que a notícia parte) e o
        # destino viaja em `params["to_continent_key"]`, resolvido pelo ramo
        # novo de `_chronicle_localized_names`. Sem esse ramo o jogador leria
        # `{to_continent}` cru — `t()` engole o KeyError e devolve o template.
        "chron_continent": origin,
        "chron_params": {"npc": npc.name, "to_continent_key": target},
    }


async def _act_cacar(session, npc: Any, ctx: dict[str, Any], rng: random.Random,
                     now: datetime) -> dict[str, Any] | None:
    """🗡️ Ele passa a CAÇAR neste continente — a emboscada lê exatamente isto.

    UMA verdade: o mesmo `jh_hunt` alimenta o encontro (explore/praça/viagem) e
    o chip "há quem te procure em X" do mapa de viagem. O anúncio é
    deliberadamente vago — ele pergunta por *um nome*, nunca pelo SEU nome: no
    jiānghú a caçada é rumor público, o alvo é privado.
    """
    cont = str(npc.continent_key or "")
    if not is_valid_continent(cont):
        return None
    _set_loadout(npc, jh_hunt={
        "continent": cont,
        "until": (now + timedelta(hours=JH_HUNT_HOURS)).isoformat(),
    })
    return {"target": cont, "chron_continent": cont, "chron_params": {"npc": npc.name}}


async def _act_contrato(session, npc: Any, ctx: dict[str, Any], rng: random.Random,
                        now: datetime) -> dict[str, Any] | None:
    """📜 Ele chega PRIMEIRO ao contrato que você deixou apodrecer.

    ⚠️ O NPC **não pode reclamar** um bounty: `bounties.claimed_by` é
    `BigInteger FK → players.telegram_id`. Gravar um `npc_cultivators.id` ali
    ou viola a FK ou — se o id colidir — **atribui o contrato a um JOGADOR
    REAL**, que passaria a aparecer como caçador na UI. E `claim_bounty` exige
    cinco condições de duelo que um NPC não tem. Sem migration o caminho
    honesto é o vocabulário que a tabela já fala: `status = 'expired'`.
    O autor fica no `jh_last` do NPC e na linha da Crônica.
    """
    from database.models import Bounty
    # ⚠️ Só os que estão a APODRECER. O Quadro anuncia a URGÊNCIA e o ato tem
    # de morder exatamente onde o anúncio prometeu: sorteando do estoque
    # inteiro, o NPC podia expirar um contrato com 40h de prazo que o jogador
    # estava a caçar naquele minuto — ele venceria o alvo e leria "expirado"
    # com o relógio da UI ainda a marcar 40h.
    pool = list(ctx.get("urgent_ids", {}).get(str(npc.continent_key or "")) or [])
    if not pool:
        return None
    bounty_id = pool[rng.randrange(len(pool))]
    row = (await session.execute(
        select(Bounty).where(Bounty.id == int(bounty_id))
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    # Revalidação sob o lock: outro jogador pode ter reclamado entre o prefetch
    # e agora. E `posted_by` é re-checado AQUI também — cinto e suspensórios
    # sobre a Lei §4 (pedras não-reembolsáveis de um jogador).
    if row is None or row.status != "open" or row.posted_by is not None:
        return None
    row.status = "expired"
    cont = str(npc.continent_key)
    ctx["urgent_ids"][cont] = [b for b in pool if int(b) != int(bounty_id)]
    ctx["urgent"][cont] = max(0, int(ctx["urgent"].get(cont, 0)) - 1)
    ctx["bounties"][cont] = [b for b in (ctx["bounties"].get(cont) or [])
                             if int(b) != int(bounty_id)]
    return {
        "target": str(npc.continent_key or ""),
        "chron_continent": str(npc.continent_key or ""),
        "chron_params": {"npc": npc.name},
        "bounty_id": int(bounty_id),
    }


async def _act_vendeta(session, npc: Any, ctx: dict[str, Any], rng: random.Random,
                       now: datetime) -> dict[str, Any] | None:
    """🩸 NPC × NPC — a notícia que **não é sobre você**.

    É este goal que faz o mundo parecer existir sem o jogador (Lei §2): um
    jiānghú onde ninguém tem contas a acertar com ninguém é um mapa. O DENTE é
    a escala do feudo: quem vence fica mensuravelmente mais perigoso da
    próxima vez que VOCÊ o encontrar — e o cartão dele diz isso ANTES.
    """
    cont = str(npc.continent_key or "")
    rows = (await session.execute(
        select(NpcCultivator).where(
            NpcCultivator.status == "active",
            NpcCultivator.source_hash.is_(None),
            NpcCultivator.continent_key == cont,
            NpcCultivator.id != int(npc.id),
        ).order_by(NpcCultivator.id).limit(12)
    )).scalars().all()
    if not rows:
        return None
    # ── Fase A4 do Motor de Mundo Vivo (pivot 2026-08-11) ──────────────────
    # A VENDETA GANHA DESTINATÁRIO. Até aqui o alvo era um vizinho AO CALHAS:
    # o mundo tinha brigas, mas nenhuma delas era CONTINUAÇÃO de coisa nenhuma,
    # e por isso as histórias morriam no primeiro salto. Agora quem perdeu (ou
    # foi humilhado por um jogador) lembra-se de quem lhe fez mal, e é lá que
    # volta — se a pessoa ainda estiver ao alcance.
    # Fail-open: memória inválida/ausente cai no acaso de sempre.
    other = None
    _wronged = (npc.loadout or {}).get("jh_wronged") if isinstance(npc.loadout, dict) else None
    _w_id = None
    try:
        _w_id = int((_wronged or {}).get("id")) if isinstance(_wronged, dict) else None
    except Exception:
        _w_id = None
    if _w_id is not None:
        other = next((r for r in rows if int(r.id) == _w_id), None)
    if other is None:
        other = rows[rng.randrange(len(rows))]
    # Quem ganha: o mais forte, com o acaso a dar uma chance honesta ao menor.
    mine = float(npc.power or 0) + rng.uniform(0.0, 1.0) * max(1.0, float(npc.power or 1)) * 0.35
    theirs = float(other.power or 0) + rng.uniform(0.0, 1.0) * max(1.0, float(other.power or 1)) * 0.35
    winner, loser = (npc, other) if mine >= theirs else (other, npc)
    # ⚠️ Travar SEMPRE por id ASCENDENTE, nunca na ordem (vencedor, perdedor):
    # dois duelos do mesmo tick que compartilhem um dos dois rostos travariam
    # (A,B) e (B,A) e se abraçariam. É a mesma regra do P2P trade (locks
    # ascendentes anti AB-BA); aqui a ordem do resultado é aleatória por
    # construção, então o risco seria real e intermitente.
    steps = {int(winner.id): 1, int(loser.id): -1}
    for npc_id in sorted(steps):
        locked = (await session.execute(
            select(NpcCultivator).where(NpcCultivator.id == npc_id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if locked is None:
            continue
        cur = int((locked.loadout or {}).get("jh_scale", 0) or 0)
        _kw: dict[str, Any] = {"jh_scale": max(-JH_SCALE_MAX,
                                               min(JH_SCALE_MAX, cur + steps[npc_id]))}
        # Fase A4 — o PERDEDOR guarda quem lhe fez isto; o vencedor esquece a
        # dívida que acabou de cobrar. É o que faz um feudo ter capítulos em vez
        # de ser um dado rolado outra vez.
        # ⚠️ JSON-safe sempre: este dict é copiado para `duel_sessions.fighter_b`,
        # e um datetime cru rebentaria a serialização (contrato do `_set_loadout`).
        if steps[npc_id] < 0:
            _kw["jh_wronged"] = {"id": int(winner.id), "name": str(winner.name or ""),
                                 "at": now.isoformat()}
        else:
            _kw["jh_wronged"] = None
        _set_loadout(locked, **_kw)
    return {
        "target": other.name,
        "chron_continent": cont,
        # {npc} e {other} são NOMES PRÓPRIOS: language-neutral, viajam em
        # `params` (precedente `params={"rival": npc.name}` do MV-6).
        "chron_params": {"npc": winner.name, "other": loser.name},
        "won": bool(winner is npc),
    }


_ACTS = {
    "marchar": _act_marchar,
    "cacar": _act_cacar,
    "contrato": _act_contrato,
    "vendeta": _act_vendeta,
}


# ══════════════════════════════════════════════════════════════════════════
# P2 — O BATIMENTO: `jianghu_pulse` (passo 6 do World Pulse de 6h)
# ══════════════════════════════════════════════════════════════════════════

async def _jianghu_sweep(session, now: datetime) -> int:
    """**Kill-switch honesto** — o fecho de todo plano cujo autor evaporou.

    `_whisper_npc_ascension` marca `status='ascended'` em QUALQUER NPC ativo de
    realm ≥ 4 a cada 6h — inclusive um que acabou de anunciar uma marcha (em
    prod, **18 dos 44 seeds do s2 já ascenderam: 41% do elenco**). Um plano
    anunciado cujo autor some sem uma linha de fecho é exatamente o void
    silencioso que a Lei §1 proíbe. Molde: o kill-switch do `rival_pulse`.
    """
    closed = 0
    rows = (await session.execute(
        select(NpcCultivator).where(
            NpcCultivator.source_hash.is_(None),
            NpcCultivator.status != "active",
        ).limit(200)
    )).scalars().all()
    for npc in rows:
        lo = npc.loadout or {}
        if not lo.get("jh_last") and not lo.get("jh_hunt"):
            continue
        try:
            async with session.begin_nested():
                locked = (await session.execute(
                    select(NpcCultivator).where(NpcCultivator.id == int(npc.id))
                    .with_for_update().execution_options(populate_existing=True)
                )).scalar_one_or_none()
                if locked is None or locked.status == "active":
                    continue
                had_plan = bool((locked.loadout or {}).get("jh_last"))
                _set_loadout(locked, jh_last=None, jh_hunt=None)
                if had_plan:
                    from core.world_pulse_engine import emit_chronicle
                    await emit_chronicle(
                        session, event_type="jh_sumiu", text_key="jh_chron_sumiu",
                        params={"npc": locked.name},
                        continent_key=locked.continent_key, importance=1, now=now,
                    )
                    closed += 1
        except Exception:
            logger.exception("jianghu sweep: fecho falhou (npc=%s)", getattr(npc, "id", None))
    return closed


async def _actor_pool(session, continent: str, exclude: set[int]) -> list[Any]:
    """Os candidatos de UM continente. O elenco é **só `origin='seed'`**
    (`source_hash IS NULL`): as rows `echo` têm name/realm/continent/karma/
    **loadout**/status RE-ASSINADOS a cada 6h por `snapshot_player_to_npc`, e
    o `_assign` casa por `source_hash` — escrever um plano num echo é escrever
    na areia, e de forma não-determinística (o snapshot só varre os 20
    jogadores mais recentes)."""
    rows = (await session.execute(
        select(NpcCultivator).where(
            NpcCultivator.status == "active",
            NpcCultivator.source_hash.is_(None),
            NpcCultivator.continent_key == continent,
        ).order_by(NpcCultivator.power.desc())
        .limit(max(9, JH_ACTORS_PER_CONTINENT * 3))
    )).scalars().all()
    return [r for r in rows if int(r.id) not in exclude]


async def jianghu_pulse(session) -> dict[str, Any] | None:
    """O passo 6 do World Pulse de 6h. Assinatura **só `session`** — os irmãos
    (`sync_region_states`, `generate_market_reports`) também não aceitam `now`,
    e divergir aqui seria a única exceção do passo.

    Sequência: sweep de fecho → Quadro → K atores por continente (ordem semeada
    POR MUNDO) → cada ator no próprio SAVEPOINT → anúncio dentro do orçamento.
    Flag OFF → `None` **sem UMA query**. Commit próprio; qualquer falha é
    engolida e logada (o batimento nunca cai).
    """
    if not jianghu_on():
        return None
    now = _utcnow()
    world = current_world_key()
    # `world_pulse_engine` semeia com `(sect_id, tick_epoch)` SEM o mundo, e o
    # custo está medido: main e s2 contaram a MESMA história por 7 dias. Toda
    # semente deste engine carrega o `world_key`.
    epoch = tick_epoch(now, 6 * 3600.0)
    t0 = _time.monotonic()
    summary: dict[str, Any] = {
        "epoch": epoch, "world": world, "acted": 0, "announced": 0,
        "skipped": 0, "closed": 0, "goals": {}, "ms": 0,
    }
    try:
        summary["closed"] = await _jianghu_sweep(session, now)

        ctx = await board_ctx(session, now=now)

        # Exclusões: quem é ALVO de um contrato aberto e quem é rival de
        # alguém — o mundo não deve disputar o mesmo rosto consigo mesmo, e a
        # rivalidade do MV-6 é pessoal (o board é público).
        exclude: set[int] = set()
        try:
            from core.bounty_engine import open_npc_ids
            exclude |= await open_npc_ids(session)
        except Exception:
            logger.debug("jianghu_pulse: bounty exclusion failed", exc_info=True)
        try:
            from core.reputation_engine import rival_npc_ids
            exclude |= await rival_npc_ids(session)
        except Exception:
            logger.debug("jianghu_pulse: rival exclusion failed", exc_info=True)

        # Ordem semeada dos CONTINENTES: sem ela, Línghé (49 dos 94 ativos)
        # levaria os dois anúncios de toda batida e o resto do mundo seria mudo
        # para sempre — o mesmo defeito que obrigou o teto a ser POR continente.
        order = list(CONTINENT_KEYS)
        random.Random(f"jianghu_order:{world}:{epoch}").shuffle(order)
        announce_budget = JH_ANNOUNCE_PER_TICK

        for continent in order:
            try:
                pool = await _actor_pool(session, continent, exclude)
            except Exception:
                logger.exception("jianghu_pulse: pool falhou (continente=%s)", continent)
                continue
            random.Random(f"jianghu_actors:{world}:{continent}:{epoch}").shuffle(pool)
            # ⚠️ Contar ATOS, não candidatos. Fatiar `pool[:K]` ANTES do teste
            # de descanso fazia um NPC em cooldown QUEIMAR uma vaga: com 18h de
            # descanso sobre um pulse de 6h cada ator fica bloqueado 3 batidas,
            # e a rotação semeada punha os cansados à frente — Mòyǔ (8 seeds)
            # produzia ZERO atos numa batida com três descansados nas posições
            # 4-8 do MESMO pool. É o continente que mais precisa de marchas.
            acted_here = 0
            for npc in pool:
                if acted_here >= JH_ACTORS_PER_CONTINENT:
                    break
                await asyncio.sleep(0)   # o loop das 9 casas não cede; este cede.
                try:
                    async with session.begin_nested():
                        locked = (await session.execute(
                            select(NpcCultivator).where(NpcCultivator.id == int(npc.id))
                            .with_for_update().execution_options(populate_existing=True)
                        )).scalar_one_or_none()
                        if locked is None or locked.status != "active":
                            continue
                        last = (locked.loadout or {}).get("jh_last") or {}
                        # (a) Dedupe do próprio tick. A `world_chronicle` **não
                        # tem dedupe nenhum** (índice único só em `ts`, sem
                        # `ref_id`) e o job é `coalesce=True` +
                        # `misfire_grace_time=3600` ⇒ um re-fire duplicaria todo
                        # anúncio. O epoch do último ato é o guard (mesmo
                        # idioma do `last_pulse_at` das 9 casas).
                        if int(last.get("epoch", -1)) == epoch:
                            summary["skipped"] += 1
                            continue
                        # (b) Descanso — espalha o palco em vez de um só repetir.
                        at = _aware(last.get("at"))
                        if at is not None and (now - at) < timedelta(hours=JH_ACTOR_COOLDOWN_HOURS):
                            summary["skipped"] += 1
                            continue

                        cont = str(locked.continent_key or continent)
                        offers = offers_for(ctx, cont, sect_id=locked.sect_id,
                                            npc_id=int(locked.id), path=locked.path)
                        allowed = {"cacar"}
                        if len(CONTINENT_KEYS) > 1:
                            allowed.add("marchar")
                        # O gate segue o mesmo pool do ATO (só os urgentes):
                        # permitir o goal sobre o estoque inteiro faria o NPC
                        # escolher `contrato` e o ato devolver None — vaga
                        # gasta e nenhuma consequência.
                        if ctx.get("urgent_ids", {}).get(cont):
                            allowed.add("contrato")
                        if int(ctx["seeds"].get(cont, 0) or 0) > 1:
                            allowed.add("vendeta")
                        rng = random.Random(seed_for(world, int(locked.id), epoch))
                        goal = pick_goal(soul_from_npc(locked), offers, rng, allowed=allowed)
                        if goal is None:
                            continue

                        out = await _ACTS[goal](session, locked, ctx, rng, now)
                        if out is None:
                            # O goal não se materializou (o alvo sumiu sob o
                            # lock). Silêncio é a resposta certa: nunca uma
                            # linha de Crônica sobre um ato que não aconteceu.
                            continue

                        _set_loadout(locked, jh_last={
                            "goal": goal,
                            "epoch": int(epoch),
                            "at": now.isoformat(),        # NUNCA um datetime (JSONB)
                            "target": out.get("target"),
                        })

                        # (c) O anúncio, dentro do orçamento. A maioria dos atos
                        # muda estado em SILÊNCIO e só é revelada a quem está
                        # lá: a batida da Chronicle já escreve 9 linhas e a
                        # superfície mais vista mostra 4.
                        if announce_budget > 0:
                            spec = JH_GOALS[goal]
                            from core.world_pulse_engine import emit_chronicle
                            crow = await emit_chronicle(
                                session,
                                event_type=f"jh_{goal}",
                                text_key=str(spec["text_key"]),
                                params=dict(out.get("chron_params") or {}),
                                continent_key=out.get("chron_continent"),
                                sect_id=locked.sect_id,
                                importance=int(spec["importance"]),
                                now=now,
                            )
                            if crow is not None:
                                announce_budget -= 1
                                summary["announced"] += 1

                        acted_here += 1
                        summary["acted"] += 1
                        summary["goals"][goal] = summary["goals"].get(goal, 0) + 1
                except Exception:
                    logger.exception("jianghu_pulse: ator falhou (npc=%s)",
                                     getattr(npc, "id", None))
                    continue

        await session.commit()
        summary["ms"] = int((_time.monotonic() - t0) * 1000)
        return summary
    except Exception:
        logger.exception("jianghu_pulse failed")
        try:
            await session.rollback()
        except Exception:
            pass
        return None


# ══════════════════════════════════════════════════════════════════════════
# P4 — A 🚩 BANDEIRA: a presença é DERIVADA, nunca armazenada
# ══════════════════════════════════════════════════════════════════════════

async def occupation_map(session) -> dict[str, dict[str, Any]]:
    """`{continente: {sect_id, presence}}` — quem hasteia bandeira onde.

    **Derivada, nunca armazenada**: uma coluna de "ocupante" seria uma segunda
    verdade que divergiria da população real na primeira marcha. É o gêmeo do
    `count_sect_npc_population`, com `GROUP BY (sect_id, continent_key)`.

    Só conta o ELENCO (`source_hash IS NULL`) — os echoes são espelhos de
    jogadores reescritos a cada 6h, e deixá-los contar faria a bandeira subir e
    descer por uma causa que o jiānghú não controla: a onda tem de causar a
    própria ocupação.

    Só conta continente **ESTRANGEIRO** (≠ sede da casa) — sem isso
    "abyssal_depths ocupa Mòyǔ" seria um rótulo estático eterno, não um mundo
    vivo. Flag OFF → `{}` **sem UMA query**.
    """
    if not jianghu_on():
        return {}
    try:
        from sqlalchemy import func
        from core.world_sects_engine import get_native_continent_for_sect
        rows = (await session.execute(
            select(NpcCultivator.sect_id, NpcCultivator.continent_key, func.count())
            .where(
                NpcCultivator.status == "active",
                NpcCultivator.source_hash.is_(None),
                NpcCultivator.sect_id.is_not(None),
            )
            .group_by(NpcCultivator.sect_id, NpcCultivator.continent_key)
        )).all()
        best: dict[str, dict[str, Any]] = {}
        for sect_id, continent, n in rows:
            if not sect_id or continent not in CONTINENT_KEYS:
                continue
            if get_native_continent_for_sect(str(sect_id)) == continent:
                continue  # em casa não se ocupa nada
            count = int(n or 0)
            if count < JH_OCC_MIN_PRESENCE:
                continue
            cur = best.get(continent)
            # Desempate DETERMINÍSTICO — sem ele a bandeira trocaria de dono a
            # cada pulse só pela ordem em que o Postgres devolveu as linhas.
            # Ordena por (−presença, sect_id): mais gente primeiro; no empate,
            # o sect_id alfabeticamente menor.
            if cur is None or (-count, str(sect_id)) < (-int(cur["presence"]), str(cur["sect_id"])):
                best[continent] = {"sect_id": str(sect_id), "presence": count}
        return best
    except Exception:
        logger.exception("occupation_map failed")
        return {}


# ══════════════════════════════════════════════════════════════════════════
# P5 — A EMBOSCADA: um ENCONTRO COM ESCOLHA, nunca um duelo forçado
# ══════════════════════════════════════════════════════════════════════════
# §0.9 do recon, com os números reais: perder um PvE drena 50% do dano tomado,
# derrota total = −50% do HP bruto, DUAS derrotas = 0 HP — e a 0 HP fecham SEIS
# portas, com ~16,7h de regen. O próprio código já decidiu esta questão: a
# única auto-entrada em duelo do jogo recusa com a Lei citada no comentário
# (`arena_engine.py`: "Lei §1: no forced losses").

async def _ambush_marked(session, player: Any, continent: str, now: datetime) -> str | None:
    """Por que ELE viria atrás de você? Devolve o motivo (a key de disclosure)
    ou None. Um OU declarado: karma sozinho alcançaria 6 pessoas em prod."""
    try:
        if int(getattr(player, "karma", 0) or 0) <= JH_MARK_KARMA:
            return "karma"
    except (TypeError, ValueError):
        pass
    # O ATO, não o estoque — 75% dos jogadores têm karma exatamente 0, mas 19
    # jogadores distintos tiveram evento de karma negativo em 30d.
    try:
        from database.models import KarmaLog
        cut = now - timedelta(days=JH_MARK_DAYS)
        row = (await session.execute(
            select(KarmaLog.id).where(
                KarmaLog.player_id == int(player.telegram_id),
                KarmaLog.event_type.in_(JH_MARK_EVENTS),
                KarmaLog.delta < 0,
                KarmaLog.created_at >= cut,
            ).limit(1)
        )).first()
        if row is not None:
            return "ato"
    except Exception:
        logger.debug("_ambush_marked: karma_log falhou", exc_info=True)
    # MV-6 — quem o LUGAR despreza (leitor gated do irmão: flag OFF → 0 sem
    # query ⇒ este ramo simplesmente não existe).
    try:
        from core.reputation_engine import get_region_rep
        if int(await get_region_rep(session, int(player.telegram_id), continent)) <= JH_MARK_REP:
            return "rep"
    except Exception:
        logger.debug("_ambush_marked: rep falhou", exc_info=True)
    return None


async def _ambush_on_cooldown(session, player_id: int, now: datetime) -> bool:
    """Pacer PRÓPRIO (o explore não tem cooldown nenhum — `EXPLORE_COOLDOWN_SECONDS=0`
    — e uma chance solta viraria um corredor de emboscadas). Derivado das duas
    marcas que os três ramos deixam: o duelo (⚔️) e a linha de registro do
    `karma_log` (💰/🏃)."""
    cut = now - timedelta(hours=JH_AMBUSH_COOLDOWN_H)
    try:
        from database.models import DuelSession, KarmaLog
        row = (await session.execute(
            select(DuelSession.id).where(
                DuelSession.attacker_id == int(player_id),
                DuelSession.pve_source == JH_AMBUSH_SOURCE,
                DuelSession.created_at >= cut,
            ).limit(1)
        )).first()
        if row is not None:
            return True
        # A marca de 💰/🏃. ⚠️ Quem FUGIU volta a ser procurado em metade do
        # tempo: a janela efetiva sai da própria marca, não de uma constante.
        rows = (await session.execute(
            select(KarmaLog.created_at, KarmaLog.metadata_).where(
                KarmaLog.player_id == int(player_id),
                KarmaLog.event_type == "jianghu_ambush",
                KarmaLog.created_at >= cut,
            ).order_by(KarmaLog.created_at.desc()).limit(1)
        )).first()
        if rows is None:
            return False
        created, meta = rows[0], (rows[1] or {})
        created = _aware(created)
        window = JH_AMBUSH_COOLDOWN_H
        if str(meta.get("branch") or "") == "flee":
            window *= JH_FLEE_RETURN_FACTOR
        if created is None:
            return True
        return (now - created) < timedelta(hours=window)
    except Exception:
        logger.debug("_ambush_on_cooldown falhou", exc_info=True)
        return True   # fail-safe: na dúvida NÃO embosca


async def hunters_by_continent(session, now: datetime | None = None) -> dict[str, int]:
    """`{continente: nº de caçadores ativos}` — a MESMA verdade que alimenta a
    emboscada e o chip "há quem te procure" do mapa de viagem. Flag OFF → `{}`
    sem UMA query."""
    if not jianghu_on():
        return {}
    now = now or _utcnow()
    out: dict[str, int] = {}
    try:
        for npc in await _hunter_rows(session, None, now):
            cont = str((npc.loadout or {}).get("jh_hunt", {}).get("continent") or "")
            if cont in CONTINENT_KEYS:
                out[cont] = out.get(cont, 0) + 1
    except Exception:
        logger.debug("hunters_by_continent falhou", exc_info=True)
    return out


async def _hunter_rows(session, continent: str | None, now: datetime) -> list[Any]:
    """As rows seed com `jh_hunt` VIVO (a janela é filtrada em Python — o
    `until` mora dentro do JSONB e um operador de JSON no WHERE seria a única
    query não-portável do engine)."""
    rows = (await session.execute(
        select(NpcCultivator).where(
            NpcCultivator.status == "active",
            NpcCultivator.source_hash.is_(None),
        ).limit(200)
    )).scalars().all()
    out = []
    for npc in rows:
        hunt = (npc.loadout or {}).get("jh_hunt") or {}
        if not hunt:
            continue
        until = _aware(hunt.get("until"))
        if until is None or until <= now:
            continue
        if continent is not None and str(hunt.get("continent") or "") != continent:
            continue
        out.append(npc)
    return out


async def ambush_offer(session, player: Any, *, source: str, lang: str | None = None,
                       now: datetime | None = None) -> dict[str, Any] | None:
    """O ENCONTRO. Devolve o payload da oferta (ou None) — **nunca cria duelo**.

    Ordem deliberada: flag → chance do cano → pacer → marca → caçador VIVO.
    A chance vem antes das queries para que um mundo com a flag ON pague, na
    esmagadora maioria dos taps, exatamente UM `random()` e nada mais.

    ⚠️ `lang` DERIVA do jogador quando o caller não o passa (molde do irmão
    `storylet_engine.maybe_offer`). Com um default fixo "pt", o cano de
    VIAGEM — o mais generoso dos três, 20% — mandava título/intro/motivo em
    português para todo jogador en/es, colados a botões em inglês.
    """
    if not jianghu_on() or player is None:
        return None
    lang = (lang or getattr(player, "language", None) or "pt").lower()
    chance = {
        "explore": JH_AMBUSH_EXPLORE_CHANCE,
        "plaza": JH_AMBUSH_PLAZA_CHANCE,
        "travel": JH_AMBUSH_TRAVEL_CHANCE,
    }.get(source, 0.0)
    if chance <= 0.0 or random.random() >= chance:
        return None
    now = now or _utcnow()
    try:
        continent = str(getattr(player, "current_continent", None) or "linghe")
        if not is_valid_continent(continent):
            return None
        if await _ambush_on_cooldown(session, int(player.telegram_id), now):
            return None
        reason = await _ambush_marked(session, player, continent, now)
        if reason is None:
            return None
        hunters = await _hunter_rows(session, continent, now)
        if not hunters:
            return None
        # Semeado por (mundo, jogador, epoch): dois taps do mesmo minuto veem
        # o mesmo caçador — nunca um elenco que troca a cada refresh.
        rng = random.Random(seed_for(current_world_key(), int(player.telegram_id),
                                     tick_epoch(now, 3600.0), salt="ambush"))
        npc = hunters[rng.randrange(len(hunters))]
        realm = int(getattr(player, "realm", 0) or 0)
        from core.bounty_engine import BOUNTY_REWARD_BASE, BOUNTY_REWARD_PER_REALM
        from core.combat_engine import NPC_DIFFICULTIES
        from core.i18n import t as i18n_t
        bribe = int(BOUNTY_REWARD_BASE + BOUNTY_REWARD_PER_REALM * realm)
        return {
            "npc_id": int(npc.id),
            "name": npc.name,
            "realm": int(npc.realm or 0),
            "power": int(npc.power or 0),
            "continent": continent,
            "reason": reason,
            "source": source,
            # NARRATIVA server-resolved (o mini-app tem ZERO keys de texto de
            # mundo — ele exibe a string já pronta, padrão Chronicle).
            "title": i18n_t(lang, "jh_amb_title"),
            "intro": i18n_t(lang, "jh_amb_intro", npc=npc.name),
            "reason_line": i18n_t(lang, f"jh_amb_reason_{reason}"),
            "qi_cost": int(NPC_DIFFICULTIES.get("normal", {}).get("qi_cost", 25) or 25),
            "travel_cooldown_hours": int(_travel_cooldown_hours()),
            # O número é DITO ANTES do tap (Lei §1) — e o botão nunca some por
            # falta de pedras: ele aparece desabilitado com o valor à vista
            # (a lição do hard-gate do [jogador]: nunca esconder a opção).
            "bribe_cost": bribe,
            "can_bribe": int(getattr(player, "spirit_stones", 0) or 0) >= bribe,
            "stones": int(getattr(player, "spirit_stones", 0) or 0),
        }
    except Exception:
        logger.exception("ambush_offer failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return None


async def ambush_resolve(session, player: Any, *, npc_id: int, branch: str,
                         lang: str = "pt", now: datetime | None = None) -> dict[str, Any]:
    """Os três ramos, em três eixos distintos: dinheiro (💰) / tempo (🏃) /
    risco (⚔️).

    ⚠️ **CONTRATO DE LOCK (E6):** o `player` chega **já travado
    `.with_for_update()` pelo caller**, exatamente como `do_travel` e
    `claim_bounty`. Não existe helper de débito de pedras neste projeto — os
    oito sinks fazem `player.spirit_stones = ... - cost` INLINE sobre uma row
    que o CALLER travou. Se este engine fizesse o próprio SELECT sem lock, um
    duplo-tap no botão 💰 debitaria duas vezes. O caller também é dono do commit.
    """
    if not jianghu_on():
        return {"ok": False, "reason": "off"}
    now = now or _utcnow()
    branch = (branch or "").lower()
    if branch not in ("fight", "bribe", "flee"):
        return {"ok": False, "reason": "invalid_branch"}
    try:
        npc = (await session.execute(
            select(NpcCultivator).where(NpcCultivator.id == int(npc_id))
        )).scalar_one_or_none()
        # O caçador pode ter ascendido entre a oferta e o tap (a cada 6h,
        # qualquer NPC de realm ≥ 4). Dizer que ele sumiu é a Lei §1; um botão
        # que não faz nada é o void.
        if npc is None or npc.status != "active":
            return {"ok": False, "reason": "hunter_gone"}
        hunt = (npc.loadout or {}).get("jh_hunt") or {}
        until = _aware(hunt.get("until"))
        if until is None or until <= now:
            return {"ok": False, "reason": "hunter_gone"}

        # ⚠️ CONSUMIR o encontro. O pacer era consultado só na OFERTA, e a
        # mensagem de chat guarda os 3 botões vivos: um duplo-toque em 💰
        # debitava as pedras DUAS vezes (o FOR UPDATE serializa um lost-update,
        # não um toque REPETIDO), e três toques em ⚔️ abriam três duelos — três
        # settles, três recompensas, por uma emboscada. A janela do caçador dura
        # 24h, então isso ficava aberto o dia inteiro.
        if await _ambush_on_cooldown(session, int(player.telegram_id), now):
            return {"ok": False, "reason": "already_resolved"}

        if branch == "bribe":
            realm = int(getattr(player, "realm", 0) or 0)
            from core.bounty_engine import BOUNTY_REWARD_BASE, BOUNTY_REWARD_PER_REALM
            cost = int(BOUNTY_REWARD_BASE + BOUNTY_REWARD_PER_REALM * realm)
            have = int(getattr(player, "spirit_stones", 0) or 0)
            if have < cost:
                return {"ok": False, "reason": "not_enough_stones",
                        "cost": cost, "have": have}
            # Pedras espirituais, NUNCA jade (Lei §4). Você paga exatamente o
            # que a sua cabeça valia.
            player.spirit_stones = have - cost
            _ambush_mark(session, player, npc, "bribe", now)
            return {"ok": True, "branch": "bribe", "spent_stones": cost,
                    "spirit_stones": int(player.spirit_stones or 0),
                    "npc_id": int(npc.id), "name": npc.name}

        if branch == "flee":
            # Custa a ESTRADA e a DÍVIDA — nunca HP e nunca karma. Recusar é
            # livre nesta casa; o que custa é comprar distância.
            #
            # ⚠️ A estrada sozinha NÃO é custo no cano de viagem (o mais
            # provável, 20%): o `do_travel` acabou de carimbar `last_travel_at`,
            # então re-carimbar não tira nada e a frase prometia 4h. O custo
            # REAL — e o do spec — é a DÍVIDA: quem foge é procurado de novo em
            # METADE do tempo (`_ambush_on_cooldown` lê a marca e encurta a
            # janela). Ele lembra da fuga.
            player.last_travel_at = now
            _ambush_mark(session, player, npc, "flee", now)
            return {"ok": True, "branch": "flee", "npc_id": int(npc.id),
                    "name": npc.name,
                    "travel_cooldown_ms": int(_travel_cooldown_hours() * 3600 * 1000),
                    "returns_in_hours": int(JH_AMBUSH_COOLDOWN_H * JH_FLEE_RETURN_FACTOR)}

        # ⚔️ Enfrentar — o ÚNICO ramo que cria um duelo, e só depois do tap.
        from core.combat_engine import get_current_hp, NPC_DIFFICULTIES
        if get_current_hp(player) <= 0:
            return {"ok": False, "reason": "hp_depleted"}
        # O guard que TODAS as outras cinco fontes de duelo têm e que
        # `start_duel_pve` NÃO faz por si. Sem ele, um duelo de exploração
        # abandonado (`_open_exploration_duel` só casa com a fonte dele) e uma
        # emboscada coexistiriam: as sondas "estou em duelo?" do jogo usam
        # `.limit(1)` sem ordem, o mini-app resumiria o duelo errado, e o sweep
        # settlearia OS DOIS — dois drenos de HP a partir da mesma vida.
        from database.models import DuelSession as _DS
        open_duel = (await session.execute(
            select(_DS.id).where(
                _DS.attacker_id == int(player.telegram_id),
                _DS.state.in_(["waiting_actions", "pending_acceptance"]),
            ).limit(1)
        )).first()
        if open_duel is not None:
            return {"ok": False, "reason": "duel_already_active",
                    "duel_id": str(open_duel[0])}
        qi_cost = int(NPC_DIFFICULTIES.get("normal", {}).get("qi_cost", 25) or 25)
        # ⚠️ A coluna chama-se `qi` — NÃO existe `current_qi` no modelo Player.
        # Com o nome errado o `getattr` devolvia o default 0 para TODO jogador,
        # e o ramo ⚔️ recusava 100% das vezes (com a barra de qi cheia); e a
        # linha do débito escrevia um atributo fantasma que o SQLAlchemy nunca
        # gravaria — ou seja, a luta seria de graça. Molde:
        # `api_combat_npc_cultivator_fight`.
        if float(player.qi or 0) < qi_cost:
            return {"ok": False, "reason": "qi_insufficient", "qi_cost": qi_cost,
                    "qi": float(player.qi or 0)}
        from core.duel_engine import start_duel_pve
        from core.npc_cultivator_engine import rehydrate_npc_fighter
        # ⚠️ O duelo PRIMEIRO, o qi depois. Se `start_duel_pve` levantasse com o
        # qi já debitado, o `except` devolveria internal_error — mas o endpoint
        # comita de qualquer forma, e o jogador pagaria por uma luta que nunca
        # existiu (o molde é o do_travel: nunca comitar um débito sem o efeito).
        duel = await start_duel_pve(
            session, player, archetype="npc_cultivator", difficulty="normal",
            source=JH_AMBUSH_SOURCE,
            context={"npc_id": int(npc.id),
                     "continent_key": str(getattr(player, "current_continent", None) or ""),
                     "reason": str(hunt.get("reason") or "")},
            fighter_b_override=rehydrate_npc_fighter(npc),
        )
        player.qi = max(0.0, float(player.qi or 0) - qi_cost)
        return {"ok": True, "branch": "fight", "duel_id": str(duel.id),
                "qi_cost": qi_cost, "npc_id": int(npc.id), "name": npc.name}
    except Exception:
        logger.exception("ambush_resolve failed (player=%s, npc=%s, branch=%s)",
                         getattr(player, "telegram_id", None), npc_id, branch)
        return {"ok": False, "reason": "internal_error"}


async def resolve_ambush_from_duel(session, duel, player, won: bool) -> dict[str, Any]:
    """O settle de `pve_source='jianghu_ambush'` (molde
    `resolve_npc_cultivator_from_duel`).

    Vitória paga a MESMA régua do desafio de praça (40 + 12·reino) e OFERECE o
    fork moral — nada de recompensa nova para uma luta que o jogador não
    procurou. A derrota não custa nada além do que o próprio duelo já cobra
    (o dreno de HP do `apply_post_duel_effects`): a emboscada é um risco
    ACEITO, nunca uma punição empilhada.

    O `player` já está FOR UPDATE na sessão do settle. Nunca levanta.
    """
    ctx = duel.pve_context or {}
    npc_id = ctx.get("npc_id")
    payload: dict[str, Any] = {
        "jianghu_ambush": True, "npc_id": npc_id, "won": bool(won),
        "offer_moral_choice": bool(won),
    }
    if won:
        try:
            from core.npc_cultivator_engine import (
                NPC_CHALLENGE_REWARD_BASE, NPC_CHALLENGE_REWARD_PER_REALM,
            )
            realm = int(player.realm or 0)
            reward = int((NPC_CHALLENGE_REWARD_BASE
                          + NPC_CHALLENGE_REWARD_PER_REALM * realm)
                         * random.uniform(0.85, 1.15))
            player.spirit_stones = int(player.spirit_stones or 0) + reward
            payload["reward_stones"] = reward
        except Exception:
            logger.exception("resolve_ambush_from_duel: reward failed (duel=%s)", duel.id)
        # O caçador que perdeu para a presa deixa de caçar — senão ele
        # reapareceria na próxima exploração como se nada tivesse acontecido
        # (e o chip do mapa continuaria a mentir).
        try:
            if npc_id is not None:
                npc = (await session.execute(
                    select(NpcCultivator).where(NpcCultivator.id == int(npc_id))
                    .with_for_update().execution_options(populate_existing=True)
                )).scalar_one_or_none()
                if npc is not None:
                    _set_loadout(npc, jh_hunt=None)
        except Exception:
            logger.exception("resolve_ambush_from_duel: hunt clear failed (duel=%s)", duel.id)
    # MV-6 — o mesmo gancho único de reputação/RIVAL que as outras duas fontes
    # de duelo vs NpcCultivator já chamam. Gated (flag OFF → None sem query).
    try:
        from core.reputation_engine import on_npc_duel_settled
        _mv6 = await on_npc_duel_settled(session, player, npc_id, bool(won))
        if _mv6:
            payload["mv6"] = _mv6
    except Exception:
        logger.exception("resolve_ambush_from_duel: mv6 hook failed (duel=%s)", duel.id)
    return payload


async def sweep_orphan_ambush_duels(session) -> int:
    """DEPRECADO desde 2026-09-04 — delega em `sweep_orphan_pve_duels`.

    ⚠️ Este varredor era um de TRES, cada um a nomear a SUA fonte, enquanto o
    codigo cria DEZ. Sete familias ficaram anos sem rede — entre elas a maior do
    jogo (`arena_npc_fallback`) e o proprio default de `start_duel_pve`
    (`npc_hunt`). Resultado medido a 2026-09-03: 27 duelos expirados a prender
    13 jogadores, o mais antigo ha' 103 dias.

    Fica como nome, nao como segunda implementacao: duas copias da mesma
    varredura divergem no primeiro fix que so' uma delas recebe. O scheduler
    chama a familia inteira, uma vez.
    """
    from core.duel_engine import sweep_orphan_pve_duels
    return await sweep_orphan_pve_duels(session)
def _travel_cooldown_hours() -> float:
    try:
        from core.travel_engine import TRAVEL_COOLDOWN_HOURS
        return float(TRAVEL_COOLDOWN_HOURS)
    except Exception:
        return 4.0


def _ambush_mark(session, player: Any, npc: Any, branch: str, now: datetime) -> None:
    """A marca do pacer para os ramos que NÃO criam duelo (💰/🏃).

    Uma linha de `KarmaLog` com **delta 0** — o precedente existe e é do próprio
    karma_engine (`path_crystallized`, "zero migration — é uma linha de KarmaLog
    com delta 0"). Escrita DIRETA, nunca por `apply_karma`: aquele caminho
    dispara o barramento de conquistas (#27 Karmic Devotee, contagem vitalícia)
    e um suborno não é um ato de karma. O evento fica FORA de `KARMA_EVENTS`,
    então o catálogo do KarmaModal — que itera esse dict — não é poluído.
    """
    try:
        from database.models import KarmaLog
        session.add(KarmaLog(
            player_id=int(player.telegram_id),
            delta=0,
            new_value=int(getattr(player, "karma", 0) or 0),
            event_type="jianghu_ambush",
            metadata_={"branch": branch, "npc_id": int(npc.id), "name": npc.name},
            created_at=now,
        ))
    except Exception:
        logger.exception("_ambush_mark falhou (player=%s)",
                         getattr(player, "telegram_id", None))


# ══════════════════════════════════════════════════════════════════════════
# P6 — A VITRINE: como o jogador DISTINGUE um NPC com vontade de uma estátua
# ══════════════════════════════════════════════════════════════════════════

def npc_jianghu_view(npc: Any, lang: str = "pt", *, now: datetime | None = None
                     ) -> dict[str, Any] | None:
    """O bloco `jianghu` do cartão de um NPC — server-resolved, no molde dos
    `wpulse_action_*` que a casa já usa para as 9 casas.

    **Key CONDICIONAL**: flag OFF (ou NPC sem feito) → `None` ⇒ a key nem
    aparece no payload ⇒ os 57 continuam byte-idênticos. PURA (sem DB).
    """
    if not jianghu_on():
        return None
    lo = getattr(npc, "loadout", None) or {}
    last = lo.get("jh_last") or {}
    hunt = lo.get("jh_hunt") or {}
    # ⚠️ MESMO clamp de `jianghu_strike_mult`. Sem ele, baixar `JH_SCALE_MAX`
    # por env (3 → 1) com rows já em 3 faria o cartão anunciar +12% enquanto o
    # duelo aplicava +4% — e o cartão É a promessa da Lei §1.
    scale = max(-JH_SCALE_MAX, min(JH_SCALE_MAX, int(lo.get("jh_scale", 0) or 0)))
    if not last and not hunt and not scale:
        return None
    now = now or _utcnow()
    from core.i18n import t as i18n_t
    out: dict[str, Any] = {}
    goal = last.get("goal")
    if goal in JH_GOALS:
        at = _aware(last.get("at"))
        out["goal"] = goal
        out["icon"] = goal_icon(goal)
        out["label"] = i18n_t(lang, goal_label_key(goal))
        out["at_ms"] = int(at.timestamp() * 1000) if at is not None else None
    hunt_until = _aware(hunt.get("until"))
    if hunt_until is not None and hunt_until > now:
        out["hunting"] = str(hunt.get("continent") or "")
        out["hunting_until_ms"] = int(hunt_until.timestamp() * 1000)
    if scale:
        pct = int(round(scale * JH_SCALE_STEP * 100))
        out["scale"] = scale
        out["power_pct"] = pct
        # Lei §1: um oponente mais perigoso tem de ser dito ANTES do tap — e
        # um oponente ENFRAQUECIDO não pode ser anunciado como vencedor. Duas
        # frases: a escala sobe E desce (o perdedor da vendeta leva −1).
        out["scale_line"] = (
            i18n_t(lang, "jh_scale_line", pct=pct) if scale > 0
            else i18n_t(lang, "jh_scale_line_down", pct=pct))
    return out or None


def jianghu_strike_mult(npc: Any) -> float:
    """O multiplicador de GOLPE que a escala do feudo dá. Estritamente
    strike-only (`combat_profile['faction_dmg']`, o lever harness-validado),
    clampado em ±12%, e ZERO com a flag OFF ⇒ o duelo dos 57 é byte-idêntico."""
    if not jianghu_on():
        return 1.0
    try:
        scale = int((getattr(npc, "loadout", None) or {}).get("jh_scale", 0) or 0)
    except (TypeError, ValueError):
        return 1.0
    scale = max(-JH_SCALE_MAX, min(JH_SCALE_MAX, scale))
    return 1.0 + JH_SCALE_STEP * scale
