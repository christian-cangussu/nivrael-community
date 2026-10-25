from datetime import date, datetime, timezone
import uuid
from sqlalchemy import BigInteger, Date, Float, Integer, String, Boolean, DateTime, Text, ForeignKey, UUID, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.db import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=True)
    dao_name: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, index=True)

    realm: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    sub_layer: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    cultivation_base: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)

    spirit_root: Mapped[int] = mapped_column(Integer, default=4, nullable=False)  # 0=Heavenly..4=Low

    spirit_stones: Mapped[int] = mapped_column(BigInteger, default=500, nullable=False)
    spirit_jade: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    # Migration 115 (2026-06-12) — monotonic lifetime jade EARNED (never
    # decremented; refunds are spend rollbacks, not income). Feeds Achievement
    # #12 Jade Collector via core.monetization.grant_jade — the old
    # current-balance high-water mark was unreachable for spend-as-you-earn
    # players ([jogador]).
    lifetime_jade_earned: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    qi: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    qi_capacity: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)

    battle_power: Mapped[int] = mapped_column(BigInteger, default=50, nullable=False)
    soul_strength: Mapped[int] = mapped_column(BigInteger, default=50, nullable=False)
    perception: Mapped[int] = mapped_column(BigInteger, default=40, nullable=False)
    luck: Mapped[int] = mapped_column(BigInteger, default=30, nullable=False)

    is_meditating: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    meditation_type: Mapped[str] = mapped_column(String(32), nullable=True)
    meditation_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="pt", nullable=False)
    # 性 O GENERO (Mig 140, 2026-09-07) — "male" | "female" | None.
    # ⚠️ NULL e' um estado LEGITIMO, nao um defeito: os ~248 do beta nascem sem
    # genero e o jogo serve-os inteiros (a figura de costas, 背影). NADA e'
    # gated por esta coluna — em particular o casamento (`dao_partners`), que
    # existe desde antes dela e continua gender-free por desenho.
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True, default=None)
    meditation_multiplier: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    last_online: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    prestige_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prestige_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_title: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unlocked_titles: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)  # extra titles from VIP, BP, etc.
    shadow_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    foundation_quality: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    foundation_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    core_quality: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    core_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    core_essence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    body_tempering_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    body_tempering_progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Sprint 3 (Migration 123) — Mortal Flesh band counter (Pele→Vísceras, 0..7),
    # the R0–R6 body axis. SEPARATE from body_tempering_level (R7+ Nine
    # Transformations) so the bands never collide. Gives durability only (never
    # qi_capacity). Server-gated: only written by the `cultivo_corpo_r0` temper
    # action; the 57 on `main` stay 0 → neutral (body_durability_mult → 1.0).
    mortal_body_level: Mapped[int] = mapped_column(Integer, server_default="0", default=0, nullable=False)
    # Sprint 4 (Migration 124) — Horta 灵田 temper progress toward the NEXT Mortal
    # tier. Harvesting spiritual herbs adds points here; enough points DISCOUNT the
    # qi cost of the next "Temperar a Carne" (the patient path — BC-4/BC-6). NEVER
    # converts to qi/qi_capacity (BC-5). The 57 on `main` stay 0 → neutral.
    mortal_temper_progress: Mapped[int] = mapped_column(Integer, server_default="0", default=0, nullable=False)
    # Sprint 5 (Migration 125) — Caça 狩猎 body-tempering materials (BC-3). Beast
    # expeditions in a `cultivo_corpo_r0` world drop hunt_essence; refining it adds
    # to mortal_temper_progress (a 2nd faucet into the same pipe). Gated + additive;
    # the 57 on `main` stay 0 → neutral.
    hunt_essence: Mapped[int] = mapped_column(Integer, server_default="0", default=0, nullable=False)
    # Sprint 6 (Migration 126) — Ambiental 环境 global cooldown stamp (BC). The 3rd
    # input: tempering the flesh at an extreme-environment SITE (in the player's
    # current continent) adds to mortal_temper_progress, paced by THIS global
    # cooldown (situational + time, no stone cost). Its OWN state (Lei §5) — never
    # shared with any combat/farm cooldown. NULL = never env-tempered. The 57 on
    # `main` stay NULL → neutral; combat never reads it.
    env_last_temper_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Sprint 8 (Migration 127) — Cerimónia-Semente (Breakthrough Trials). Two nullable
    # timestamps, server-gated by `breakthrough_trials` (OFF on main → never read → the
    # 57's realm-ups stay byte-identical). `insight_charge_expires_at`: the 顿悟 charge a
    # near-death fight grants (Sprint 7) that lets Forçar skip its failure risk (BT-4).
    # `breakthrough_setback_until`: the recoverable cooldown after a failed Forçar — the
    # realm-up still happens (Lei §1), only the next Forçar is locked until it expires.
    insight_charge_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    breakthrough_setback_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Sprint 7 (Migration 128) — Combate 顿悟 faucet cooldown. A worthy combat WIN tempers
    # the flesh (+mortal_temper_progress), paced by this stamp. The 顿悟 CHARGE from a near-
    # death win reuses insight_charge_expires_at above. Server-gated (cultivo_corpo_r0 OFF on
    # main → the post-settle hook is a no-op → the 57's duels stay byte-identical).
    last_combat_insight_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # MV-4 (Migration 132) — Corpo Profundo: os 12 MERIDIANOS 经脉. `meridians_opened`
    # = canal aberto -> {opened_at, attempts} ('{}' = nenhum — o estado de todos hoje);
    # `meridian_ritual` = o ritual EM CURSO (NULL = nenhum). Server-gated pela flag
    # per-world `corpo_profundo` (OFF on main → nunca escrito → os 57 byte-idênticos).
    # O bónus por canal folda em body_tempering_engine.body_durability_mult (Alma).
    meridians_opened: Mapped[dict | None] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    meridian_ritual: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    # MV-6 (Migration 134) — O RIVAL com memória (patent-safe: 1 rival por jogador,
    # memória = texto + power scaling). `rival_npc_id` = o NpcCultivator que sobreviveu
    # a você e LEMBRA; `rival_state` JSONB = {defeats, last_defeat_at, taunt_seed,
    # returned, spared, spared_count, continent} (NULL = sem rival). Server-gated pela
    # flag per-world `reputacao_rival` (OFF on main → nunca escrito → 57 byte-idênticos).
    rival_npc_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("npc_cultivators.id", ondelete="SET NULL"), nullable=True, default=None
    )
    rival_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    # ⚔️ O GOLPE PADRÃO (Migration 141) — report do [jogador] 10/09: a técnica que o
    # preenchimento automático da ronda usa quando o jogador não respondeu em
    # 15 s. Antes era SEMPRE `technique_id: 0` (o golpe básico), portanto quem
    # fechava o mini-app lutava a soco e não movia Intenção nem maestria.
    # ⚠️ NULL = golpe básico = o comportamento de hoje. Gated pela flag
    # per-world `golpe_padrao` (OFF no `main` → nunca lido → os 57 byte-idênticos).
    # ⚠️ Uma arte do Caminho Proibido NUNCA entra aqui: ela cobra karma e anos de
    # vida por uso, e um automático não pode cobrar um preço que o jogador não
    # escolheu naquele instante (ver `core/duel_engine.resolve_default_strike`).
    default_technique_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, default=None)
    # 減 P7 (Migration 142) — A REDUÇÃO PROGRESSIVA. Por sistema, o ponto em que
    # está a frase que o explica: ausente (nunca agiu) · "apto" (agiu com
    # sucesso — o SERVIDOR escreve, na transacção da acção) · "recolhido" (o
    # jogador escolheu «Já percebi»). NULL = nada recolhido = a tela de hoje.
    # Dono único: `core/explicacoes.py`. Só escrito com a onda ligada (OFF no
    # `main` → nunca escrito → os 57 byte-idênticos).
    explicacoes: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)

    # MV-7 (Migration 135) — Profissões Wuxia. `profession` = key canônica sem
    # acento ('alquimista' | 'ferreiro' | 'medico'; NULL = sem ofício — os 57
    # intactos). `profession_xp` cresce pelo que o jogador JÁ FAZ (tracker-reuse
    # via track_quest); tiers derivados por thresholds no engine, nunca
    # persistidos. Server-gated pela flag per-world `profissoes` (OFF em main).
    profession: Mapped[str | None] = mapped_column(String(24), nullable=True, default=None)
    profession_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    profession_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    # TEC-2 (Migration 137) — Economia do Pergaminho. `scroll_econ` = o livro do
    # DIA da doação: {"d": "YYYY-MM-DD", "cp": <creditado hoje>} (NULL = nunca
    # doou — o estado de todos hoje). Existe só para o teto diário de
    # contribuição por doação (knob SCR_DONATE_DAILY_CAP): a contribuição de
    # seita NPC não tem tabela de log (sect_contribution_log é da GUILDA).
    # Server-gated pela flag per-world `escassez_scrolls` (OFF em main → nunca
    # escrito → os 57 byte-idênticos).
    scroll_econ: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)

    current_hp: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)  # NULL = full HP

    alchemy_energy: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    alchemy_energy_max: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    alchemy_energy_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    celestial_fragments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # H-14 (v13): tracked on each interaction, used by sects to detect inactives.
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        default=lambda: datetime.now(timezone.utc),
    )

    # Celestial System (Mahayana) — F-11
    celestial_trials_passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    celestial_essence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    celestial_trial_cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    body_transformed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # v14.3 D-6b — Apex Reflection Chamber filler currency. Migration 083.
    # Spent post-launch (currency designed to survive the WIPE per §5.5).
    divine_law_insights: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    apex_chamber_entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # v14.4 D-1 — Foundation system completo. Migration 084.
    # `foundation_reroll_used`: D-1a `/recomeço` one-shot guard, permanent.
    # `foundation_break_count` / `last_foundation_break_at`: D-1b ritual stats + cooldown.
    foundation_reroll_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    foundation_break_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_foundation_break_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # v14.5 — Notifications Pack + Auto-progress Dungeon. Migration 086.
    # State-tracking only — opt-out toggles live in PlayerNotificationPref.
    last_breakthrough_notified_realm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_breakthrough_notified_sub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_alchemy_full_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_progress_dungeon: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # v14.13 MA-47 — Tutorial / onboarding flag. Mini-app welcome modal shows
    # on first launch; toggled True on dismiss/skip. Migration 089 backfills
    # TRUE for existing beta players so they don't see it post-deploy.
    tutorial_seen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # v14.14c — Prestige Shop perks. Read by process_prestige to re-apply soul
    # echoes after stat reset. Migration 090.
    # v15.1 hotfix (2026-05-15): nullable=True so the column add survives rolling
    # deploy without AccessExclusiveLock deadlock vs the live tick query. All
    # callers already do `dict(player.prestige_perks or {})`, tolerating NULL.
    prestige_perks: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, server_default=text("'{}'::jsonb"))

    # v16.0 — World Foundation. The two geographic columns that anchor every
    # subsequent v16 system (sect lineage, path trinity, karma spine, dungeon
    # gating, scroll economy, rivalry events). See `core/continent_engine.py`
    # for the canonical key list and `migrations/100_player_continent.sql`
    # for the schema. DEFAULT 'linghe' migrates all 57+ beta players to the
    # neutral starter continent transparently.
    home_continent: Mapped[str] = mapped_column(String(16), nullable=False, default="linghe", server_default=text("'linghe'"))
    current_continent: Mapped[str] = mapped_column(String(16), nullable=False, default="linghe", server_default=text("'linghe'"), index=True)
    # Onda 4b — Travel cooldown stamp (migration 112). NULL = never travelled.
    # Its OWN state — never shared with any combat/farm cooldown (Lei §5). The
    # travel_engine reads/writes this when the player moves between continents.
    last_travel_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # v16.2 — Path Trinity. Successor to PlayerFaction. NULL = "never picked"
    # (engine resolves to 'rogue' for reads). Migration 102 backfills from
    # existing PlayerFaction rows (celest* → righteous, demon* → demonic).
    # See `core/path_engine.py` for the canonical key list. PlayerFaction
    # table stays intact for backwards-compat until v16.4.
    path: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None, index=True)

    # v16.3 — Karma Spine. Silent stat that DERIVES the Path. At R3 the
    # karma engine reads accumulated karma and crystallizes the Path
    # automatically (Righteous/Demonic/Rogue). Range narrativo [-1000,
    # +1000] — engine clamps on every write. Migration 103 adds with
    # DEFAULT 0 so all 57+ beta players land neutral (Lei §1 + §5).
    karma: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default=text("0"), index=True)

    # v16.4 — Sect-Guild Split. The NPC sect (lore-canon eternal institution)
    # the cultivator was RECRUITED into via affinity — distinct from a player
    # guild (the `sects` table). NULL = unaffiliated (all 57+ beta players
    # land here). FK -> world_sects.id (a v16.1 lineage key). sect_rank walks
    # disciple -> inner -> core -> heir. Membership is NEVER jade-buyable
    # (Lei §4) — only the recruiter encounter grants it. Migration 105.
    sect_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("world_sects.id"), nullable=True, default=None, index=True)
    sect_rank: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    sect_joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    # v16.4c — Sect Library + Ranks. The NPC-sect rank currency, earned by
    # Sect Quests + tribute. SEPARATE from the player-GUILD's contribution
    # (SectMember.contribution_points / sect_contribution_log) — that is the
    # UUID `sects` alliance; this is the String `world_sects` house. The
    # promotion engine reads this against SECT_RANK_THRESHOLDS + realm gates.
    # Migration 109 adds with DEFAULT 0 (neutral for all 57+ players).
    sect_contribution: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default=text("0"))
    # Pedra 2 wave 3 — LIFETIME contribution earned (the RANK ladder reads THIS;
    # `sect_contribution` above is the SPENDABLE balance debited by the Merit
    # Pavilion). Split so spending cosmetic merit NEVER recedes rank progress.
    # Migration 118 backfills earned = sect_contribution (so no existing rank
    # changes). Both rise together on every contribution gain; only the balance
    # falls on a Pavilion purchase. The promotion guard never demotes regardless.
    sect_contribution_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default=text("0"))
    # Pedra 2 — Master-Disciple bond 师徒. The Wuxia name of the Elder who
    # courted this cultivator into their Cultivation Sect (cosmetic identity only;
    # the bond's mechanical bonus is DEFERRED to the wipe §4). NULL for every
    # existing member — display falls back to a deterministic name seeded by
    # (sect_id, telegram_id). Persisted on join. Migration 117.
    sect_master_name: Mapped[str | None] = mapped_column(String(48), nullable=True, default=None)
    # Track A item 5 — Raízes (灵根 composition axis). The ORTHOGONAL partner to
    # `spirit_root` (above, which is QUALITY/purity only). Holds WHICH Wuxing
    # elements {metal/wood/water/fire/earth} + an optional rare variant
    # {lightning/ice/wind/dark/chaos/space/time} the root carries, as a JSONB array
    # of language-neutral keys (e.g. ["fire","earth"]). DISCLOSURE-ONLY this wave —
    # nothing in combat/cultivation/alchemy reads it; the elemental gating + Wuxing
    # cycle are Track B (wipe). NULL for every existing player; derived
    # deterministically per telegram_id (core.root_engine) at birth + via an
    # idempotent startup backfill. Migration 120.
    root_elements: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    # Track A (B4) — Lifespan 寿命 (the mortality clock). DISCLOSURE-ONLY this wave:
    # the per-realm ceiling is DERIVED (core.lifespan_engine.REALM_LIFESPAN), NOT a
    # column. These two MUTABLE counters stay 0 for everyone now — nothing ages, dies,
    # or reads them in combat/cultivation/alchemy/scheduler. `age_years` = longevity
    # already consumed (the World Pulse ageing tick lights up at the WIPE);
    # `lifespan_bonus_years` = extensions from future longevity pills/treasures (the
    # pill economy is wipe-bound, Lei §4). NOT NULL DEFAULT 0 — every existing beta
    # player backfills to 0 neutrally. Migration 121. See GameDesign/lifespan_design.md.
    age_years: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    lifespan_bonus_years: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    # Sprint 1 — Raça (KEYSTONE A): the 3rd birth axis, ORTHOGONAL to spirit_root
    # (quality) and root_elements (Wuxing composition). One of 6 language-neutral
    # keys derived per telegram_id in core.race_engine (humano/celeste/primordial/
    # tita/demonio/draconato). DISCLOSURE-ONLY this wave — NOTHING in combat/
    # cultivation/alchemy/travel reads it (mechanical depth is Track B, wipe-bound).
    # ⚠️ DEFAULT NULL + NO backfill (unlike root_elements): the 57 beta players on
    # `main` stay NULL forever; the ONLY write is at the BIRTH of a NEW character in
    # a world where the `racas` flag is ON. Migration 122.
    race: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)


class KarmaLog(Base):
    """v16.3 — Karma audit log.

    Every karma-mutating event writes a row here. Consumed by:
        • KarmaModal recent events display (last 10)
        • Chat /karma history sub-view
        • Future v16.10 Rivalry Events sect-level karma aggregates
        • Achievement #27 Karmic Devotee (target: 1000 lifetime entries)

    Schema mirrors the one in migrations/103_karma_spine.sql exactly.
    Foreign key CASCADE: when player row is dropped (wipe), karma_log
    cleans up automatically.
    """

    __tablename__ = "karma_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    new_value: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class WorldSect(Base):
    """v16.4 — NPC Sect (eternal lore-canon institution).

    The 9 Great Houses (azure_cloud .. abyssal_depths). DISTINCT from a
    player guild (the `sects` table). Single source of truth lives in
    `core.world_sects_engine.WORLD_SECT_META`; this table is seeded from it
    (`database.seeds.world_sects_seeds`) so `Player.sect_id` and the
    recruiter-pending rows have valid FK targets. `signature_techs` is
    populated by v16.4c (Sect Library). Schema mirrors
    migrations/105_sect_guild_split.sql exactly.
    """

    __tablename__ = "world_sects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # == v16.1 lineage_key
    name_key: Mapped[str] = mapped_column(String(64), nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)  # righteous | demonic
    continent_key: Mapped[str] = mapped_column(String(16), nullable=False)
    rival_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("world_sects.id"), nullable=True)
    philosophy_key: Mapped[str] = mapped_column(String(96), nullable=False)
    bonuses: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    signature_techs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    # World Pulse Fase 1 — 5 hidden personality scalars (Crusader Kings souls,
    # 0..1) seeded per-sect from WORLD_SECT_SOUL + dynamic sim state. `strength`
    # is an ABSTRACT new number that does NOT buff any player (Lei §5) — it only
    # moves the world narrative (and, future, scales the Guild blessing §4).
    # Schema mirrors migrations/116_world_pulse.sql exactly.
    ambition: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default=text("0.5"))
    honor: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default=text("0.5"))
    greed: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default=text("0.5"))
    zeal: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default=text("0.5"))
    aggression: Mapped[float] = mapped_column(Float, nullable=False, default=0.5, server_default=text("0.5"))
    strength: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default=text("100"))
    momentum: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    # Fase A3 do Motor de Mundo Vivo (Mig 139) — {sect_id: intensidade}: quem me
    # deve, e quanto. ESTADO DE RUNTIME como `strength`/`momentum`: nenhum Pass
    # do seed pode escrever aqui, ou um deploy zerava a memória do mundo.
    grudges: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    last_action: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    last_pulse_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class WorldSectRecruiterPending(Base):
    """v16.4 — A pending Recruiter encounter (the Elder on the pine tree).

    Inserted by the hourly `world_sect_recruiter_tick` scheduler job when a
    player's affinity for an NPC sect crosses the threshold (75). One active
    encounter per player per week. Resolved by accept (-> join) / decline /
    expire. Schema mirrors migrations/105_sect_guild_split.sql exactly.
    """

    __tablename__ = "world_sect_recruiter_pending"
    __table_args__ = (
        UniqueConstraint("player_id", "sect_id", "expires_at", name="uq_recruiter_pending"),
        Index("idx_recruiter_player", "player_id", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False
    )
    sect_id: Mapped[str] = mapped_column(String(32), ForeignKey("world_sects.id"), nullable=False)
    affinity_score: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class WorldSectTrial(Base):
    """v16.4b — A Sect Recruitment trial attempt (duel vs the house Elder).

    Created when a cultivator accepts a recruiter encounter and faces the
    Elder. ``status`` walks pending → won | lost. ``duel_id`` links the
    turn-based trial duel (reuses ``duel_engine``); the settle path resolves
    this row from that duel. On a loss, ``cooldown_until`` gates the retry
    (never a soft-lock — Lei §1). ``pending_id`` references the
    ``world_sect_recruiter_pending`` row that invited the cultivator so a win
    can mark the encounter accepted. Schema mirrors
    migrations/108_world_sect_trial.sql exactly.
    """

    __tablename__ = "world_sect_trial"
    __table_args__ = (
        Index("idx_sect_trial_player", "player_id", "sect_id", "created_at"),
        Index("idx_sect_trial_duel", "duel_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False
    )
    sect_id: Mapped[str] = mapped_column(String(32), ForeignKey("world_sects.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending | won | lost
    duel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("duel_sessions.id"), nullable=True
    )
    pending_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    affinity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NpcCultivator(Base):
    """Onda 3 — A persistent, autonomous NPC cultivator (the world population).

    Generated from an ANONYMIZED, READ-ONLY snapshot of a real player's PUBLIC
    combat state (``origin='echo'``) or as a synthetic bootstrap cultivator so
    the world is never born empty (``origin='seed'``). Carries continent + sect
    + path + tier + karma + a rehydratable combat ``loadout`` (the v16.7 Três
    Tesouros fighter dict — combat_profile + hp + bp + qi_capacity + techniques),
    so a player can FIGHT it via ``start_duel_pve`` (pve_source='npc_cultivator')
    using the SAME combat model — fair by construction.

    NO PII (Lei §5): no telegram_id, no real dao_name, no live FK to the source
    Player. ``source_hash`` is a one-way, non-reversible hash of the source
    telegram_id used ONLY for idempotent echo upsert (one echo per source);
    never surfaced to any client. Always rendered with an honest NPC chip
    (Lei §1) — never disguised as a real player. Schema mirrors
    migrations/110_npc_cultivators.sql exactly.
    """

    __tablename__ = "npc_cultivators"
    __table_args__ = (
        Index("idx_npc_cult_realm", "realm"),
        Index("idx_npc_cult_power", "power"),
        # One anonymized echo per source player (mirrors migration 110 so
        # create_all and the migration agree regardless of apply-order).
        Index("uq_npc_cult_source", "source_hash", unique=True,
              postgresql_where=text("source_hash IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(48), nullable=False)
    realm: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sub_layer: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    continent_key: Mapped[str] = mapped_column(
        String(16), nullable=False, default="linghe", server_default=text("'linghe'")
    )
    sect_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("world_sects.id"), nullable=True, default=None)
    sect_rank: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    path: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    karma: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    power: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    loadout: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active | ascended | fallen
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="seed")  # seed | echo
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class HeavensWhisperLog(Base):
    """Onda 3 — Heaven's Whispers global narrative feed (the world breathing).

    A read-only, atmospheric world-event log: NPC ascension, beast tide, demonic
    intrusion, sect recruiting, ruin discovered. The mini-app Whispers feed reads
    recent rows; the scheduler delivery job picks relevant recent rows and
    ``notify(kind='whisper')``s a capped, opted-in, cooldowned subset of players
    (anti-churn, Lei §1). Pure cosmetic/atmospheric — zero balance. Schema
    mirrors migrations/110_npc_cultivators.sql exactly.
    """

    __tablename__ = "heavens_whisper_log"
    __table_args__ = (
        Index("idx_heavens_whisper_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    theme: Mapped[str] = mapped_column(String(32), nullable=False)
    title_key: Mapped[str] = mapped_column(String(96), nullable=False)
    body_key: Mapped[str] = mapped_column(String(96), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    continent_key: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    sect_id: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    icon: Mapped[str] = mapped_column(String(16), nullable=False, default="🌌")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


class Bounty(Base):
    """Onda 4a — a world-issued Bounty Board contract on a dark-karma NPC.

    A bounty names a single persistent ``NpcCultivator`` of dark karma
    (``karma <= BOUNTY_TARGET_MAX_KARMA``) and pays ONCE: the first hunter who
    beats the named target via the SAME npc_cultivator duel claims it
    (``status`` open -> claimed, ``claimed_by`` + ``claimed_at``). The NPC row
    is NEVER mutated — it stays active and can be re-targeted by a fresh
    contract once this one expires. A partial UNIQUE index keeps at most one
    OPEN bounty per target (idempotent refill, one-duel-one-bounty). Additive +
    wipe-safe (Lei §5). Schema mirrors migrations/111_bounties.sql exactly.
    """

    __tablename__ = "bounties"
    __table_args__ = (
        Index("idx_bounty_status", "status"),
        Index("idx_bounty_expires", "expires_at"),
        # At most one OPEN bounty per target NPC (mirrors migration 111 so
        # create_all and the migration agree regardless of apply-order).
        Index("uq_bounty_open_npc", "npc_id", unique=True,
              postgresql_where=text("status = 'open'")),
        # Player-posted contracts (Track A item 3 / migration 119): the post path
        # counts a poster's OPEN bounties (anti-grief cap) and the board splits
        # the two origins.
        Index("idx_bounty_posted_by", "posted_by",
              postgresql_where=text("posted_by IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    npc_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("npc_cultivators.id", ondelete="CASCADE"), nullable=False
    )
    continent_key: Mapped[str] = mapped_column(
        String(16), nullable=False, default="linghe", server_default=text("'linghe'")
    )
    realm: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    karma: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_stones: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open | claimed | expired
    claimed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id"), nullable=True, default=None
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    # Track A item 3 — origin of the contract. NULL = world-issued (Onda 4a /
    # World Pulse); set = posted by this player ("colocar a cabeça a prêmio").
    # Additive + wipe-safe (Lei §5); mirrors migrations/119_player_bounties.sql.
    posted_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id"), nullable=True, default=None
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


class WorldChronicle(Base):
    """World Pulse Fase 1 — "Os Registos Celestiais" 天记 (the living world log).

    An APPEND-ONLY chronicle of what the world did on its own: every World Pulse
    beat (a sect recruiting, fortifying, raiding a rival, claiming a node, seeking
    an inheritance, fracturing) writes one row, and any future world event can too.
    ``text_key`` + ``params`` are resolved server-side PER the reader's language
    (the {sect}/{rival}/{continent} names are merged in at render time, so params
    stay language-neutral — same idiom as heavens_whisper_log). Pure
    cosmetic/atmospheric — ZERO balance, wipe-safe. It is also the ready memory
    corpus for the future LLM Dao Celestial (§6 Camada B). Schema mirrors
    migrations/116_world_pulse.sql exactly.
    """

    __tablename__ = "world_chronicle"
    __table_args__ = (
        Index("idx_world_chronicle_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    continent_key: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    sect_id: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    text_key: Mapped[str] = mapped_column(String(96), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))


class WorldEvent(Base):
    """MV-2 Mundo Vivo v2 — Tiandao Director: um evento celestial com LUGAR
    (continent_key) + TIMER (expires_at) + RESOLUÇÃO (state) + consequência.

    Tipos da Onda 1 (Lei §3 — profundidade > variedade): ``beast_tide`` (goal =
    N vitórias PvE de qualquer jogador NO continente; contida → recompensa aos
    contribuintes; ignorada → estrada fechada = travel +50% derivado do próprio
    row expirado) e ``meteor`` (POI de colheita, cooldown 6h/jogador via
    ``payload["miners"]``; expira sozinho, sem punição). Só existe conteúdo em
    mundos com a flag ``tiandao_director`` ON — main nunca escreve aqui.
    Schema mirrors migrations/130_world_events.sql exactly.
    """

    __tablename__ = "world_events"
    __table_args__ = (
        Index("idx_world_events_state", "state", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    continent_key: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default=text("'active'")
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    goal: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


class RegionState(Base):
    """MV-3 Mundo Vivo v2 — Estados Regionais: o estado VIVO de um continente
    (``prospera`` default · ``tensa`` maré ativa · ``sitiada`` maré ignorada ·
    ``festival`` meteoro colhido/maré contida), com overrides mecânicos que o
    jogador sente (preços do mercado local, risco de explore, densidade de qi
    no cultivo). Eventos do MV-2 são a CAUSA; o estado é o EFEITO persistente.

    Transições SÓ no World Pulse de 6h (``sync_region_states`` em
    core/region_state_engine.py — mesmo passo faz o decay, lição sect_war);
    as 5 rows são seedadas lazy pelo próprio sync (upsert idempotente, sem
    seed runner novo). Row ausente lê-se como 'prospera'. Só existe conteúdo
    em mundos com a flag ``estados_regionais`` ON — main nunca escreve aqui.
    Schema mirrors migrations/131_region_states.sql exactly.
    """

    __tablename__ = "region_states"

    continent_key: Mapped[str] = mapped_column(String(16), primary_key=True)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="prospera", server_default=text("'prospera'")
    )
    since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))


class StoryletCatalog(Base):
    """MV-5 Mundo Vivo v2 — Quests VIVAS (storylets/QBN): um pedaço de história
    com ``requirements`` JSONB declarativo (continent / region_state /
    world_event / karma_min-max / realm_min-max / path / meridians_min / flag —
    todos opcionais, AND entre presentes) que só é OFERECIDO quando o mundo o
    torna verdadeiro. ``objective_type`` REUSA os trackers das quests (lição
    MV-1 — nunca objetivo órfão); ``reward`` = pedras/itens nativos/karma,
    NUNCA técnica (Lei §12) nem jade. Nomes/diálogos server-resolved via chat
    locales (``sty_<key>_name/_desc/_d1/_d2`` — convenção, sem coluna).
    Seed-able (database/seeds/storylet_seeds.py), wipe-safe.
    Schema mirrors migrations/133_storylets.sql exactly.
    """

    __tablename__ = "storylet_catalog"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    giver_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="npc_cultivator", server_default=text("'npc_cultivator'")
    )
    emoji: Mapped[str] = mapped_column(String(8), nullable=False, default="📜", server_default=text("'📜'"))
    requirements: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    objective_type: Mapped[str] = mapped_column(String(32), nullable=False)
    objective_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    reward: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    expires_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=48, server_default=text("48"))
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default=text("10"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))


class PlayerStorylet(Base):
    """MV-5 — o estado de um storylet por jogador: ``offered`` → ``accepted``
    → ``done`` (ou ``declined`` / ``expired``). ``context`` JSONB = onde/quando
    a quest nasceu (continente, estado regional, evento, nome do giver — a
    quest LEMBRA de onde nasceu). Expiry é LAZY (padrão
    world_sect_recruiter_pending): ``expires_at`` filtrado na leitura + flip
    honesto em ``sync_player_storylets``; storylet COMPLETA (progress ≥ count)
    NUNCA expira (Lei §1 — a recompensa espera). Só existe conteúdo em mundos
    com a flag ``quests_vivas`` ON — main nunca escreve aqui.
    Schema mirrors migrations/133_storylets.sql exactly.
    """

    __tablename__ = "player_storylets"
    __table_args__ = (
        Index("idx_player_storylets_player", "player_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False
    )
    storylet_key: Mapped[str] = mapped_column(String(48), ForeignKey("storylet_catalog.key"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="offered", server_default=text("'offered'")
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    offered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


class PlayerRegionRep(Base):
    """MV-6 — a memória do LUGAR sobre o jogador: 1 INT por (jogador,
    continente), clamp [-100, +100]. Sobe com o que você FAZ ali (storylet
    concluído +3 · bounty caçado +2 · maré contida +2 · cultivador local
    vencido +1 com cap diário) e decai 1/semana RUMO A ZERO nos continentes
    onde você não está (fama esvai, rancor cicatriza — Lei §1, nunca um poço
    eterno). ``payload`` JSONB = contadores auxiliares ({day, wins} do cap
    diário, last_decay) — NUNCA a verdade do rep. Só existe conteúdo em mundos
    com a flag ``reputacao_rival`` ON — main nunca escreve aqui.
    Schema mirrors migrations/134_reputation_rival.sql exactly.
    """

    __tablename__ = "player_region_rep"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    continent_key: Mapped[str] = mapped_column(String(16), primary_key=True)
    rep: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlayerExploration(Base):
    """Onda 5 (Fase 1) — light per-player STATE for the additive Reinos
    Exploráveis loop. A player has AT MOST one active expedition (PK =
    player_id). It tracks the continent being explored, the current ``depth``,
    the in-flight loot ``bag`` (same JSONB shape as the dungeon expedition bag —
    materials only, NEVER techniques, Lei §5), the expedition's OWN cooldown
    stamp ``last_explore_at`` (NEVER shared with ``PlayerNPCCooldown``'s
    ``last_cultivator_fight`` / farm — Lei §5), and ``started_at``.

    The node map + themes + loot pools live in the ENGINE
    (``core/exploration_engine.py``), NOT the DB — the whole map is wipe-safe.
    "Safe return" banks the bag and resets depth/bag; dying deep loses 90% of
    the bag and resets the expedition. Additive + wipe-safe (Lei §5). Schema
    mirrors migrations/113_player_exploration.sql exactly.
    """

    __tablename__ = "player_exploration"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    continent_key: Mapped[str] = mapped_column(
        String(16), nullable=False, default="linghe", server_default=text("'linghe'")
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    bag: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    last_explore_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class FormationCatalog(Base):
    """Onda 5 (Fase 2) — the craftable Matrizes/Formações 阵法 catalog
    (SEED-able content — database/seeds/formation_seeds.py upserts it, so the
    catalog is wipe-safe and needs no migration to evolve). ``key`` is the
    stable i18n slug (``formation_name_<key>`` / ``formation_desc_<key>``).
    ``effect_type`` deliberately reuses the EXISTING PlayerBuff vocabulary
    (bp_boost / defense_boost / qi_regen_boost / dao_fragment_chance /
    perception_boost) plus ONE new exploration consumer ``explore_protection``
    — activating a Formação "on the body" creates a plain PlayerBuff row, NO
    parallel buff system (Lei §3). ``recipe`` JSONB mirrors the ForgeRecipe /
    PillCatalog material convention: {"stones": int, "herbs": [{"herb_id",
    "qty"}], "ores": [{"ore_id", "qty"}]}. Schema mirrors
    migrations/114_cavern_formations.sql exactly."""

    __tablename__ = "formation_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🔯", nullable=False, server_default=text("'🔯'"))
    effect_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effect_value: Mapped[float] = mapped_column(Float, default=1.0, nullable=False, server_default=text("1.0"))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False, server_default=text("60"))
    tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default=text("1"))
    min_realm: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default=text("0"))
    recipe: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))


class PlayerFormation(Base):
    """Onda 5 (Fase 2) — crafted-but-not-yet-activated Formações (the player's
    formation pouch). Composite PK like PlayerDaoFragment."""

    __tablename__ = "player_formations"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    formation_id: Mapped[int] = mapped_column(Integer, ForeignKey("formation_catalog.id"), primary_key=True)
    qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default=text("0"))
    # 印记 Marca do Traçado (Mig 138) — ativações DESTA formação NO CORPO. A
    # caverna não conta de propósito: a escolha corpo-vs-caverna tem de doer.
    # A row sobrevive a `qty = 0` quando isto é > 0 (senão o bolso vazio
    # apagaria a maestria — ver `formation_engine._consume_one`).
    body_uses: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default=text("0"))


class PlayerCavern(Base):
    """Onda 5 (Fase 2) — the Personal Cavern 洞府, ONE per player (PK =
    player_id). Idle qi accrues from ``last_claimed_at`` (capped at
    CAVERN_CAP_HOURS in core/cavern_engine.py, scaled to realm — conservative,
    a retention net, NEVER pay-to-win — Lei §4/§5). The Formação slot
    (``active_formation_id`` + the ``formation_set_at``..``formation_expires_at``
    window) boosts the idle yield (qi_regen_boost) or grants Dao-fragment
    comprehension (dao_fragment_chance). Schema mirrors
    migrations/114_cavern_formations.sql exactly."""

    __tablename__ = "player_cavern"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    continent_key: Mapped[str] = mapped_column(
        String(16), nullable=False, default="linghe", server_default=text("'linghe'")
    )
    established_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        nullable=False, server_default=text("now()")
    )
    last_claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        nullable=False, server_default=text("now()")
    )
    total_qi_claimed: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, server_default=text("0"))
    active_formation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("formation_catalog.id"), nullable=True, default=None
    )
    formation_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    formation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


class PlayerGardenPlot(Base):
    """Sprint 4 (Migration 124) — a plot in the player's Horta 灵田 (Spiritual
    Field). Composite PK (player_id, slot_index): a fixed grid of GARDEN_PLOTS
    slots. herb_key NULL = empty; planted_at NULL = empty. The herb matures by
    timestamp (now − planted_at ≥ GARDEN_HERBS[herb].grow_seconds, in
    core/garden_engine.py — NO per-player job). Harvest grants Mortal temper
    progress (never qi/qi_capacity — BC-5). Per-world isolation via the routed
    session (no world_key — mirrors player_cavern). Schema = migration 124."""

    __tablename__ = "player_garden_plots"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    slot_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    herb_key: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    planted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


class HerbCatalog(Base):
    __tablename__ = "herbs_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    base_price: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🌿", nullable=False)


class PillCatalog(Base):
    __tablename__ = "pills_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    ingredients: Mapped[dict] = mapped_column(JSONB, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    effect_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effect_value: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="💊", nullable=False)
    min_realm: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    required_alchemy_tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CauldronCatalog(Base):
    __tablename__ = "cauldrons_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    grade: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    success_bonus: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    slots: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_durability: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    base_price: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="⚗️", nullable=False)


class PlayerInventory(Base):
    __tablename__ = "player_inventory"
    __table_args__ = (
        UniqueConstraint("player_id", "item_type", "item_id", "quality", name="uq_player_inventory"),
        Index("idx_inventory_player_type_item", "player_id", "item_type", "item_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(16), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    quality: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)


class ArtifactCatalog(Base):
    __tablename__ = "artifacts_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # weapon, armor, etc
    grade: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    base_stats: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🗡️", nullable=False)
    min_realm: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PlayerArtifact(Base):
    __tablename__ = "player_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    catalog_id: Mapped[int] = mapped_column(Integer, ForeignKey("artifacts_catalog.id"), nullable=False)
    grade: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    slot: Mapped[str] = mapped_column(String(32), nullable=True)
    is_equipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enchant_rune: Mapped[str] = mapped_column(String(64), nullable=True)
    has_spirit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    spirit_name: Mapped[str] = mapped_column(String(64), nullable=True)
    custom_stats: Mapped[dict] = mapped_column(JSONB, nullable=True)
    # H-8 (v13): manual lock skips item from bulk dismantle.
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class OreCatalog(Base):
    __tablename__ = "ores_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🪨", nullable=False)


class PlayerOre(Base):
    __tablename__ = "player_ores"
    __table_args__ = (UniqueConstraint("player_id", "ore_id", name="uq_player_ore"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    ore_id: Mapped[int] = mapped_column(Integer, ForeignKey("ores_catalog.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PlayerCauldron(Base):
    __tablename__ = "player_cauldrons"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    cauldron_id: Mapped[int] = mapped_column(Integer, ForeignKey("cauldrons_catalog.id"), nullable=False)
    is_equipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    durability: Mapped[int] = mapped_column(Integer, default=100, nullable=False)


class PlayerBuff(Base):
    __tablename__ = "player_buffs"
    __table_args__ = (
        Index("idx_player_buff_expires", "expires_at", postgresql_where="expires_at IS NOT NULL"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    buff_type: Mapped[str] = mapped_column(String(32), nullable=False)
    buff_value: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # v14.5 N-10 — flagged once the pre-expiry DM has been sent. Migration 086.
    expiry_notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class MarketplaceListing(Base):
    __tablename__ = "marketplace_listings"
    __table_args__ = (
        Index("idx_marketplace_active", "is_sold", "expires_at", postgresql_where="is_sold = false"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=True, index=True)  # None = NPC/system listing
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    item_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_auction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_bid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    highest_bidder: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_sold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class P2PTrade(Base):
    __tablename__ = "p2p_trades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    initiator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    offer_items: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    request_items: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    initiator_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    target_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending, completed, cancelled, expired
    initiator_msg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_msg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_player: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=True, index=True)
    to_player: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # buy, auction, trade, fee
    item_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tax_paid: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class Tribulation(Base):
    __tablename__ = "tribulations"
    __table_args__ = (
        Index("idx_tribulation_pending", "player_id", "status", postgresql_where="status = 'pending'"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    realm: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending, in_progress, completed, failed, expired
    strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)  # resist, dodge, absorb
    rounds_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rounds_survived: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)  # perfect, success, failure_light, failure_grave
    tribulation_type: Mapped[str] = mapped_column(String(32), default="thunder", nullable=False)
    phases_completed: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # v14.5 Q-4 — flagged once the cooldown-expired DM has been sent. Migration 086.
    cooldown_notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Sect(Base):
    __tablename__ = "sects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    master_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_members: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    spirit_stones: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    
    # Buildings
    training_lvl: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    herb_garden_lvl: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forge_lvl: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    library_lvl: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    defense_lvl: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    spirit_vein_lvl: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    group_link: Mapped[str | None] = mapped_column(String(256), nullable=True)
    bulletin: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # v14.2 D-3a — /decreto_supremo (24h sect-wide announcement, master only).
    # Distinct from bulletin (permanent) — decree expires after 24h.
    decree_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    decree_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decree_author_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # v14.2 D-3b — /passar_tocha ritual.
    # last_torch_passed_at: enforces 30-day cooldown.
    # pending_torch_to_id + pending_torch_at: single in-flight consent slot.
    last_torch_passed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_torch_to_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pending_torch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # v16.1 — Sect Lineage. Nullable: sects existentes têm ~30 dias para
    # escolher (chooser no SectTab). lineage_key validado via
    # core.sect_lineage_engine.LINEAGE_KEYS. Irreversível em v16.1.
    lineage_key: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    lineage_chosen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# v16.4 — Sect-Guild Split (lexical rename only, zero schema change).
# In Wuxia canon a "Sect" is an eternal NPC institution (see WorldSect);
# player-created groups are "Guilds". The `sects` table IS the player guild —
# the user-facing language (mini-app + chat) now calls it a Guild/Guilda.
# This alias lets new code read `Guild` while every existing import of `Sect`
# keeps working. No table/column/command renamed — 57 players lose nothing.
Guild = Sect


class SectMember(Base):
    __tablename__ = "sect_members"
    __table_args__ = (
        Index("idx_sect_member_sect_rank", "sect_id", "rank"),
    )

    sect_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sects.id", ondelete="CASCADE"), nullable=False)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True)
    rank: Mapped[str] = mapped_column(String(16), default="member", nullable=False) # master, elder, member
    contribution_points: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class SectBuildingLog(Base):
    __tablename__ = "sect_buildings_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sect_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sects.id", ondelete="CASCADE"), nullable=False, index=True)
    building: Mapped[str] = mapped_column(String(32), nullable=False)
    old_level: Mapped[int] = mapped_column(Integer, nullable=False)
    new_level: Mapped[int] = mapped_column(Integer, nullable=False)
    upgraded_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False)
    cost: Mapped[int] = mapped_column(BigInteger, nullable=False)
    upgraded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class SectTerritory(Base):
    __tablename__ = "sect_territories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sect_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sects.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    bonus_stones: Mapped[int] = mapped_column(BigInteger, default=1000, nullable=False)
    bonus_cb: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SectWarLog(Base):
    __tablename__ = "sect_war_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attacker_sect: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sects.id", ondelete="CASCADE"), nullable=False, index=True)
    defender_sect: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sects.id", ondelete="CASCADE"), nullable=False, index=True)
    winner_sect: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sects.id", ondelete="CASCADE"), nullable=True)
    territory_id: Mapped[int] = mapped_column(Integer, ForeignKey("sect_territories.id", ondelete="CASCADE"), nullable=False)
    war_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class SectWarState(Base):
    __tablename__ = "sect_war_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    participating_sects: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    attacks: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    attacked_players: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    sect_names: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class CombatLog(Base):
    __tablename__ = "combat_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attacker_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    defender_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # sparring, arena, sect_war
    winner_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=True)
    rounds_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    spirit_stones_reward: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    wager_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    wager_winner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class ArenaRanking(Base):
    __tablename__ = "arena_rankings"
    __table_args__ = (
        Index("idx_arena_ranking_season_elo", "season", text("elo_points DESC")),
    )

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    elo_points: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_combat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ArenaQueue(Base):
    """v15.1.5 — DB-backed arena matchmaking queue.

    Replaces the legacy `context.bot_data["arena_queue"]` chat-only list so
    both surfaces (chat handler + mini-app webserver) can share a single
    pool. One row per player while they are waiting / matched; rows are
    flagged 'expired' on timeout but kept around for short-term audit.
    """

    __tablename__ = "arena_queue"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    elo: Mapped[int] = mapped_column(Integer, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # waiting | matched | expired
    status: Mapped[str] = mapped_column(String(16), default="waiting", nullable=False)
    duel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TechniqueCatalog(Base):
    __tablename__ = "techniques_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    element: Mapped[str] = mapped_column(String(32), nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="⚔️", nullable=False)
    effect_type: Mapped[str] = mapped_column(String(32), nullable=False)  # evasion, damage_mult, damage_reduce, dodge, armor_ignore, cb_boost, qi_regen_boost, hp_regen_boost, soul_boost, perception_boost, luck_boost
    effect_value: Mapped[float] = mapped_column(Float, nullable=False)
    effect_round: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 = all rounds
    req_realm: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    req_spirit_root: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_dao_law_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("dao_laws_catalog.id"), nullable=True)
    required_dao_insight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tech_type: Mapped[str] = mapped_column(String(16), default="combat", nullable=False)  # combat, meditation, interior
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # v15.1 — qi consumption per technique activation in turn-based duels.
    # Tier guideline: common 10-15, rare 25-40, legendary 50-80, faction 30-60.
    # Hotfix 2026-05-15: nullable=True for rolling-deploy safety; seed runner
    # backfills concrete tiered values from combat_seeds.QI_COSTS on startup
    # so the duel engine always reads a real number (also tolerates None
    # defensively via `int(tech.get("qi_cost", 10) or 10)`).
    qi_cost: Mapped[int | None] = mapped_column(Integer, default=10, nullable=True)
    # v15.2 — intent affinity (sword|fist|body|dao|killing). NULL for
    # non-combat techs (meditation/interior). Drives the duel matchup matrix.
    intent_affinity: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    # v16.4c — Sect Library. NULL ⇒ an ordinary technique (drops/scrolls as
    # today). A world_sects.id ⇒ a HOUSE SIGNATURE art: learnable only via the
    # Sect Library (rank-gated, no scroll), and EXCLUDED from drop/scroll/
    # learnable pools so it never collides with the live scroll economy the 57
    # paying players own (Lei §5; the "Library = primary source" switch is the
    # wipe's job, v16.5). Migration 109.
    sect_key: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    # TEC-1 — Biblioteca da Seita (Migration 136). library_tier = the house
    # shelf (1 Externa / 2 Interna / 3 Núcleo); NULL = outside the shelf model
    # (ordinary techs AND the v16.4c per-rank arts 500-544, untouched).
    # library_cp_cost = contribution (Merit Pavilion BALANCE) to unlock; the
    # whole model only bites where the per-world flag `biblioteca_seitas` is ON
    # (core/sect_library_engine.py) — main stays byte-identical.
    library_tier: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    library_cp_cost: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)


class DuelSession(Base):
    """v15.1 — Turn-based duel state machine.

    States:
      waiting_actions → both players choose technique + stance per round
      resolving       → server resolves the round (transient, set then back to waiting_actions or finished)
      finished        → winner_id set, resolved_at stamped
      forfeited       → loser forfeited
      expired         → no action submitted within window
    """

    __tablename__ = "duel_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attacker_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True
    )
    # v15.1.4 — defender_id is NULL for PvE duels (NPC Hunt, Dungeon Boss).
    # PvP duels still populate it. The settle dispatcher uses pve_source
    # to route, not defender_id presence — but the FK + nullable shift is
    # what allows the row to exist without a defender player.
    defender_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=True, index=True
    )
    state: Mapped[str] = mapped_column(String(24), default="waiting_actions", nullable=False)
    round_idx: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_rounds: Mapped[int] = mapped_column(Integer, default=9, nullable=False)
    # v15.1.5 hotfix — BigInteger for end-game BP/qi headroom. Tang
    # (BP=2.98B) overflowed the int32 ceiling on bp_a snapshot. Same
    # widening for combat_qi_* since pool = 20% × qi_capacity and
    # end-game qi_capacity can exceed int32 too. Migration 096.
    combat_qi_a: Mapped[int] = mapped_column(BigInteger, nullable=False)
    combat_qi_b: Mapped[int] = mapped_column(BigInteger, nullable=False)
    combat_qi_a_max: Mapped[int] = mapped_column(BigInteger, nullable=False)
    combat_qi_b_max: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hp_a: Mapped[float] = mapped_column(Float, nullable=False)
    hp_b: Mapped[float] = mapped_column(Float, nullable=False)
    hp_a_max: Mapped[float] = mapped_column(Float, nullable=False)
    hp_b_max: Mapped[float] = mapped_column(Float, nullable=False)
    bp_a: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bp_b: Mapped[int] = mapped_column(BigInteger, nullable=False)
    armor_a: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    armor_b: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fighter_a: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    fighter_b: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    pending_action_a: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pending_action_b: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    action_log: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    winner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sudden_death: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # v15.1.4 — PvE markers. NULL on PvP duels (legacy + ongoing).
    npc_archetype: Mapped[str | None] = mapped_column(String(24), nullable=True)
    npc_difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pve_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    pve_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class PlayerNotification(Base):
    """v15.1.2 — Persistent notification storage.

    Coexists with the live-state aggregation in api_notifications_inbox. Use
    this table for EVENTS (achievement unlocked, duel challenge incoming,
    title earned, gacha banner refresh, etc) that the player might miss while
    offline. Use the live aggregation for STATES (quest_ready, alchemy_full,
    breakthrough_ready) that reflect current snapshot.

    Helper: `core.notification_engine.notify(session, player_id, kind, ...)`.
    """

    __tablename__ = "player_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    ref_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title_key: Mapped[str] = mapped_column(String(96), nullable=False)
    body_key: Mapped[str] = mapped_column(String(96), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    icon: Mapped[str] = mapped_column(String(16), default="🔔", nullable=False)
    target_tab: Mapped[str | None] = mapped_column(String(32), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlayerTechnique(Base):
    __tablename__ = "player_techniques"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), primary_key=True)
    technique_id: Mapped[int] = mapped_column(Integer, ForeignKey("techniques_catalog.id"), primary_key=True)
    mastery_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    mastery_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active_combat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    grade: Mapped[str] = mapped_column(String(16), default="common", nullable=False)  # common, refined, perfected, transcendent, celestial


class PlayerSectTechnique(Base):
    """TEC-1 — the Library's memory (Migration 136): which house taught which
    shelf art to which cultivator. Rows are NEVER deleted on sect leave — a
    tier-3 art merely LOCKS (unusable) until the cultivator returns to the SAME
    house (cross-sect rule §3, technique_scarcity_economy.md). cp_paid audits
    the contribution sink. Only written where `biblioteca_seitas` is ON."""

    __tablename__ = "player_sect_techniques"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    technique_id: Mapped[int] = mapped_column(Integer, ForeignKey("techniques_catalog.id"), primary_key=True)
    sect_key: Mapped[str] = mapped_column(String(32), nullable=False)
    cp_paid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlayerIntent(Base):
    """v15.2 — Intent System (Sword/Fist/Body/Dao/Killing).

    Tracks cultivator mastery over one of the 5 canonical Wuxia "yì"
    paths. XP is awarded on duel termination (winner +25 dominant intent,
    loser +5). Rank 0..9 follows a ×1.6 curve in core.intent_engine.
    Each player has up to 5 rows (one per intent) — rows are created
    lazily on first XP gain via upsert.
    """

    __tablename__ = "player_intents"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    intent: Mapped[str] = mapped_column(String(16), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlayerNPCCooldown(Base):
    __tablename__ = "player_npc_cooldowns"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True)
    last_npc_fight: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fights_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reset_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Onda 3 — SEPARATE cooldown for NPC-cultivator challenges (does not share the
    # regular NPC-hunt cooldown above, so the 57 players' farming loop is untouched).
    last_cultivator_fight: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# v14.9 round 3 — persistent PvP challenges (mini-app PvP). Replaces the
# in-memory bot_data dict the chat handler uses, which the mini-app cannot
# access. Auto-expire via expires_at + on-read filter (no scheduler needed).
class PVPChallenge(Base):
    __tablename__ = "pvp_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    challenger_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    wager: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    # pending | accepted | declined | cancelled | expired | completed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    winner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rounds_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # round 4 (2026-05-20): per-party seen flags — challenger needs to see
    # outcomes too, not just target. Auto-open modal + bell badge when unseen.
    challenger_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    target_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # v15.1.3 — when target accepts, we spawn a turn-based DuelSession and
    # link it here. Wager stays escrowed on this row; settle path looks the
    # row up via duel_id when the duel terminates.
    duel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class QuestCatalog(Base):
    __tablename__ = "quests_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # daily / weekly
    description: Mapped[str] = mapped_column(Text, nullable=False)
    objective_type: Mapped[str] = mapped_column(String(32), nullable=False)
    objective_value: Mapped[int] = mapped_column(Integer, nullable=False)
    rewards: Mapped[dict] = mapped_column(JSONB, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🎯", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # v16.3.5 Karmic Crossroads — ordered list of moral-choice dicts, or NULL.
    # NULL ⇒ quest behaves exactly as today (single fixed reward). Migration 107.
    choices: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    # v16.4c — Sect Quests. Tags a quest to an NPC house. NULL ⇒ a normal
    # daily/weekly quest, OR (when type=='sect') a UNIVERSAL sect quest shown to
    # any member; a world_sects.id ⇒ a house-specific quest. The quest engine
    # member-gates type=='sect' rows by Player.sect_id. Migration 109.
    sect_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("world_sects.id"), nullable=True, default=None)


class PlayerQuest(Base):
    __tablename__ = "player_quests"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), primary_key=True)
    quest_id: Mapped[int] = mapped_column(Integer, ForeignKey("quests_catalog.id"), primary_key=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    claimed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # v16.3.5 — which moral fork was taken THIS cycle (NULL = none / not a
    # choice quest). Resets to NULL with `claimed` on the next reset, so it
    # never double-counts across cycles. Migration 107.
    chosen_choice_id: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)


class QuestChoiceLog(Base):
    """v16.3.5 — Karmic Crossroads audit log.

    Every applied moral choice writes one append-only row here. Mirrors
    KarmaLog's shape (Lei §1 honest disclosure + future analytics on which
    Wuxia path players walk). The karma side-effect is ALSO logged in
    karma_log via apply_karma; this table additionally records the stones/
    item/reputation deltas and which choice was picked, scoped by reset_at.

    Foreign key CASCADE: a player wipe drops these rows automatically.
    Schema mirrors migrations/107_karmic_crossroads.sql exactly.
    """

    __tablename__ = "quest_choice_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    quest_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chosen_choice_id: Mapped[str] = mapped_column(String(32), nullable=False)
    karma_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_karma: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reputation_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stones_delta: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    item_gained: Mapped[str | None] = mapped_column(String(64), nullable=True)
    item_lost: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class LoginStreak(Base):
    __tablename__ = "login_streak"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), primary_key=True)
    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    total_logins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class BeastCatalog(Base):
    __tablename__ = "beasts_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    rank: Mapped[str] = mapped_column(String(16), nullable=False)
    element: Mapped[str] = mapped_column(String(32), nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🐾", nullable=False)
    base_stats: Mapped[dict] = mapped_column(JSONB, nullable=False)
    special_ability: Mapped[str] = mapped_column(Text, nullable=False)
    catch_rate: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class PlayerBeast(Base):
    __tablename__ = "player_beasts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    catalog_id: Mapped[int] = mapped_column(Integer, ForeignKey("beasts_catalog.id"), nullable=False)
    rank: Mapped[str] = mapped_column(String(16), nullable=False)
    custom_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    exp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_companion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_on_expedition: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expedition_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expedition_returns_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExpeditionCatalog(Base):
    __tablename__ = "expeditions_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    req_beast_rank: Mapped[str] = mapped_column(String(16), nullable=False)
    drops: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🗺️", nullable=False)


class DaoLawCatalog(Base):
    __tablename__ = "dao_laws_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), nullable=False)
    element: Mapped[str] = mapped_column(String(32), nullable=False)
    total_fragments: Mapped[int] = mapped_column(Integer, nullable=False)
    effect_type: Mapped[str] = mapped_column(Text, nullable=False)
    effect_per_fragment: Mapped[float] = mapped_column(Float, nullable=False)
    min_realm: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class PlayerDaoFragment(Base):
    __tablename__ = "player_dao_fragments"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), primary_key=True)
    dao_law_id: Mapped[int] = mapped_column(Integer, ForeignKey("dao_laws_catalog.id"), primary_key=True)
    fragments_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    insight_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# --- 3000 Dao Laws System ---

class DaoCategory(Base):
    __tablename__ = "dao_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name_pt: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name_es: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emoji: Mapped[str] = mapped_column(String(8), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_realm: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    bonus_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_heavenly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DaoPath(Base):
    __tablename__ = "dao_paths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("dao_categories.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    name_pt: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name_es: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emoji: Mapped[str] = mapped_column(String(8), nullable=False)
    element: Mapped[str | None] = mapped_column(String(32), nullable=True)
    total_laws: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    min_realm: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    bonus_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_heavenly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DaoPathLaw(Base):
    __tablename__ = "dao_path_laws"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path_id: Mapped[int] = mapped_column(Integer, ForeignKey("dao_paths.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    name_pt: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name_es: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rarity: Mapped[str] = mapped_column(String(16), default="common", nullable=False)
    min_realm: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlayerDaoDiscovery(Base):
    __tablename__ = "player_dao_discoveries"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True)
    law_id: Mapped[int] = mapped_column(Integer, ForeignKey("dao_path_laws.id"), primary_key=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class WorldBoss(Base):
    __tablename__ = "world_bosses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), nullable=False)
    hp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_hp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    loot_table: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tier: Mapped[str] = mapped_column(String(16), default="mortal", nullable=False)
    phase: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    rewards_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class WorldBossDamage(Base):
    __tablename__ = "world_boss_damage"

    boss_id: Mapped[int] = mapped_column(Integer, ForeignKey("world_bosses.id", ondelete="CASCADE"), primary_key=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True)
    total_damage: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_hit: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PrestigeLog(Base):
    __tablename__ = "prestige_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    prestige_level: Mapped[int] = mapped_column(Integer, nullable=False)
    prestige_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    retained_technique: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retained_dao_laws: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


# --- Monetization ---

class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_eur: Mapped[float] = mapped_column(Float, nullable=False)
    spirit_jade_granted: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(64), nullable=False) # e.g., 'telegram_stars', 'stripe', 'admin'
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlayerVIP(Base):
    __tablename__ = "player_vip"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True)
    vip_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_spent_eur: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_rerolls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    monthly_card_type: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    monthly_card_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    monthly_card_claimed_today: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    vip_milestones_claimed: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )


class BattlePass(Base):
    __tablename__ = "battle_pass"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_jade_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_tiers: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class GachaBanner(Base):
    __tablename__ = "gacha_banners"

    id: Mapped[str] = mapped_column(String(64), primary_key=True) # e.g., 'ancient_chest_01'
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    items: Mapped[dict] = mapped_column(JSONB, nullable=False) # The loot table and probabilities
    pity_at: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GachaHistory(Base):
    __tablename__ = "gacha_history"
    __table_args__ = (
        Index("idx_gacha_history_player_banner", "player_id", "banner_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    banner_id: Mapped[str] = mapped_column(String(64), ForeignKey("gacha_banners.id", ondelete="SET NULL"), nullable=True)
    result_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    result_rarity: Mapped[str] = mapped_column(String(32), nullable=False)
    pity_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class DungeonCatalog(Base):
    __tablename__ = "dungeons_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    min_realm: Mapped[int] = mapped_column(Integer, nullable=False)
    max_realm: Mapped[int] = mapped_column(Integer, nullable=False)
    floor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    qi_cost_per_floor: Mapped[int] = mapped_column(Integer, nullable=False)
    drops: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🗺️", nullable=False)
    base_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("200"))
    floor_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # MV-1 (Mig 129): continente onde o portal fica ancorado. NULL = não-ancorada
    # (visível em todo lado). Só morde com a flag per-world `dungeons_regionais`.
    continent: Mapped[str | None] = mapped_column(String(16), nullable=True)


class PlayerDungeon(Base):
    __tablename__ = "player_dungeons"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True)
    dungeon_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeons_catalog.id", ondelete="CASCADE"), primary_key=True)
    current_floor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_floor_reached: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expedition_bag: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    best_difficulty: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default=text("0"))


class AchievementCatalog(Base):
    __tablename__ = "achievements_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_value: Mapped[int] = mapped_column(Integer, nullable=False)
    title_granted: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stat_bonus: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    emoji: Mapped[str] = mapped_column(String(8), default="🏆", nullable=False)


class PlayerAchievement(Base):
    __tablename__ = "player_achievements"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True)
    achievement_id: Mapped[int] = mapped_column(Integer, ForeignKey("achievements_catalog.id", ondelete="CASCADE"), primary_key=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CelestialEvent(Base):
    __tablename__ = "celestial_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # meteor_shower, dao_convergence, immortal_auction, spirit_tide, demonic_invasion
    description: Mapped[str] = mapped_column(Text, nullable=False)
    multipliers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"cb_mult": 3.0, "loot_mult": 2.0, ...}
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)  # seed default duration
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    emoji: Mapped[str] = mapped_column(String(8), default="🌌", nullable=False)


class GachaPity(Base):
    """Persistent pity counter per player per banner. Reset only on legendary pull."""
    __tablename__ = "gacha_pity"
    __table_args__ = (UniqueConstraint("player_id", "banner_id", name="uq_gacha_pity"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    banner_id: Mapped[str] = mapped_column(String(64), ForeignKey("gacha_banners.id", ondelete="CASCADE"), nullable=False)
    current_pity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class DaoPartner(Base):
    __tablename__ = "dao_partners"
    __table_args__ = (UniqueConstraint("player1_id", "player2_id", name="uq_dao_partners"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player1_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    player2_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    intimacy_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    married_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    ring_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class DaoPartnerProposal(Base):
    __tablename__ = "dao_partner_proposals"
    __table_args__ = (UniqueConstraint("proposer_id", "target_id", name="uq_dao_proposal"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlayerMedicineResistance(Base):
    __tablename__ = "player_medicine_resistance"
    __table_args__ = (UniqueConstraint("player_id", "pill_id", name="uq_player_pill_resistance"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), nullable=False, index=True)
    pill_id: Mapped[int] = mapped_column(Integer, nullable=False)
    consumption_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PlayerAlchemySkill(Base):
    __tablename__ = "player_alchemy_skills"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), primary_key=True)
    tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1=Apprentice..5=Celestial
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_crafts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    divine_crafts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PlayerForgeSkill(Base):
    __tablename__ = "player_forge_skills"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id"), primary_key=True)
    tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1=Novice..5=Legendary
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_forges: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    divine_forges: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ForgeRecipe(Base):
    __tablename__ = "forge_recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(Integer, ForeignKey("artifacts_catalog.id"), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    materials: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    required_realm: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    base_success_rate: Mapped[float] = mapped_column(Float, default=80.0, nullable=False)
    bp_bonus: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PlayerForgeMastery(Base):
    __tablename__ = "player_forge_mastery"
    __table_args__ = (UniqueConstraint("player_id", "recipe_id", name="uq_player_forge_mastery"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    recipe_id: Mapped[int] = mapped_column(Integer, ForeignKey("forge_recipes.id", ondelete="CASCADE"), nullable=False)
    mastery_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    forges_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class BattlePassMission(Base):
    __tablename__ = "battle_pass_missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    objective_type: Mapped[str] = mapped_column(String(32), nullable=False)
    objective_value: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_jade: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_items: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_premium_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description_key: Mapped[str] = mapped_column(String(64), nullable=False)  # locale key
    reset_type: Mapped[str] = mapped_column(String(10), default="none", nullable=False)  # none / daily / weekly


class PlayerBPMission(Base):
    __tablename__ = "player_bp_missions"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True)
    mission_id: Mapped[int] = mapped_column(Integer, ForeignKey("battle_pass_missions.id", ondelete="CASCADE"), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    claimed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    times_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlayerSpatialRing(Base):
    __tablename__ = "player_spatial_rings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id"), unique=True, nullable=False, index=True
    )
    tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_slots: Mapped[int] = mapped_column(Integer, default=50, nullable=False)


class PlayerPrestigePurchase(Base):
    """v14.14c — Prestige Shop purchase ledger.

    One row per (player, item) pair; ``count`` tracks repeat purchases so the
    engine can enforce ``max_purchases`` caps without scanning history.
    """
    __tablename__ = "player_prestige_purchases"
    __table_args__ = (UniqueConstraint("player_id", "item_id", name="uq_player_prestige_purchase"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlayerPillMastery(Base):
    __tablename__ = "player_pill_mastery"
    __table_args__ = (UniqueConstraint("player_id", "pill_id", name="uq_player_pill_mastery"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    pill_id: Mapped[int] = mapped_column(Integer, nullable=False)
    mastery_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    crafts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PlayerRecipe(Base):
    __tablename__ = "player_recipes"
    __table_args__ = (UniqueConstraint("player_id", "item_type", "item_id", name="uq_player_recipe"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "pill" or "artifact"
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"), nullable=False
    )


class PlayerSoulFire(Base):
    __tablename__ = "player_soul_fire"

    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True)
    fire_tier: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fire_exp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# ── Faction System ──────────────────────────────────────────────────

class FactionCatalog(Base):
    """Static definition of each faction (Celestial / Demonic)."""
    __tablename__ = "factions_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), nullable=False)
    bonuses: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class PlayerFaction(Base):
    """A player's faction membership and reputation."""
    __tablename__ = "player_factions"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    faction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("factions_catalog.id"), nullable=False
    )
    reputation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_rep_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rank: Mapped[str] = mapped_column(String(32), default="Initiate", nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class FactionQuestCatalog(Base):
    """Static catalogue of faction quests."""
    __tablename__ = "faction_quests_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    faction_id: Mapped[int] = mapped_column(Integer, ForeignKey("factions_catalog.id"), nullable=False)
    quest_type: Mapped[str] = mapped_column(String(32), nullable=False)  # dungeon, combat, alchemy, gather
    target: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {"dungeon_id": 1, "floor": 5} or {"count": 10}
    reward_rep: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_items: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"spirit_stones": 5000, ...}
    min_realm: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cooldown_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="📋", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class PlayerFactionQuest(Base):
    """A player's progress on a faction quest."""
    __tablename__ = "player_faction_quests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True
    )
    quest_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("faction_quests_catalog.id"), nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    claimed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FactionShopItem(Base):
    """Items available for purchase with faction reputation."""
    __tablename__ = "faction_shop_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    faction_id: Mapped[int] = mapped_column(Integer, ForeignKey("factions_catalog.id"), nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)  # technique, recipe, artifact, pill
    item_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # item-specific payload
    rep_cost: Mapped[int] = mapped_column(Integer, nullable=False)
    min_rank: Mapped[str] = mapped_column(String(32), default="Initiate", nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🛒", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class SectContributionLog(Base):
    __tablename__ = "sect_contribution_log"
    __table_args__ = (
        Index("idx_sect_contrib_sect_id", "sect_id"),
        Index("idx_sect_contrib_created_at", "created_at"),
        Index("idx_sect_contrib_player_sect", "player_id", "sect_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False)
    sect_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sects.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # donation, quest, war
    amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


# -- Dungeon Quests ----------------------------------------------------------

class DungeonQuestCatalog(Base):
    """Static definition of story-driven dungeon quests."""
    __tablename__ = "dungeon_quests_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dungeon_id: Mapped[int] = mapped_column(Integer, ForeignKey("dungeons_catalog.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description_key: Mapped[str] = mapped_column(String(64), nullable=False)
    story_intro_key: Mapped[str] = mapped_column(String(64), nullable=False)
    story_complete_key: Mapped[str] = mapped_column(String(64), nullable=False)
    objective_type: Mapped[str] = mapped_column(String(32), nullable=False)
    objective_target: Mapped[str | None] = mapped_column(String(64), nullable=True)
    objective_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reward_rep: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_stones: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_items: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    cooldown_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    min_difficulty: Mapped[str] = mapped_column(String(16), default="easy", nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="📜", nullable=False)


class PlayerDungeonQuest(Base):
    """Player progress on a dungeon quest, with repeatable cooldown."""
    __tablename__ = "player_dungeon_quests"
    __table_args__ = (
        UniqueConstraint("player_id", "quest_id", name="uq_pdq_player_quest"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), nullable=False, index=True
    )
    quest_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dungeon_quests_catalog.id"), nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PlayerNotificationPref(Base):
    """M-9: per-player toggles for non-essential notifications."""
    __tablename__ = "player_notification_prefs"

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    anomaly_global: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sect_edict: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pill_finished: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alchemy_energy_full: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    breakthrough_ready: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trib_cooldown_done: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Onda 3 — Heaven's Whispers opt-out (atmospheric world-event notifications).
    whisper: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class GlobalAnnouncement(Base):
    """Persistent feed of broadcast events shown in the mini-app.
    Populated by core.announcement_engine.broadcast() so the mini-app can show
    a global news feed without re-running the broadcast logic.
    """
    __tablename__ = "global_announcements"
    __table_args__ = (
        Index("idx_global_announcements_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # realm_up, world_boss, sect_war, etc.
    icon: Mapped[str] = mapped_column(String(8), default="📜", nullable=False)
    message_key: Mapped[str] = mapped_column(String(64), nullable=False)  # i18n key
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    rendered_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # PT pre-rendered fallback
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
