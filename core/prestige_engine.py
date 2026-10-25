import logging
from datetime import datetime, timezone
import json
from sqlalchemy import select, delete
from database.models import Player, PrestigeLog, PlayerArtifact, PlayerDaoFragment, PlayerTechnique, TechniqueCatalog
from core.i18n import t

logger = logging.getLogger(__name__)

PRESTIGE_REQ_REALM = 10
PRESTIGE_REQ_SUB_LAYER = 9

def can_prestige(player: Player) -> bool:
    """Verifica se o jogador atende aos requisitos para o Prestige."""
    return player.realm >= PRESTIGE_REQ_REALM and player.sub_layer >= PRESTIGE_REQ_SUB_LAYER

def get_prestige_multiplier(prestige_level: int) -> float:
    """Retorna o multiplicador de CB ganho por Prestige Level (+1% por nível)."""
    return 1.0 + (prestige_level * 0.01)

def get_prestige_title(prestige_level: int, lang: str = "pt") -> str:
    """Retorna o título de prestige."""
    if prestige_level == 0:
        return ""
    if prestige_level >= 10:
        return t(lang, "prestige_title_eternal", level=prestige_level)
    elif prestige_level >= 5:
        return t(lang, "prestige_title_celestial", level=prestige_level)
    else:
        return t(lang, "prestige_title_immortal", level=prestige_level)

async def process_prestige(session, player: Player, retained_technique_id: int | None = None) -> PrestigeLog:
    """
    Processa o renascimento (Prestige).
    - RESET: realm, sub_layer, CB, foundation, golden core, core_essence, qi, qi_capacity, techniques (except 1), incomplete dao fragments.
    - MANTÉM: Spirit Stones, Spirit Jade, Artifacts, Inventory, Cauldrons, Beasts, completed Dao Laws, Prestige Points, Titles.
    - GANHA: +1 Prestige Level, +100 PP.
    """
    if not can_prestige(player):
        raise ValueError("Player does not meet prestige requirements.")

    # ── 轮回 — O CAMINHO RE-DERIVA DO KARMA QUE ATRAVESSA AS VIDAS ──────────
    # PERGUNTA do [jogador] (2026-08-14, main): *"how do I get to the demonic path?
    # My karma is -1000... Even after reborn, I immediately become the rogue
    # path. I can't select my path on 3rd grade up."*
    #
    # Ele não estava a perder nada — era IMPOSSÍVEL. A cadeia, medida:
    #   1. o Caminho cristaliza SOZINHO ao chegar ao reino 3, a partir do karma
    #      daquele instante (`derive_path_from_karma`: >=+250 justo, <=-250
    #      demoníaco, no meio ERRANTE);
    #   2. `set_player_path` é ONE-SHOT — depois disso devolve `path_already_set`;
    #   3. o renascimento reseta reino, stats, pílulas, buffs… e **não tocava no
    #      Caminho**;
    #   4. o único destrancamento é o Rito do Coração-Demônio do TEC-5, que vive
    #      atrás da flag `forbidden_path` — OFF no `main` POR CONSTRUÇÃO;
    #   5. e o Errante é o único caminho SEM gatilho de divergência
    #      ("neutralidade, por definição, nunca está errada"), portanto o jogo
    #      nunca lhe mandava sequer um aviso.
    # ⇒ quem cristalizou Errante numa vida em que o karma andava perto de zero
    # ficava trancado fora de um terço do jogo PARA SEMPRE, sem uma única tela a
    # dizê-lo. Dead-end de Lei §1, e a pergunta dele é a prova.
    #
    # A correção não inventa mecânica nenhuma: o karma **já** atravessa o
    # renascimento de propósito (业力 segue a alma — é canon), e é exatamente
    # ele que a cristalização lê. Renascer passa a RE-DERIVAR o Caminho a partir
    # do karma acumulado. Quem não mudou de vida moral mantém o mesmo caminho;
    # quem passou uma vida inteira a afundar o karma renasce naquilo que se
    # tornou.
    #
    # ⚠️ Corre ANTES do reset do reino (`player.realm = 0` mais abaixo) porque
    # `set_player_path` exige R3+ — aqui o jogador ainda está no reino 10.
    # ⚠️ `allow_recrystallize=True` deixa de ser exclusivo do Rito; a docstring
    # do `path_engine` foi atualizada em vez de ficar a mentir.
    _path_before = getattr(player, "path", None)
    _path_after = None
    try:
        from core.karma_engine import derive_path_from_karma
        from core.path_engine import set_player_path
        _karma_now = int(getattr(player, "karma", 0) or 0)
        _derived = derive_path_from_karma(_karma_now)
        if _derived != _path_before:
            _res = await set_player_path(session, player.telegram_id, _derived,
                                         allow_recrystallize=True)
            if _res.get("ok"):
                _path_after = _derived
                logger.info(
                    "Prestige: path re-derived for %s — %s → %s (karma=%s)",
                    player.telegram_id, _path_before, _derived, _karma_now,
                )
    except Exception:
        logger.warning("prestige: path re-derivation failed for %s",
                       player.telegram_id, exc_info=True)

    # Obter Dao Laws completadas para o log
    stmt_dao = select(PlayerDaoFragment).where(
        PlayerDaoFragment.player_id == player.telegram_id,
        PlayerDaoFragment.is_completed == True
    )
    dao_logs = (await session.execute(stmt_dao)).scalars().all()
    retained_dao_laws_dict = {str(d.dao_law_id): True for d in dao_logs}

    # Remover todas as Dao Laws incompletas (Supreme Laws)
    stmt_dao_del = delete(PlayerDaoFragment).where(
        PlayerDaoFragment.player_id == player.telegram_id,
        PlayerDaoFragment.is_completed == False
    )
    await session.execute(stmt_dao_del)
    # NOTE: 3000 Laws discoveries (PlayerDaoDiscovery) are intentionally KEPT.
    # Knowledge is never lost, but bonuses are realm-gated (min_realm filters
    # in get_dao_laws_bonuses), so a realm 0 player gets zero bonuses until
    # climbing back to realm 5+. Same pattern as completed Supreme Laws.

    # Lógica das Técnicas: reter apenas a técnica selecionada (se houver) e remover o resto
    if retained_technique_id is not None:
        stmt_tech_del = delete(PlayerTechnique).where(
            PlayerTechnique.player_id == player.telegram_id,
            PlayerTechnique.technique_id != retained_technique_id
        )
        await session.execute(stmt_tech_del)
    else:
        # Deletar todas as técnicas
        stmt_tech_del = delete(PlayerTechnique).where(PlayerTechnique.player_id == player.telegram_id)
        await session.execute(stmt_tech_del)

    # Resetar Base do Player
    player.realm = 0
    player.sub_layer = 1
    player.cultivation_base = 0.0
    player.foundation_quality = None
    player.foundation_locked = False
    player.core_quality = None
    player.core_locked = False
    player.core_essence = 0

    # Reset Base Stats to default values to prevent exponential growth across reincarnations
    player.battle_power = 50
    player.soul_strength = 50
    player.perception = 40
    player.luck = 30

    # Resetar medicine resistance (evita herdar resistência da vida passada).
    # H-11 (v13): use a direct DELETE that we can count, so production logs
    # confirm the wipe happened even if reset_medicine_resistance is later
    # patched by another module.
    from database.models import PlayerMedicineResistance
    _med_del = await session.execute(
        delete(PlayerMedicineResistance).where(
            PlayerMedicineResistance.player_id == player.telegram_id
        )
    )
    logger.info(
        "Prestige H-11: medicine resistance wiped for player %s (rows=%s)",
        player.telegram_id, getattr(_med_del, "rowcount", "?")
    )

    # Limpar todos os buffs ativos de pílulas (evita herdar buffs do endgame no realm 0)
    from database.models import PlayerBuff
    await session.execute(delete(PlayerBuff).where(PlayerBuff.player_id == player.telegram_id))

    # O utilizador pediu expressamente para reter Spirit Stones e Artefactos/Inventário
    # Aproveitamos para resetar o limite e a quantidade atual de Qi
    player.qi = 100.0
    # FIX 2026-06-01 ([jogador] report): body tempering's flat +QI_CAP_BONUS_PER_LEVEL
    # per level is BAKED into the stored qi_capacity column (body_tempering_engine
    # perform_tempering). A flat reset to 100 silently wiped it on every rebirth,
    # even though body_tempering_level itself is preserved (D-7 below). That
    # collapsed the cap (player saw ~340k → tiny). Re-establish the tempering
    # FLOOR here; realm-based growth correctly resets to 0 and re-accrues on the
    # re-climb. Honra o contrato D-7 + body_tempering.md ("+200 qi_capacity MANTIDO").
    from core.body_tempering_engine import QI_CAP_BONUS_PER_LEVEL as _QI_CAP_PER_LVL
    _bt_level = int(getattr(player, "body_tempering_level", 0) or 0)
    player.qi_capacity = 100.0 + _bt_level * _QI_CAP_PER_LVL

    # D-7 (DESIGN_DECISIONS_v14): body tempering persists 100% across rebirth.
    # Authentic Wuxia: o corpo lembra-se mesmo quando a alma renasce. Player
    # report 2026-04-30 ([jogador]): "Tava com 30k/100k e fui pra 15 pontos"
    # — perdia in-progress essence ao renascer. Saint admitiu "Nem eu sabia
    # dessa kk". Body tempering é gated por celestial_essence (escasso por
    # design); resetar é punição cruel sem mérito narrativo.
    # body_tempering_level (10/11/12) já era preservado (F-11.5).
    # body_tempering_progress agora também — corpo é continuum.

    # 2026-08-18 (report do [jogador]: "renascer não recupera a energia, o que é
    # estranho"). Estava certo: o renascimento devolve o Qi ao cheio, limpa
    # buffs, cancela meditação — e deixava a energia de alquimia exactamente
    # onde estava, muitas vezes a ZERO. A alma refaz-se e a chama não. Não é
    # exploit: o renascimento custa o reino inteiro, e o tier de Alquimia (que
    # define o tecto) atravessa-o intacto — logo o alquimista renasce com a
    # chama do seu posto, não com a do Aprendiz.
    from core.alchemy_engine import get_alchemy_energy, get_alchemy_tier
    from core.monetization import get_player_vip_level
    try:
        _vip = await get_player_vip_level(session, player.telegram_id)
    except Exception:
        _vip = 0
    _a_tier = await get_alchemy_tier(session, player.telegram_id)
    _, _energy_cap, _ = get_alchemy_energy(player, _vip, _a_tier)
    player.alchemy_energy = _energy_cap
    player.alchemy_energy_updated_at = datetime.now(timezone.utc)

    # Cancelar meditação ativa (evita herdar multiplicador de endgame no realm 0)
    player.is_meditating = False
    player.meditation_type = None
    player.meditation_end = None
    player.meditation_multiplier = 1.0

    # v14.4 D-1b: rebirth resets the `Quebrar a Fundação` cooldown ("30 dias real
    # OU 1 por rebirth — o que vier primeiro"). foundation_break_count is the
    # lifetime stat — it stays. foundation_reroll_used (D-1a /recomeço) is also
    # NOT reset by design — newbie grace is once per cultivator forever.
    player.last_foundation_break_at = None

    # Auto-unequip artifacts that require a realm higher than 0 (post-rebirth)
    from database.models import ArtifactCatalog
    stmt_high_arts = (
        select(PlayerArtifact)
        .join(ArtifactCatalog)
        .where(
            PlayerArtifact.player_id == player.telegram_id,
            PlayerArtifact.is_equipped == True,
            ArtifactCatalog.min_realm > 0,
        )
    )
    high_artifacts = (await session.execute(stmt_high_arts)).scalars().all()
    for art in high_artifacts:
        art.is_equipped = False
        art.slot = None
    unequipped_count = len(high_artifacts)

    # Reset faction membership (player can choose again after reaching Realm 3)
    from database.models import PlayerFaction, PlayerFactionQuest
    await session.execute(delete(PlayerFactionQuest).where(PlayerFactionQuest.player_id == player.telegram_id))
    await session.execute(delete(PlayerFaction).where(PlayerFaction.player_id == player.telegram_id))

    # Ganhas:
    player.prestige_level += 1
    player.prestige_points += 100

    # v14.14c — re-apply permanent Prestige Shop perks (soul echoes etc) AFTER
    # the stat reset block above. Without this, the +5/+5/+5 soul/perception/luck
    # from soul_echo_triad would be wiped on every rebirth, breaking the
    # "permanent" promise (lei §4: pagantes/grinders never lose what they bought).
    from core.prestige_shop_engine import re_apply_persistent_perks
    re_apply_persistent_perks(player)

    # Criar Log
    prestige_log = PrestigeLog(
        player_id=player.telegram_id,
        prestige_level=player.prestige_level,
        retained_technique=retained_technique_id,
        retained_dao_laws=retained_dao_laws_dict
    )
    session.add(prestige_log)
    
    return prestige_log, unequipped_count

async def get_player_techniques(session, telegram_id) -> list[tuple[PlayerTechnique, TechniqueCatalog]]:
    """Gera a lista de técnicas do jogador."""
    stmt = select(PlayerTechnique, TechniqueCatalog).join(
        TechniqueCatalog, PlayerTechnique.technique_id == TechniqueCatalog.id
    ).where(PlayerTechnique.player_id == telegram_id)
    result = await session.execute(stmt)
    return result.all()
