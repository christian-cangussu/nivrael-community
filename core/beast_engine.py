import random
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update

# 名 2026-09-14 — o espolio da expedicao diz o nome na lingua do dono.
from core.i18n import (catalog_name, catalog_desc, catalog_text,
                       catalog_slug)
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import t
from core.activity_indicators import _invalidate_cache as _inv_cache
from config import (
    BEAST_RANKS,
    BEAST_RANK_INDEX,
    EXPEDITION_MIN_RANK,
    BEAST_TRAIN_COST_PER_LEVEL,
    BEAST_TRAIN_EXP_PER_LEVEL,
    BEAST_EVOLVE_CORES_COST,
    BEAST_CAPTURE_BASE_CHANCE,
    BEAST_MAX_LEVEL,
)
from database.models import (
    BeastCatalog,
    PlayerBeast,
    ExpeditionCatalog,
    PlayerInventory,
    Player,
    HerbCatalog,
    OreCatalog,
)

logger = logging.getLogger(__name__)


# ═══ 獸 O NOME DA BESTA — O DONO ÚNICO (2026-09-15) ══════════════════════════
#
# 🔴 A MEDIÇÃO DERRUBOU O PLANO QUE ESTE LOTE TRAZIA ESCRITO.
#
# O prompt trazia um conserto de duas linhas: *"não gravar `custom_name` na
# captura"* + *"as bestas já capturadas mantêm o nome que têm — ninguém perde
# nada"*. A segunda frase supõe que existam bestas com nome escolhido. Medido em
# produção ANTES de tocar em nada (`tools/db_readonly_besta_0915.py`, só SELECT):
#
#     main  1105 linhas · 241 donos  ·  RENOMEADAS: 0  ·  NULL: 0
#     s2      65 linhas ·  33 donos  ·  RENOMEADAS: 0  ·  NULL: 0
#
# **100% das 1170 linhas são a cópia mecânica do nome do catálogo**, e não podia
# ser de outra maneira: `custom_name` é escrito em exactamente DOIS sítios (a
# captura e a besta inicial), os dois com o nome do catálogo, e **não existe em
# lado nenhum do jogo uma forma de o jogador renomear uma besta**.
#
# ⇒ Parar de gravar na captura conserta as bestas FUTURAS e deixa as 1170 de
# hoje em inglês para sempre — 241 donos, 125 deles a jogar em português. Isso é
# a feature a chegar meia-feita, que é exactamente o que a Lei 0 proíbe.
#
# A regra que fica, e que alcança as 1170 sem escrever uma linha em produção:
# **um `custom_name` igual ao nome do catálogo NÃO é um nome escolhido — é a
# cópia que a captura gravou.** Quem escolher um nome diferente (hoje ninguém,
# amanhã talvez) mantém-no para sempre; quem nunca escolheu lê o catálogo, e o
# catálogo fala a língua dele.
#
# ⚠️ ZERO migrations e ZERO escrita em produção, de propósito: a coluna fica como
# está e é a LEITURA que passa a interpretá-la. No dia em que nascer o botão de
# renomear, ele grava e esta função devolve o que ele gravou, sem mudar.
#
# ⚠️ `lang` vem por PARÂMETRO e nunca se resolve aqui dentro (lição de 14/09: ir
# buscar o `player` no topo de uma função quebra a identidade OFF de quem a
# chama). Quem tem o jogador na mão é que passa a língua.
def beast_display_name(lang: str, beast, catalog) -> str:
    """O nome que o jogador lê para ESTA besta, na língua dele.

    O dono único das leituras que antes faziam `beast.custom_name or
    catalog.name` à mão, cada uma com o seu fallback diferente ("Beast", "???",
    "?"). Uma capacidade com dezassete ligações à mão diverge sempre (Lei F-7 §2).
    """
    raw = getattr(catalog, "name", None) or ""
    escolhido = getattr(beast, "custom_name", None) if beast is not None else None
    # o nome ESCOLHIDO manda — e só é escolhido quando difere do catálogo
    if escolhido and escolhido != raw:
        return escolhido
    if catalog is None:
        # sem catálogo não há o que traduzir: devolve-se o que houver, e nunca
        # um "???" — um jogador com uma linha órfã via o placeholder, não o bug
        return escolhido or ""
    return catalog_name(lang, "beast", catalog, fallback=raw)


# ── 旅 2026-09-15 — A EXPEDIÇÃO, e a dificuldade PRÓPRIA desta família ───────
#
# `PlayerBeast.expedition_type` **guarda o NOME**, e esse nome é a CHAVE de
# consulta (`where(ExpeditionCatalog.name == exp_name)` na `collect_expedition`).
# Portanto o display tem de passar a traduzir **sem que a consulta mude** — e é
# por isso que esta porta aceita as DUAS formas: a linha do catálogo (a lista de
# escolha tem-na na mão) e a string solta (o estado da besta só tem o nome).
#
# 🔴 A razão de existir uma função em vez de cinco `catalog_text(...)` à mão: a
# tela imprimia, na MESMA frase, "Boi do Trovão em Herb Expedition" — metade
# traduzida, metade crua. São NOVE sítios de display (o prompt anunciava cinco;
# a contagem real apanhou o botão da escolha, a descrição da API e a DM do
# agendador). Nove ligações à mão divergem sempre (Lei F-7 §2).
#
# ⚠️ **Interpreta-se na LEITURA, e é deliberado.** O payload da notificação
# `expedition_done` já está gravado em inglês nas linhas antigas da base
# (memória: "Notificação NUNCA ganha placeholder novo"). Resolver aqui, no
# momento de imprimir, conserta também o que já está escrito — zero migration,
# exactamente como o 卷獸圖 de 15/09 alcançou 1170 linhas.
#
# ⚠️ ZERO arte: as expedições não estão no `ART_KIND_PREFIX` do cliente (não são
# peças de carta, são lugares com emoji). Portanto não há `art_key` a preservar
# aqui — se um dia houver, o slug tem de vir do nome CANÓNICO, nunca do traduzido.
def expedition_display_name(lang: str, exp_or_name) -> str:
    """O nome da expedição na língua do jogador — da linha OU do nome cru.

    `catalog_name(lang, "exped", row)` para quem tem a linha; para quem só tem a
    string (`beast.expedition_type`) monta-se a mesma chave pelo mesmo slug, que
    é o que `_KEYED_BY_SLUG` já garante ser idêntico nos dois caminhos.
    """
    if exp_or_name is None:
        return ""
    if isinstance(exp_or_name, str):
        raw = exp_or_name
        if not raw:
            return ""
        return catalog_text(lang, "exped", catalog_slug(raw), "name", raw)
    return catalog_name(lang, "exped", exp_or_name,
                        fallback=getattr(exp_or_name, "name", None) or "")


def expedition_display_desc(lang: str, exp_row) -> str:
    """A descrição da expedição. Só a linha do catálogo a tem."""
    if exp_row is None:
        return ""
    return catalog_desc(lang, "exped", exp_row,
                        fallback=getattr(exp_row, "description", None) or "")


def beast_art_key(catalog) -> str:
    """A chave CANÓNICA que nomeia a ARTE desta besta — nunca o nome traduzido.

    🔴 Sem isto, traduzir os 15 nomes APAGA as 15 peças de arte em `pt` e `es`,
    sem erro nenhum: o cliente monta o URL a partir do nome (`beast-` + slug do
    nome), e "Boi do Trovão" não está no índice. É a avaria de 14/09 — 229 peças
    invisíveis por língua — a tentar acontecer pela terceira vez.

    ⚠️ Uma besta RENOMEADA também usa a chave do catálogo: a arte é da espécie,
    não do apelido.
    """
    return getattr(catalog, "name", None) or ""


def beast_ability_text(lang: str, catalog) -> str:
    """A HABILIDADE da espécie, na língua do jogador (🐾 3.3, 2026-10-01).

    `special_ability` é uma frase do catálogo escrita em inglês ("Jade Shell —
    +10% HP in combat") e saía assim nas DUAS superfícies — o detalhe do chat e
    o do mini-app —, ao lado de um nome já traduzido desde 15/09: metade da
    ficha numa língua, metade noutra. O texto vive em `beast_<id>_ability` × 3;
    sem a chave, a frase do catálogo (exactamente o de hoje — nunca pior).
    """
    if catalog is None:
        return ""
    raw = getattr(catalog, "special_ability", None) or ""
    return catalog_text(lang, "beast", getattr(catalog, "id", None), "ability", raw)


def limiar_xp(level) -> int:
    """O XP que o nível ``level`` pede para passar ao seguinte: ``level × 100``.

    🐾 3.3 (2026-10-01) — a regra estava escrita à mão em OITO sítios: o treino,
    o treino em lote e a recolha da expedição (dois cada, aqui), a lista do
    mini-app e o detalhe do chat. O fio de XP que a tela desenha tem de ser a
    MESMA conta com que o motor sobe de nível — duas cópias divergem sempre
    (Lei 0 §2). Fica uma, e a guarda da §33 conta as outras.
    """
    return int(level) * 100


async def get_player_beasts(session: AsyncSession, player_id: int) -> list[PlayerBeast]:
    # Order: companion first, then highest rank, then highest level. Without this,
    # late-game players with Lv100 beasts had them stuck on the last page because
    # the DB returned them in capture order.
    stmt = (
        select(PlayerBeast)
        .where(PlayerBeast.player_id == player_id)
        .order_by(
            PlayerBeast.is_companion.desc(),
            PlayerBeast.level.desc(),
            PlayerBeast.id,
        )
    )
    return (await session.execute(stmt)).scalars().all()


async def get_beast_catalog(session: AsyncSession) -> list[BeastCatalog]:
    return (await session.execute(select(BeastCatalog))).scalars().all()


async def get_beast_catalog_by_id(session: AsyncSession, catalog_id: int) -> BeastCatalog | None:
    return (await session.execute(
        select(BeastCatalog).where(BeastCatalog.id == catalog_id)
    )).scalar_one_or_none()


async def get_expedition_catalog(session: AsyncSession) -> list[ExpeditionCatalog]:
    return (await session.execute(select(ExpeditionCatalog))).scalars().all()


async def get_companion_beast(session: AsyncSession, player_id: int) -> tuple[PlayerBeast | None, BeastCatalog | None]:
    stmt = select(PlayerBeast).where(
        PlayerBeast.player_id == player_id,
        PlayerBeast.is_companion == True,
    )
    pb = (await session.execute(stmt)).scalar_one_or_none()
    if not pb:
        return None, None
    catalog = await get_beast_catalog_by_id(session, pb.catalog_id)
    return pb, catalog


def get_companion_bonuses(beast: PlayerBeast | None, catalog: BeastCatalog | None) -> dict:
    bonuses = {
        "cb_mult": 1.0,
        "bp_mult": 1.0,
        "soul_mult": 1.0,
        "luck_mult": 1.0,
        "hp_mult": 1.0,
        "evasion_mult": 1.0,
        "qi_recovery_mult": 1.0,
        "perception_mult": 1.0,
    }
    if not beast or not catalog:
        return bonuses

    stats = catalog.base_stats or {}
    level_scale = 1.0 + (beast.level - 1) * 0.005

    # Evolution multiplier: each rank above the catalog's natural rank scales
    # the bonus. Without this, paying ~30 cores to evolve Phoenix Chick
    # (Mythic) → Divine produced zero stat change because ``catalog.base_stats``
    # is fixed to the captured tier — players burned cores for nothing.
    rank_idx_now = BEAST_RANK_INDEX.get(beast.rank, 0)
    rank_idx_orig = BEAST_RANK_INDEX.get(catalog.rank, 0)
    evolution_steps = max(0, rank_idx_now - rank_idx_orig)
    evolution_mult = 1.0 + evolution_steps * 0.50

    for key in bonuses:
        if key in stats:
            raw_bonus = (stats[key] - 1.0) * evolution_mult
            bonuses[key] = 1.0 + raw_bonus * level_scale

    return bonuses


async def set_companion(session: AsyncSession, player_id: int, beast_id: int) -> bool:
    stmt = select(PlayerBeast).where(
        PlayerBeast.player_id == player_id,
        PlayerBeast.id == beast_id,
    )
    beast = (await session.execute(stmt)).scalar_one_or_none()
    if not beast:
        return False
    if beast.is_on_expedition:
        return False

    await session.execute(
        update(PlayerBeast)
        .where(PlayerBeast.player_id == player_id, PlayerBeast.is_companion == True)
        .values(is_companion=False)
    )
    beast.is_companion = True
    return True


async def remove_companion(session: AsyncSession, player_id: int) -> bool:
    result = await session.execute(
        update(PlayerBeast)
        .where(PlayerBeast.player_id == player_id, PlayerBeast.is_companion == True)
        .values(is_companion=False)
    )
    return result.rowcount > 0


async def train_beast(session: AsyncSession, player_id: int, beast_id: int) -> dict:
    stmt = select(PlayerBeast).where(
        PlayerBeast.player_id == player_id,
        PlayerBeast.id == beast_id,
    )
    beast = (await session.execute(stmt)).scalar_one_or_none()
    if not beast:
        return {"success": False, "error_key": "err_beast_not_found"}
    if beast.level >= BEAST_MAX_LEVEL:
        return {"success": False, "error_key": "err_beast_max_level"}
    if beast.is_on_expedition:
        return {"success": False, "error_key": "err_beast_on_expedition"}

    cost = BEAST_TRAIN_COST_PER_LEVEL * beast.level
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()
    if not player or player.spirit_stones < cost:
        return {"success": False, "error_key": "err_beast_stones_needed", "error_params": {"cost": cost}}

    from database.models import PlayerBuff
    _now = datetime.now(timezone.utc)
    _food_buff = (await session.execute(
        select(PlayerBuff).where(
            PlayerBuff.player_id == player_id,
            PlayerBuff.buff_type == "beast_food",
            PlayerBuff.expires_at > _now
        )
    )).scalar_one_or_none()
    xp_mult = _food_buff.buff_value if _food_buff else 1.0
    xp_gained = int(BEAST_TRAIN_EXP_PER_LEVEL * xp_mult)

    player.spirit_stones -= cost
    beast.exp = (beast.exp or 0) + xp_gained
    exp_needed = limiar_xp(beast.level)
    levels_gained = 0
    while beast.exp >= exp_needed and beast.level < BEAST_MAX_LEVEL:
        beast.exp -= exp_needed
        beast.level += 1
        levels_gained += 1
        exp_needed = limiar_xp(beast.level)

    return {
        "success": True,
        "cost": cost,
        "levels_gained": levels_gained,
        "new_level": beast.level,
        "exp": beast.exp,
        "exp_needed": exp_needed,
        "xp_boosted": xp_mult > 1.0,
        "xp_gained": xp_gained,
    }


async def train_beast_bulk(session: AsyncSession, player_id: int, beast_id: int, target_levels: int | None) -> dict:
    """H-9: train repeatedly until target_levels reached or resources run out.
    target_levels=None → train until stones run out or beast hits BEAST_MAX_LEVEL.

    Fix 2026-04-30: previous version called ``train_beast`` in a loop, which
    re-issued ``session.execute(select(...))`` each iteration. SQLAlchemy then
    autoflushed pending updates from the prior iteration — if one of those
    updates raised (e.g. transient connection blip), the whole router crashed
    with a half-baked traceback. Fetch player + beast + buff once up-front
    and do the loop entirely in-memory; flush once at the end.
    """
    from database.models import PlayerBuff

    beast = (await session.execute(
        select(PlayerBeast).where(
            PlayerBeast.player_id == player_id,
            PlayerBeast.id == beast_id,
        )
    )).scalar_one_or_none()
    if not beast:
        return {"success": False, "last_error": {"error_key": "err_beast_not_found"}, "iterations": 0,
                "cost": 0, "xp_gained": 0, "levels_gained": 0, "new_level": None}
    if beast.is_on_expedition:
        return {"success": False, "last_error": {"error_key": "err_beast_on_expedition"}, "iterations": 0,
                "cost": 0, "xp_gained": 0, "levels_gained": 0, "new_level": beast.level}
    if beast.level >= BEAST_MAX_LEVEL:
        return {"success": False, "last_error": {"error_key": "err_beast_max_level"}, "iterations": 0,
                "cost": 0, "xp_gained": 0, "levels_gained": 0, "new_level": beast.level}

    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()
    if not player:
        return {"success": False, "last_error": {"error_key": "err_beast_not_found"}, "iterations": 0,
                "cost": 0, "xp_gained": 0, "levels_gained": 0, "new_level": beast.level}

    _now = datetime.now(timezone.utc)
    _food_buff = (await session.execute(
        select(PlayerBuff).where(
            PlayerBuff.player_id == player_id,
            PlayerBuff.buff_type == "beast_food",
            PlayerBuff.expires_at > _now,
        )
    )).scalar_one_or_none()
    xp_mult = _food_buff.buff_value if _food_buff else 1.0

    total_cost = 0
    total_xp = 0
    levels_gained = 0
    iterations = 0
    last_error = None
    safety = 500

    while iterations < safety:
        if beast.level >= BEAST_MAX_LEVEL:
            last_error = {"error_key": "err_beast_max_level"}
            break
        cost = BEAST_TRAIN_COST_PER_LEVEL * beast.level
        if player.spirit_stones < cost:
            last_error = {"error_key": "err_beast_stones_needed", "error_params": {"cost": cost}}
            break

        xp_gained = int(BEAST_TRAIN_EXP_PER_LEVEL * xp_mult)
        player.spirit_stones -= cost
        beast.exp = (beast.exp or 0) + xp_gained

        exp_needed = limiar_xp(beast.level)
        while beast.exp >= exp_needed and beast.level < BEAST_MAX_LEVEL:
            beast.exp -= exp_needed
            beast.level += 1
            levels_gained += 1
            exp_needed = limiar_xp(beast.level)

        total_cost += cost
        total_xp += xp_gained
        iterations += 1

        if target_levels is not None and levels_gained >= target_levels:
            break

    return {
        "success": iterations > 0,
        "cost": total_cost,
        "xp_gained": total_xp,
        "levels_gained": levels_gained,
        "iterations": iterations,
        "last_error": last_error,
        "new_level": beast.level,
        "xp_boosted": xp_mult > 1.0,
    }


def get_evolution_requirements(beast: PlayerBeast) -> dict:
    current_rank_idx = BEAST_RANK_INDEX.get(beast.rank, 0)
    if current_rank_idx >= len(BEAST_RANKS) - 1:
        return {"can_evolve": False, "at_max": True}

    next_rank = BEAST_RANKS[current_rank_idx + 1]
    cores_needed = BEAST_EVOLVE_CORES_COST * (current_rank_idx + 1)
    level_needed = (current_rank_idx + 1) * 10

    return {
        "can_evolve": True,
        "at_max": False,
        "current_rank": beast.rank,
        "next_rank": next_rank,
        "cores_needed": cores_needed,
        "level_needed": level_needed,
        "current_level": beast.level,
        "level_met": beast.level >= level_needed,
    }


async def evolve_beast(session: AsyncSession, player_id: int, beast_id: int) -> dict:
    stmt = select(PlayerBeast).where(
        PlayerBeast.player_id == player_id,
        PlayerBeast.id == beast_id,
    )
    beast = (await session.execute(stmt)).scalar_one_or_none()
    if not beast:
        return {"success": False, "error_key": "err_beast_not_found"}
    if beast.is_on_expedition:
        return {"success": False, "error_key": "err_beast_on_expedition"}

    reqs = get_evolution_requirements(beast)
    if reqs.get("at_max"):
        return {"success": False, "error_key": "err_beast_max_rank"}

    if not reqs["level_met"]:
        return {"success": False, "error_key": "err_beast_level_needed", "error_params": {"level": reqs['level_needed'], "current": beast.level}}

    cores_needed = reqs["cores_needed"]
    inv_stmt = select(PlayerInventory).where(
        PlayerInventory.player_id == player_id,
        PlayerInventory.item_type == "beast_core",
    )
    core_rows = (await session.execute(inv_stmt)).scalars().all()
    total_cores = sum(r.quantity for r in core_rows)
    if total_cores < cores_needed:
        return {"success": False, "error_key": "err_beast_cores_needed", "error_params": {"cores": cores_needed, "qty": total_cores}}

    remaining = cores_needed
    for row in sorted(core_rows, key=lambda r: r.quantity, reverse=True):
        if remaining <= 0:
            break
        deduct = min(row.quantity, remaining)
        row.quantity -= deduct
        remaining -= deduct
    old_rank = beast.rank
    beast.rank = BEAST_RANKS[BEAST_RANK_INDEX[beast.rank] + 1]

    return {
        "success": True,
        "old_rank": old_rank,
        "new_rank": beast.rank,
        "cores_used": cores_needed,
    }


async def send_on_expedition(
    session: AsyncSession, player_id: int, beast_id: int, expedition_id: int
) -> dict:
    beast = (await session.execute(
        select(PlayerBeast).where(
            PlayerBeast.player_id == player_id,
            PlayerBeast.id == beast_id,
        )
    )).scalar_one_or_none()
    if not beast:
        return {"success": False, "error_key": "err_beast_not_found"}
    if beast.is_on_expedition:
        return {"success": False, "error_key": "err_beast_already_expedition"}
    if beast.is_companion:
        return {"success": False, "error_key": "err_beast_remove_companion"}

    # VIP expedition slot check
    from core.monetization import get_player_vip_level, get_vip_perks
    vip_lvl = await get_player_vip_level(session, player_id)
    perks = get_vip_perks(vip_lvl)
    base_slots = 1
    max_slots = base_slots + perks["expedition_slots"]

    active_exps = (await session.execute(
        select(PlayerBeast).where(
            PlayerBeast.player_id == player_id,
            PlayerBeast.is_on_expedition == True,
        )
    )).scalars().all()
    if len(active_exps) >= max_slots:
        return {"success": False, "error_key": "err_expedition_slots_full", "error_params": {"max_slots": max_slots}}

    expedition = (await session.execute(
        select(ExpeditionCatalog).where(ExpeditionCatalog.id == expedition_id)
    )).scalar_one_or_none()
    if not expedition:
        return {"success": False, "error_key": "err_expedition_not_found"}

    beast_rank_idx = BEAST_RANK_INDEX.get(beast.rank, 0)
    req_rank_idx = BEAST_RANK_INDEX.get(expedition.req_beast_rank, 0)
    if beast_rank_idx < req_rank_idx:
        return {"success": False, "error_key": "err_beast_rank_needed", "error_params": {"rank": expedition.req_beast_rank}}

    returns_at = datetime.now(timezone.utc) + timedelta(hours=expedition.duration_hours)
    beast.is_on_expedition = True
    beast.expedition_type = expedition.name
    beast.expedition_returns_at = returns_at

    return {
        "success": True,
        "expedition_name": expedition.name,
        "returns_at": returns_at,
        "duration_hours": expedition.duration_hours,
    }


async def collect_expedition(session: AsyncSession, player_id: int, beast_id: int, lang: str = "en") -> dict:
    # SEC (2026-06-01): lock the beast row so concurrent collect requests
    # serialize — the second txn blocks, re-reads is_on_expedition=False under the
    # lock, and bails (no double-collect of expedition rewards).
    beast = (await session.execute(
        select(PlayerBeast).where(
            PlayerBeast.player_id == player_id,
            PlayerBeast.id == beast_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if not beast or not beast.is_on_expedition:
        return {"success": False, "error_key": "err_beast_not_on_expedition"}

    now = datetime.now(timezone.utc)
    if beast.expedition_returns_at and now < beast.expedition_returns_at:
        remaining = beast.expedition_returns_at - now
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        return {"success": False, "error_key": "err_expedition_not_ready", "error_params": {"hours": hours, "minutes": minutes}}

    exp_name = beast.expedition_type
    expedition = (await session.execute(
        select(ExpeditionCatalog).where(ExpeditionCatalog.name == exp_name)
    )).scalar_one_or_none()

    drops_result = []
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()

    if expedition and player:
        drops_data = expedition.drops or {}

        for item in drops_data.get("guaranteed", []):
            qty = random.randint(item.get("qty_min", 1), item.get("qty_max", 1))
            if item["type"] == "herb":
                _ok = await _add_inventory(session, player_id, "herb", item["item_id"], qty)
                _herb = await session.get(HerbCatalog, item["item_id"])
                _herb_name = catalog_name(lang, "herb", _herb) if _herb else f"Herb #{item['item_id']}"
                # Medium (v16.6): never silently discard a drop when the ring is
                # full — disclose it instead (lei §1). Ore/stones below always
                # stack and can't fail; only slot-using drops can.
                if _ok:
                    drops_result.append(f"🌿 {_herb_name} x{qty}")
                else:
                    drops_result.append(t(lang, "beast_drop_lost_full", item=f"🌿 {_herb_name} x{qty}"))
            elif item["type"] == "ore":
                from database.models import PlayerOre
                ore_stmt = select(PlayerOre).where(
                    PlayerOre.player_id == player_id,
                    PlayerOre.ore_id == item["ore_id"],
                )
                ore = (await session.execute(ore_stmt)).scalar_one_or_none()
                if ore:
                    ore.quantity += qty
                else:
                    session.add(PlayerOre(player_id=player_id, ore_id=item["ore_id"], quantity=qty))
                _ore_cat = await session.get(OreCatalog, item["ore_id"])
                _ore_name = catalog_name(lang, "ore", _ore_cat) if _ore_cat else f"Ore #{item['ore_id']}"
                drops_result.append(f"⛏️ {_ore_name} x{qty}")

        for item in drops_data.get("bonus", []):
            if random.random() > item.get("chance", 0):
                continue
            if item["type"] == "spirit_stones":
                amount = random.randint(item.get("amount_min", 10), item.get("amount_max", 100))
                player.spirit_stones += amount
                drops_result.append(f"🪨 {amount} {t(lang, 'currency_spirit_stones')}")
            elif item["type"] == "ore":
                qty = random.randint(item.get("qty_min", 1), item.get("qty_max", 1))
                from database.models import PlayerOre
                ore_stmt = select(PlayerOre).where(
                    PlayerOre.player_id == player_id,
                    PlayerOre.ore_id == item["ore_id"],
                )
                ore = (await session.execute(ore_stmt)).scalar_one_or_none()
                if ore:
                    ore.quantity += qty
                else:
                    session.add(PlayerOre(player_id=player_id, ore_id=item["ore_id"], quantity=qty))
                _ore_cat2 = await session.get(OreCatalog, item["ore_id"])
                _ore_name2 = catalog_name(lang, "ore", _ore_cat2) if _ore_cat2 else f"Ore #{item['ore_id']}"
                drops_result.append(f"⛏️ {_ore_name2} x{qty}")
            elif item["type"] == "beast_core":
                qty = random.randint(item.get("qty_min", 1), item.get("qty_max", 1))
                _ok = await _add_inventory(session, player_id, "beast_core", 0, qty)
                if _ok:
                    drops_result.append(f"💎 {t(lang, 'beast_core_name')} x{qty}")
                else:
                    drops_result.append(t(lang, "beast_drop_lost_full", item=f"💎 {t(lang, 'beast_core_name')} x{qty}"))

        egg_chance = drops_data.get("beast_egg_chance", 0)
        from core.alchemy_engine import get_active_buffs
        _exp_buffs = await get_active_buffs(session, player_id)
        _luck_mult = next((b.buff_value for b in _exp_buffs if b.buff_type == "luck_boost"), 1.0)
        luck_bonus = player.luck * _luck_mult * 0.002
        if random.random() < egg_chance + luck_bonus:
            _ok = await _add_inventory(session, player_id, "beast_trap", 0, 1)
            if _ok:
                drops_result.append(t(lang, "beast_egg_drop"))
            else:
                drops_result.append(t(lang, "beast_drop_lost_full", item=t(lang, "beast_egg_drop")))

        # Recipe drop from expeditions (12-18% chance, T2-T4 pills)
        from core.alchemy_engine import roll_recipe_drop
        _recipe_chance = drops_data.get("recipe_chance", 0.12)
        _recipe_max_tier = drops_data.get("recipe_max_tier", 3)
        _recipe_pill_id = await roll_recipe_drop(session, player_id, (2, _recipe_max_tier), _recipe_chance)
        if _recipe_pill_id:
            from database.models import PillCatalog
            _pill = await session.get(PillCatalog, _recipe_pill_id)
            _pill_name = catalog_name(lang, "pill", _pill) if _pill else f"Recipe #{_recipe_pill_id}"
            drops_result.append(f"📜 {t(lang, 'beast_recipe_drop', pill_name=_pill_name)}")

    # XP scales with expedition difficulty + duration (not just beast rank)
    if expedition:
        exp_rank_idx = BEAST_RANK_INDEX.get(expedition.req_beast_rank, 0)
        beast.exp += 25 * (exp_rank_idx + 1) + 10 * expedition.duration_hours
    else:
        beast.exp += 50 * (BEAST_RANK_INDEX.get(beast.rank, 0) + 1)
    exp_needed = limiar_xp(beast.level)
    while beast.exp >= exp_needed and beast.level < BEAST_MAX_LEVEL:
        beast.exp -= exp_needed
        beast.level += 1
        exp_needed = limiar_xp(beast.level)
        drops_result.append(t(lang, "beast_level_up", level=beast.level))

    beast.is_on_expedition = False
    beast.expedition_type = None
    beast.expedition_returns_at = None
    _inv_cache(player_id)

    # Sprint 5 — Caça 狩猎 (BC-3, server-gated): in a `cultivo_corpo_r0` world a
    # R0–R6 cultivator's beast hunt ALSO brings back body-tempering materials
    # (hunt_essence), refined later into Mortal temper progress. ADDITIVE + gated →
    # main/OFF is a no-op (the 57's expedition loot is byte-identical). Defensive:
    # the body feature must never break expedition collection.
    try:
        from database.db import feature_enabled_for_world
        from core.body_tempering_engine import MIN_REALM_REQUIRED
        if (player is not None and feature_enabled_for_world("cultivo_corpo_r0")
                and int(player.realm or 0) < MIN_REALM_REQUIRED):
            from core.hunt_engine import expedition_essence_reward
            _ess = expedition_essence_reward(expedition)
            if _ess > 0:
                player.hunt_essence = int(getattr(player, "hunt_essence", 0) or 0) + _ess
                drops_result.append(t(lang, "hunt_essence_drop", n=_ess))
    except Exception:
        logger.debug("hunt essence reward skipped (player=%s)", player_id, exc_info=True)

    from core.faction_engine import update_quest_progress as fac_quest_progress
    await fac_quest_progress(session, player_id, "expedition")

    # MV-2 §0 — a weekly quest 15 ("long_expedition", 8h+) NUNCA progredia:
    # faucet órfão descoberto na auditoria do MV-1. O wire vive AQUI no engine
    # porque `expedition.duration_hours` não sai no return — e o engine cobre
    # chat + mini-app de uma vez. Threshold 8 = o "8h+" do texto da quest 15
    # (o seed não tem campo estruturado). Melhoria-estrita em main.
    try:
        if expedition is not None and int(expedition.duration_hours or 0) >= 8:
            from core.quest_engine import track_quest
            await track_quest(session, player_id, "long_expedition", 1)
    except Exception:
        logger.warning("long_expedition track_quest failed (player=%s)",
                       player_id, exc_info=True)

    _b_cat = await get_beast_catalog_by_id(session, beast.catalog_id)
    return {
        "success": True,
        "drops": drops_result,
        # 獸 2026-09-15 — as ervas, os minérios e as pílulas deste mesmo espólio
        # já saíam traduzidos desde 14/09; só a BESTA é que continuava em inglês,
        # na mesma linha de texto. Era a inconsistência dentro de UMA frase.
        "beast_name": beast_display_name(lang, beast, _b_cat),
        "beast_art_key": beast_art_key(_b_cat),
    }


async def attempt_capture(session: AsyncSession, player_id: int, catalog_id: int) -> dict:
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()
    if not player:
        return {"success": False, "error_key": "err_player_not_found"}
    # 獸 a língua sai do `player` que esta função JÁ tinha em mão — zero queries
    # novas, e por isso nenhum gate a montante muda de comportamento.
    _lang_cap = player.language or "pt"

    # Fetch all trap stacks, ordered by quality (use worst first, save best for harder beasts)
    TRAP_QUALITY_ORDER = {"normal": 0, "common": 1, "rare": 2, "epic": 3, "mythic": 4, "legendary": 5}
    TRAP_CAPTURE_BONUS = {"normal": 0.0, "common": 0.0, "rare": 0.05, "epic": 0.10, "mythic": 0.20, "legendary": 0.30}

    all_traps = (await session.execute(
        select(PlayerInventory).where(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "beast_trap",
            PlayerInventory.quantity >= 1,
        )
    )).scalars().all()
    if not all_traps:
        return {"success": False, "error_key": "err_beast_trap_needed"}

    # Use the best trap available (highest rarity)
    all_traps.sort(key=lambda t: TRAP_QUALITY_ORDER.get(t.quality or "normal", 0), reverse=True)
    trap_inv = all_traps[0]
    trap_quality = trap_inv.quality or "normal"

    catalog = await get_beast_catalog_by_id(session, catalog_id)
    if not catalog:
        return {"success": False, "error_key": "err_beast_not_in_catalog"}

    from core.alchemy_engine import get_active_buffs
    _cap_buffs = await get_active_buffs(session, player_id)
    _luck_mult = next((b.buff_value for b in _cap_buffs if b.buff_type == "luck_boost"), 1.0)
    luck_bonus = player.luck * _luck_mult * 0.003
    trap_bonus = TRAP_CAPTURE_BONUS.get(trap_quality, 0.0)
    chance = min(0.95, catalog.catch_rate * BEAST_CAPTURE_BASE_CHANCE + luck_bonus + trap_bonus)

    from database.models import PlayerBuff
    _now = datetime.now(timezone.utc)
    _lure = (await session.execute(
        select(PlayerBuff).where(
            PlayerBuff.player_id == player_id,
            PlayerBuff.buff_type == "beast_lure",
            PlayerBuff.expires_at > _now
        )
    )).scalar_one_or_none()
    lure_used = False
    if _lure:
        chance = min(0.95, chance + 0.20)

    trap_inv.quantity -= 1
    if trap_inv.quantity <= 0:
        await session.delete(trap_inv)

    if _lure:
        _lure.buff_value -= 1
        if _lure.buff_value <= 0:
            await session.delete(_lure)
        lure_used = True

    roll = random.random()

    if roll > chance:
        return {
            "success": False,
            "captured": False,
            "beast_name": beast_display_name(_lang_cap, None, catalog),
            "beast_art_key": beast_art_key(catalog),
            "emoji": catalog.emoji,
            "chance": chance,
            "trap_quality": trap_quality,
        }

    new_beast = PlayerBeast(
        player_id=player_id,
        catalog_id=catalog_id,
        rank=catalog.rank,
        # 獸 2026-09-15 — a captura DEIXOU de gravar `custom_name`.
        # NULL quer dizer "ainda não lhe dei nome", que é o que o resolvedor
        # (`beast_display_name`) espera. Gravar aqui o nome do catálogo era o que
        # trancava a família inteira em inglês: o nome ficava congelado na linha,
        # na língua em que foi capturada, e nenhuma tradução lhe chegava.
        # ⚠️ As 1170 linhas ANTIGAS não precisam de migration — o resolvedor trata
        # `custom_name == catalog.name` como "não escolhido". Ver a nota no topo.
        level=1,
        exp=0,
    )
    session.add(new_beast)

    return {
        "success": True,
        "captured": True,
        "beast_name": beast_display_name(_lang_cap, None, catalog),
        "beast_art_key": beast_art_key(catalog),
        "emoji": catalog.emoji,
        "rank": catalog.rank,
        "chance": chance,
        "trap_quality": trap_quality,
    }


async def grant_starter_beast(session: AsyncSession, player_id: int):
    existing = await get_player_beasts(session, player_id)
    if existing:
        return

    thunder_ox = await get_beast_catalog_by_id(session, 1)
    if not thunder_ox:
        return

    starter = PlayerBeast(
        player_id=player_id,
        catalog_id=1,
        rank="Common",
        # 獸 2026-09-15 — sem `custom_name`, pelo mesmo motivo da captura: o
        # Boi do Trovão é a PRIMEIRA besta que todo jogador vê, e gravá-lo aqui
        # em inglês trancava-o em inglês para sempre (256 linhas no main).
        level=1,
        exp=0,
        is_companion=True,
    )
    session.add(starter)


async def check_finished_expeditions(session: AsyncSession) -> list[dict]:
    """As expedições que ACABARAM DE terminar — cada uma anunciada UMA vez.

    ⚠️ BUG do [jogador] (2026-08-14, main): *"I keep getting message that beast
    expedition is complete, but it is not."* — e ele estava certo.

    Esta função selecionava as feras com `expedition_returns_at <= now` e
    **não mudava NADA**: não marcava a fera, não gravava que já tinha avisado.
    O job (`expedition_check_job`) corre de HORA A HORA, e a mesma linha
    continuava a bater no filtro para sempre — logo o jogador levava o mesmo
    aviso todas as horas até finalmente recolher. Pior: o aviso saía por
    `_bot.send_message` DIRETO, sem passar pelo `notify()`, portanto sem a
    deduplicação que esta casa já tem construída.

    A correção não precisa de coluna nova: `notify()` devolve `None` quando
    deduplica por `(player_id, kind, ref_id)`. O `ref_id` leva o instante do
    RETORNO, logo é estável para ESTA expedição e diferente para a próxima da
    mesma fera. Só entra na lista de DMs quem o `notify()` aceitou de facto —
    exactly-once, e o sino do mini-app ganha o aviso que nunca teve.

    O caller comita.
    """
    now = datetime.now(timezone.utc)
    stmt = select(PlayerBeast).where(
        PlayerBeast.is_on_expedition == True,
        PlayerBeast.expedition_returns_at != None,
        PlayerBeast.expedition_returns_at <= now,
    )
    finished = (await session.execute(stmt)).scalars().all()
    notifications = []
    # 獸 2026-09-15 — a língua é a do DONO de cada besta, e resolve-se AQUI.
    # Os dois consumidores desta lista precisam do mesmo texto: a linha do
    # `notify()` (que esta função escreve) e o DM do `expedition_check_job` (que
    # já sabe a língua mas usa o `beast_name` que vem daqui). Resolver num só
    # sítio é o que impede o sino e o DM de falarem línguas diferentes.
    # ⚠️ Uma consulta por DONO e não por besta: um jogador com cinco expedições
    # a terminar na mesma hora não paga cinco vezes.
    _lang_por_dono: dict[int, str] = {}
    for beast in finished:
        catalog = await get_beast_catalog_by_id(session, beast.catalog_id)
        _dono = int(beast.player_id)
        if _dono not in _lang_por_dono:
            _p = (await session.execute(
                select(Player.language).where(Player.telegram_id == _dono)
            )).scalar_one_or_none()
            _lang_por_dono[_dono] = _p or "pt"
        beast_name = beast_display_name(_lang_por_dono[_dono], beast, catalog)
        # 旅 2026-09-15 — a EXPEDIÇÃO resolve-se no MESMO sítio e com a MESMA
        # língua, e é deliberado seguir o irmão em vez de a interpretar na
        # leitura: a frase é uma só ("{beast} voltou de {type}"), e resolver
        # as duas metades em pontos diferentes é exactamente como ela nasceu
        # partida — "Boi do Trovão em Herb Expedition".
        # ⚠️ O CUSTO, dito: a linha gravada fica na língua de ENTÃO. Quem
        # mudar de idioma vê os avisos antigos na língua antiga — que é o que
        # o `beast_name` ao lado já faz desde 15/09. As linhas escritas ANTES
        # de hoje continuam em inglês; não há migration porque um aviso é um
        # registo do que aconteceu, não um ecrã de estado.
        exped_name = expedition_display_name(_lang_por_dono[_dono],
                                             beast.expedition_type)
        # A âncora da deduplicação: o instante do retorno DESTA expedição.
        try:
            _ret = beast.expedition_returns_at
            _stamp = int(_ret.timestamp()) if _ret else 0
        except Exception:
            _stamp = 0
        ref_id = f"exped:{int(beast.id)}:{_stamp}"
        try:
            from core.notification_engine import notify
            row = await notify(
                session, int(beast.player_id), "expedition_done",
                title_key="notif_expedition_done_title",
                body_key="notif_expedition_done_body",
                payload={"beast": beast_name,
                         "type": exped_name},
                ref_id=ref_id, icon="🗺️", target_tab="beasts", priority=3,
            )
        except Exception:
            logger.exception("expedition notify failed (beast=%s)", beast.id)
            row = None
        if row is None:
            continue          # já avisado nesta expedição — nada de DM repetido
        notifications.append({
            "player_id": beast.player_id,
            "beast_id": beast.id,
            "beast_name": beast_name,
            "expedition_type": exped_name,
        })
    return notifications


def get_pet_combat_ability(catalog: BeastCatalog | None, beast: PlayerBeast | None,
                           lang: str = "pt") -> dict | None:
    if not catalog or not beast:
        return None

    rank_idx = BEAST_RANK_INDEX.get(beast.rank, 0)
    level_scale = 1.0 + (beast.level - 1) * 0.01

    element = catalog.element
    base_mult = 0.05 + rank_idx * 0.03

    return {
        # ⚠️ Esta função é SÍNCRONA e não tem `player`: a língua vem por
        # parâmetro dos 4 chamadores (combate, dungeons, duelo, API), que já têm
        # o jogador na mão. Resolvê-la aqui dentro obrigaria a uma query numa
        # função que nunca teve nenhuma.
        "name": beast_display_name(lang, beast, catalog),
        "art_key": beast_art_key(catalog),
        "emoji": catalog.emoji,
        "element": element,
        "damage_mult": base_mult * level_scale,
        "special_ability": catalog.special_ability,
        "rank": beast.rank,
    }


async def _add_inventory(session: AsyncSession, player_id: int, item_type: str, item_id: int, qty: int, quality: str = "normal"):
    from core.utils import add_item_to_inventory
    return await add_item_to_inventory(session, player_id, item_type, item_id, qty, quality)
