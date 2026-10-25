import logging
from sqlalchemy import select
from database.models import QuestCatalog

logger = logging.getLogger(__name__)

# v16.3.5 Karmic Crossroads — `choices` is an ordered list of moral-fork dicts.
# Shape per choice (see core/quest_choice_engine.py):
#   {"id","label_key","result_key","karma_delta","reputation_delta",
#    "stones_delta","item_gained","item_lost"}
# REPLACE semantics: the chosen fork's deltas REPLACE the flat `rewards` (stones
# via stones_delta, plus optional concrete item_gained/item_lost). The neutral
# (karma 0) option ≈ the original reward so the economy stays flat. Only quests
# whose reward is fully expressible as stones + a concrete inventory item carry a
# fork (Q9's contribution_points reward is intentionally left as-is). label_key /
# result_key live in locales/*.json AND miniapp/i18n/*.json (parity ×3, pt = BR).

QUEST_SEEDS = [
    # ── DAILY QUESTS ──
    {
        "id": 1,
        "name": "Cultivate for 10 Minutes",
        "type": "daily",
        "description": "Cultivate for at least 10 minutes",
        "objective_type": "cultivate",
        "objective_value": 10,
        "rewards": {"spirit_stones": 500},
        "emoji": "🧘",
        "is_active": True,
        "choices": [
            {"id": "share_qi", "label_key": "qc_1_share_qi", "result_key": "qc_1_share_qi_result",
             "karma_delta": 10, "reputation_delta": 0, "stones_delta": 400, "item_gained": None, "item_lost": None},
            {"id": "hoard", "label_key": "qc_1_hoard", "result_key": "qc_1_hoard_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 500, "item_gained": None, "item_lost": None},
            {"id": "forbidden_absorb", "label_key": "qc_1_forbidden_absorb", "result_key": "qc_1_forbidden_absorb_result",
             "karma_delta": -15, "reputation_delta": 0, "stones_delta": 700, "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 2,
        "name": "Craft 3 Pills",
        "type": "daily",
        "description": "Craft 3 pills in the cauldron",
        "objective_type": "craft_pill",
        "objective_value": 3,
        "rewards": {"spirit_stones": 300, "herb_pack": 2},
        "emoji": "⚗️",
        "is_active": True,
        "choices": [
            {"id": "gift_pills", "label_key": "qc_2_gift_pills", "result_key": "qc_2_gift_pills_result",
             "karma_delta": 15, "reputation_delta": 0, "stones_delta": 250, "item_gained": None, "item_lost": None},
            {"id": "sell_fair", "label_key": "qc_2_sell_fair", "result_key": "qc_2_sell_fair_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 400,
             "item_gained": {"type": "herb", "id": 1, "quantity": 3}, "item_lost": None},
            {"id": "counterfeit", "label_key": "qc_2_counterfeit", "result_key": "qc_2_counterfeit_result",
             "karma_delta": -20, "reputation_delta": 0, "stones_delta": 600, "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 3,
        # MV-9 §P6 (review): o objetivo mudou para `npc_combat` mas o NOME e a
        # DESCRIÇÃO continuavam a mandar treinar com outro jogador — o jogador
        # lia "sparring" e completava batendo num NPC. Texto alinhado ao que a
        # quest realmente pede. (Não há `q_3_name`/`q_3_desc` em i18n: estas
        # strings do seed são o que a tela imprime.)
        "name": "Test Your Fists",
        "type": "daily",
        "description": "Win a duel against a wandering cultivator",
        # MV-9 §P6 — era `sparring`: PvP consentido, exigindo um SEGUNDO jogador
        # vivo que aceitasse o duelo. Medido: 0 sparrings em 30 dias no main e 0
        # desde sempre no s2 — esta daily foi entregue a todo jogador, todo dia,
        # e era INCOMPLETÁVEL. 4ª recorrência da mesma regra ("objetivo nunca
        # depende de outro jogador vivo"). `npc_combat` mantém a temática de
        # duelo (o texto continua a ser um treino) e é solo-completável.
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "⚔️",
        "is_active": True,
        "choices": [
            {"id": "mercy", "label_key": "qc_3_mercy", "result_key": "qc_3_mercy_result",
             "karma_delta": 15, "reputation_delta": 0, "stones_delta": 150, "item_gained": None, "item_lost": None},
            {"id": "honor", "label_key": "qc_3_honor", "result_key": "qc_3_honor_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 250, "item_gained": None, "item_lost": None},
            {"id": "cripple", "label_key": "qc_3_cripple", "result_key": "qc_3_cripple_result",
             "karma_delta": -15, "reputation_delta": 0, "stones_delta": 400, "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 4,
        "name": "Daily Login",
        "type": "daily",
        "description": "Log in to the bot today",
        "objective_type": "login",
        "objective_value": 1,
        "rewards": {"spirit_jade": 5},
        "emoji": "☯️",
        "is_active": True,
    },
    {
        "id": 5,
        "name": "Send Beast on Expedition",
        "type": "daily",
        "description": "Send a Spirit Beast on an expedition",
        "objective_type": "beast_expedition",
        "objective_value": 1,
        "rewards": {"spirit_stones": 400},
        "emoji": "🐉",
        "is_active": True,
        "choices": [
            {"id": "release_rare", "label_key": "qc_5_release_rare", "result_key": "qc_5_release_rare_result",
             "karma_delta": 20, "reputation_delta": 0, "stones_delta": 300, "item_gained": None, "item_lost": None},
            {"id": "capture", "label_key": "qc_5_capture", "result_key": "qc_5_capture_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 400, "item_gained": None, "item_lost": None},
            {"id": "harvest_core", "label_key": "qc_5_harvest_core", "result_key": "qc_5_harvest_core_result",
             "karma_delta": -20, "reputation_delta": 0, "stones_delta": 600, "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 6,
        "name": "Attack World Boss",
        "type": "daily",
        "description": "Attack the World Boss at least once",
        "objective_type": "boss_attack",
        "objective_value": 1,
        "rewards": {"spirit_stones": 500},
        "emoji": "👹",
        "is_active": True,
        "choices": [
            {"id": "protect", "label_key": "qc_6_protect", "result_key": "qc_6_protect_result",
             "karma_delta": 20, "reputation_delta": 0, "stones_delta": 400, "item_gained": None, "item_lost": None},
            {"id": "glory", "label_key": "qc_6_glory", "result_key": "qc_6_glory_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 500, "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 7,
        "name": "Win a Combat",
        "type": "daily",
        "description": "Win an Arena or Sparring combat",
        "objective_type": "arena_win",
        "objective_value": 1,
        "rewards": {"spirit_stones": 300},
        "emoji": "🏆",
        "is_active": True,
        "choices": [
            {"id": "spare", "label_key": "qc_7_spare", "result_key": "qc_7_spare_result",
             "karma_delta": 10, "reputation_delta": 0, "stones_delta": 200, "item_gained": None, "item_lost": None},
            {"id": "claim_spoils", "label_key": "qc_7_claim_spoils", "result_key": "qc_7_claim_spoils_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 300, "item_gained": None, "item_lost": None},
            {"id": "humiliate", "label_key": "qc_7_humiliate", "result_key": "qc_7_humiliate_result",
             "karma_delta": -10, "reputation_delta": 0, "stones_delta": 450, "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 8,
        "name": "Use 3 Pills",
        "type": "daily",
        "description": "Consume 3 pills to boost your cultivation",
        "objective_type": "use_pill",
        "objective_value": 3,
        "rewards": {"spirit_stones": 200},
        "emoji": "💊",
        "is_active": True,
    },
    # ── WEEKLY QUESTS ──
    {
        "id": 9,
        "name": "Contribute 5000 Stones to Sect",
        "type": "weekly",
        "description": "Donate 5000 Spirit Stones to your sect's vault",
        "objective_type": "sect_contribution",
        "objective_value": 5000,
        "rewards": {"contribution_points": 500, "technique_scroll": 1},
        "emoji": "🏯",
        "is_active": True,
    },
    {
        "id": 10,
        "name": "Top 3 in Arena",
        "type": "weekly",
        "description": "Reach the top 3 in the Arena rankings",
        "objective_type": "arena_top3",
        "objective_value": 1,
        "rewards": {"spirit_jade": 50},
        "emoji": "🏆",
        "is_active": True,
    },
    {
        "id": 11,
        "name": "Craft 10 Pills",
        "type": "weekly",
        "description": "Craft 10 pills over the course of the week",
        "objective_type": "craft_pill",
        "objective_value": 10,
        "rewards": {"spirit_stones": 1500},
        "emoji": "💊",
        "is_active": True,
    },
    {
        "id": 12,
        "name": "Survive 3 Tribulations",
        "type": "weekly",
        "description": "Survive 3 Heavenly Tribulations this week",
        "objective_type": "tribulation_survive",
        "objective_value": 3,
        "rewards": {"spirit_stones": 2000, "technique_scroll": 1},
        "emoji": "⚡",
        "is_active": True,
        "choices": [
            {"id": "shield_others", "label_key": "qc_12_shield_others", "result_key": "qc_12_shield_others_result",
             "karma_delta": 20, "reputation_delta": 0, "stones_delta": 1500,
             "item_gained": {"type": "technique_scroll", "id": 1, "quantity": 1}, "item_lost": None},
            {"id": "endure_alone", "label_key": "qc_12_endure_alone", "result_key": "qc_12_endure_alone_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 2000,
             "item_gained": {"type": "technique_scroll", "id": 1, "quantity": 1}, "item_lost": None},
        ],
    },
    {
        "id": 13,
        "name": "Deal 1M Boss Damage",
        "type": "weekly",
        "description": "Deal a total of 1,000,000 damage to World Bosses",
        "objective_type": "boss_damage",
        "objective_value": 1000000,
        "rewards": {"spirit_jade": 30},
        "emoji": "👹",
        "is_active": True,
    },
    {
        "id": 14,
        "name": "Win 10 Arena Matches",
        "type": "weekly",
        "description": "Win 10 Arena matches this week",
        "objective_type": "arena_win",
        "objective_value": 10,
        "rewards": {"spirit_jade": 25, "spirit_stones": 1000},
        "emoji": "🏆",
        "is_active": True,
    },
    {
        "id": 15,
        "name": "Complete a 8h+ Expedition",
        "type": "weekly",
        "description": "Complete a beast expedition that lasts 8 hours or more",
        "objective_type": "long_expedition",
        "objective_value": 1,
        "rewards": {"spirit_stones": 800, "beast_core": 1},
        "emoji": "🗺️",
        "is_active": True,
    },
    {
        "id": 16,
        "name": "Clear 5 Dungeon Floors",
        "type": "daily",
        "description": "Clear 5 floors in any dungeon",
        "objective_type": "dungeon_floor",
        "objective_value": 5,
        "rewards": {"spirit_stones": 600},
        "emoji": "🗺️",
        "is_active": True,
        "choices": [
            {"id": "escort_weak", "label_key": "qc_16_escort_weak", "result_key": "qc_16_escort_weak_result",
             "karma_delta": 15, "reputation_delta": 0, "stones_delta": 450, "item_gained": None, "item_lost": None},
            {"id": "speedrun", "label_key": "qc_16_speedrun", "result_key": "qc_16_speedrun_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 600, "item_gained": None, "item_lost": None},
            {"id": "loot_first", "label_key": "qc_16_loot_first", "result_key": "qc_16_loot_first_result",
             "karma_delta": -10, "reputation_delta": 0, "stones_delta": 800, "item_gained": None, "item_lost": None},
        ],
    },
    # ── SECT QUESTS (v16.4c — member-gated, type='sect') ──
    # sect_id=None ⇒ UNIVERSAL: shown to any house member, framed by the player's
    # own house in the Hall. Rewards grant `sect_contribution` (the NPC-sect rank
    # currency). The first wave is a small spine that scales to all 9 houses; a
    # fork quest (602) reuses Karmic Crossroads (sect_contribution_delta per fork).
    {
        "id": 600,
        "name": "Devotion of the Disciple",
        "type": "sect",
        "description": "Meditate for 30 minutes in service of your house.",
        "objective_type": "cultivate",
        "objective_value": 30,
        "rewards": {"spirit_stones": 300, "sect_contribution": 30},
        "emoji": "🏯",
        "is_active": True,
        "sect_id": None,
    },
    {
        "id": 601,
        "name": "Defend the House's Honour",
        "type": "sect",
        "description": "Win 3 Arena matches to bring glory to your house.",
        "objective_type": "arena_win",
        "objective_value": 3,
        "rewards": {"spirit_stones": 400, "sect_contribution": 40},
        "emoji": "⚔️",
        "is_active": True,
        "sect_id": None,
    },
    {
        "id": 602,
        "name": "The Elder's Judgment",
        "type": "sect",
        "description": "A junior disciple stole from the sect vault and stands before you. The Elder leaves the verdict in your hands.",
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "⚖️",
        "is_active": True,
        "sect_id": None,
        "choices": [
            {"id": "mercy", "label_key": "qc_602_mercy", "result_key": "qc_602_mercy_result",
             "karma_delta": 20, "reputation_delta": 0, "stones_delta": 200, "sect_contribution_delta": 30,
             "item_gained": None, "item_lost": None},
            {"id": "honor", "label_key": "qc_602_honor", "result_key": "qc_602_honor_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 300, "sect_contribution_delta": 40,
             "item_gained": None, "item_lost": None},
            {"id": "cruelty", "label_key": "qc_602_cruelty", "result_key": "qc_602_cruelty_result",
             "karma_delta": -25, "reputation_delta": 0, "stones_delta": 450, "sect_contribution_delta": 50,
             "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 603,
        "name": "Tribute to the Treasury",
        "type": "sect",
        "description": "Strike the World Boss in the name of your house.",
        "objective_type": "boss_attack",
        "objective_value": 1,
        "rewards": {"spirit_stones": 250, "sect_contribution": 25},
        "emoji": "💰",
        "is_active": True,
        "sect_id": None,
    },
    {
        "id": 604,
        "name": "The Deep Secrets",
        "type": "sect",
        "description": "Clear 10 dungeon floors to prove yourself worthy of the house's deeper teachings.",
        "objective_type": "dungeon_floor",
        "objective_value": 10,
        "rewards": {"spirit_stones": 600, "sect_contribution": 60},
        "emoji": "📜",
        "is_active": True,
        "sect_id": None,
    },
    # ── SECT QUEST ARCS (Pedra 2 wave 2 — per Cultivation Sect, 610-636) ──
    # One bespoke 3-beat arc per house (gancho → ato → clímax moral fork),
    # member-gated by sect_id (FK → world_sects.id; the seed runner seeds the
    # 9 houses FIRST, see database/db.py). SEED-ONLY, zero migration, zero
    # stat/jade. Names/descriptions are localized via q_<id>_name/_desc
    # (server-resolved in the Hall + chat; the stored English is the silent
    # fallback). Fork beats reuse Karmic Crossroads (qc_<id>_<choice>).
    {
        "id": 610,
        "name": "The Vow of the Wandering Cloud",
        "type": "sect",
        "description": "The village of White Pine lives beneath Azure Cloud's veil of mist, and famine has come with the drought of Linghe's celestial rivers. Sit in meditation for thirty minutes and let your qi rise as an offering to the heavens, so the mercy of the clouds may once more rain upon the people who trusted in our protection.",
        "objective_type": "cultivate",
        "objective_value": 30,
        "rewards": {"spirit_stones": 300, "sect_contribution": 25},
        "emoji": "☁️",
        "is_active": True,
        "sect_id": "azure_cloud",
    },
    {
        "id": 611,
        "name": "Bandits Beneath the Mist",
        "type": "sect",
        "description": "The same sacred mist that shields White Pine has become a hiding place: fallen cultivators use our cloud-veil to ambush pilgrims on the trails of Linghe. Azure Cloud's freedom was never a license to plunder — defeat two of these wandering bandits and return the paths to those who travel beneath the open sky.",
        "objective_type": "npc_combat",
        "objective_value": 2,
        "rewards": {"spirit_stones": 350, "sect_contribution": 30},
        "emoji": "🌫️",
        "is_active": True,
        "sect_id": "azure_cloud",
    },
    {
        "id": 612,
        "name": "The Cloud That Turned to Storm",
        "type": "sect",
        "description": "A sect-brother twisted the vow of the cloud: he took the freedom we swore to protect and turned it into tyranny over those we should shelter. The Elder withdraws into the silence of the heights and leaves the verdict in your hands, once you face him in a duel before the sect.",
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "⚖️",
        "is_active": True,
        "sect_id": "azure_cloud",
        "choices": [
            {"id": "mercy", "label_key": "qc_612_mercy", "result_key": "qc_612_mercy_result",
             "karma_delta": 20, "reputation_delta": 0, "stones_delta": 250, "sect_contribution_delta": 35,
             "item_gained": None, "item_lost": None},
            {"id": "justice", "label_key": "qc_612_justice", "result_key": "qc_612_justice_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 350, "sect_contribution_delta": 50,
             "item_gained": None, "item_lost": None},
            {"id": "expose", "label_key": "qc_612_expose", "result_key": "qc_612_expose_result",
             "karma_delta": -20, "reputation_delta": 0, "stones_delta": 500, "sect_contribution_delta": 25,
             "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 613,
        "name": "The Ancestral Ember Falters",
        "type": "sect",
        "description": "The mother-flame of the Pavilion, lit since its founding in Linghe, has guttered down to a single ember, and no furnace in the hall can rekindle it. The Elder commands you to feed the inner fire by meditating twenty-five minutes, letting your own qi burn as fuel so the Eternal Flame never dies. If the flame dies we kindle another, yet this one must not die through your neglect.",
        "objective_type": "cultivate",
        "objective_value": 25,
        "rewards": {"spirit_stones": 300, "sect_contribution": 25},
        "emoji": "🔥",
        "is_active": True,
        "sect_id": "eternal_flame",
    },
    {
        "id": 614,
        "name": "Ash, Say the Thousand Bloom",
        "type": "sect",
        "description": "Disciples of the rival Thousand Bloom spread the word through every hall of Linghe that the Eternal Flame is nothing but cold ash now, toothless and burnt out, a House the Dao itself has abandoned. The Elder orders you to silence the scorn where it stings most by winning three duels in the arena, each victory rekindling the House's name before every cultivator.",
        "objective_type": "arena_win",
        "objective_value": 3,
        "rewards": {"spirit_stones": 400, "sect_contribution": 35},
        "emoji": "⚔️",
        "is_active": True,
        "sect_id": "eternal_flame",
    },
    {
        "id": 615,
        "name": "The Cornered Prodigy",
        "type": "sect",
        "description": "At last you cross blades with the Thousand Bloom prodigy who mocked the House, and in a single duel you corner him with no way out, his qi flickering like a candle in the wind. Glory blows hot in your ear, yet the Elder whispers that true fire knows when to blaze and when to hold; at the end of the bout, the choice is yours.",
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "🔥",
        "is_active": True,
        "sect_id": "eternal_flame",
        "choices": [
            {"id": "glory", "label_key": "qc_615_glory", "result_key": "qc_615_glory_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 450, "sect_contribution_delta": 40,
             "item_gained": None, "item_lost": None},
            {"id": "prudence", "label_key": "qc_615_prudence", "result_key": "qc_615_prudence_result",
             "karma_delta": 15, "reputation_delta": 0, "stones_delta": 250, "sect_contribution_delta": 50,
             "item_gained": None, "item_lost": None},
            {"id": "ruthless", "label_key": "qc_615_ruthless", "result_key": "qc_615_ruthless_result",
             "karma_delta": -20, "reputation_delta": 0, "stones_delta": 550, "sect_contribution_delta": 25,
             "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 616,
        "name": "The Tremor Beneath the Jade",
        "type": "sect",
        "description": "A shudder of imbalance rises from the Abyssal Depths and makes the qi ley-lines of Linghe ripple like fouled water; you feel the discord even in your own breath. Sit in harmony-meditation for 30 minutes to resettle your core and return balance to the earth's veins.",
        "objective_type": "cultivate",
        "objective_value": 30,
        "rewards": {"spirit_stones": 300, "sect_contribution": 25},
        "emoji": "🪷",
        "is_active": True,
        "sect_id": "jade_harmony",
    },
    {
        "id": 617,
        "name": "Shadows at the Jade Shrine",
        "type": "sect",
        "description": "Two Abyssal cultists have crept upward to defile an ancient jade shrine with corrupted qi. Drive off the two wandering cultivators without letting hatred into your heart, for the clean strike is born of calm, not of wrath.",
        "objective_type": "npc_combat",
        "objective_value": 2,
        "rewards": {"spirit_stones": 380, "sect_contribution": 32},
        "emoji": "☯️",
        "is_active": True,
        "sect_id": "jade_harmony",
    },
    {
        "id": 618,
        "name": "Verdict of the Fallen Disciple",
        "type": "sect",
        "description": "A sect-brother, seduced by abyssal power, broke the harmony and harmed an innocent; the Elders hand him to you for judgment. Cross blades with him in a single sparring trial and then, with your core still serene, pronounce the House's verdict.",
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "⚖️",
        "is_active": True,
        "sect_id": "jade_harmony",
        "choices": [
            {"id": "mercy", "label_key": "qc_618_mercy", "result_key": "qc_618_mercy_result",
             "karma_delta": 20, "reputation_delta": 0, "stones_delta": 250, "sect_contribution_delta": 35,
             "item_gained": None, "item_lost": None},
            {"id": "justice", "label_key": "qc_618_justice", "result_key": "qc_618_justice_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 350, "sect_contribution_delta": 50,
             "item_gained": None, "item_lost": None},
            {"id": "expose", "label_key": "qc_618_expose", "result_key": "qc_618_expose_result",
             "karma_delta": -20, "reputation_delta": 0, "stones_delta": 500, "sect_contribution_delta": 25,
             "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 619,
        "name": "The Vigil of Iron Veins",
        "type": "sect",
        "description": "Before the first ray of dawn touches the Mountain Gate, the Elder bids you sit unmoving upon the cold stone and temper flesh and will through stillness. Meditate for thirty minutes, yielding neither to the trembling nor the cold, for in Iron Mountain the body is the strongest sword, and the body that does not move through one night will never break across a century.",
        "objective_type": "cultivate",
        "objective_value": 30,
        "rewards": {"spirit_stones": 300, "sect_contribution": 25},
        "emoji": "🏔️",
        "is_active": True,
        "sect_id": "iron_mountain",
    },
    {
        "id": 620,
        "name": "Hold the Deep Passage",
        "type": "sect",
        "description": "The mountain's roots groan: the ancient passage threading the heart of Qianhe threatens to collapse upon the brothers who guard it. The Elder does not send the swift to flee, but the steadfast to descend. Hold each level on your own shoulders and your own tempered flesh, clearing eight floors until the stone ceases its weeping.",
        "objective_type": "dungeon_floor",
        "objective_value": 8,
        "rewards": {"spirit_stones": 420, "sect_contribution": 35},
        "emoji": "⛰️",
        "is_active": True,
        "sect_id": "iron_mountain",
    },
    {
        "id": 621,
        "name": "The Abandoned Post",
        "type": "sect",
        "description": "A sworn brother fled his post, seized by fear, and because of it others were nearly buried alive beneath the stone. The Elder lowers the granite hammer before you and falls silent: the Mountain's verdict shall be yours. Measure the man in a single sparring bout, see with your own eyes whether any steel remains in him, then pronounce his fate.",
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "⚖️",
        "is_active": True,
        "sect_id": "iron_mountain",
        "choices": [
            {"id": "mercy", "label_key": "qc_621_mercy", "result_key": "qc_621_mercy_result",
             "karma_delta": 20, "reputation_delta": 0, "stones_delta": 250, "sect_contribution_delta": 35,
             "item_gained": None, "item_lost": None},
            {"id": "justice", "label_key": "qc_621_justice", "result_key": "qc_621_justice_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 350, "sect_contribution_delta": 50,
             "item_gained": None, "item_lost": None},
            {"id": "expose", "label_key": "qc_621_expose", "result_key": "qc_621_expose_result",
             "karma_delta": -20, "reputation_delta": 0, "stones_delta": 500, "sect_contribution_delta": 25,
             "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 622,
        "name": "The Silence Beneath Eternal Ice",
        "type": "sect",
        "description": "The Elders of Frozen Peak summon you to the deepest meditation hall, where breath itself crystallizes in the air. Sit within the stillness of ice and cultivate for 35 minutes unbroken, until the cold silences your mind and the Dao whispers in the motionlessness.",
        "objective_type": "cultivate",
        "objective_value": 35,
        "rewards": {"spirit_stones": 320, "sect_contribution": 25},
        "emoji": "❄️",
        "is_active": True,
        "sect_id": "frozen_peak",
    },
    {
        "id": 623,
        "name": "Raiders in the Treacherous Thaw",
        "type": "sect",
        "description": "The spring thaw has opened paths through the ice, and wandering cultivators climb the peak to loot the shrines of the frost arts. Serenity is not weakness: defeat 2 of these intruders and send them back to the frozen valley from which they came.",
        "objective_type": "npc_combat",
        "objective_value": 2,
        "rewards": {"spirit_stones": 380, "sect_contribution": 32},
        "emoji": "🌨️",
        "is_active": True,
        "sect_id": "frozen_peak",
    },
    {
        "id": 624,
        "name": "The Broken Oath of Ice",
        "type": "sect",
        "description": "A disciple shattered the sacred silence and leaked the House's frost arts to outsiders, endangering all of Frozen Peak. The Elders name you judge: face the transgressor in a single trial-spar, and then pronounce the verdict the ice demands.",
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "⚖️",
        "is_active": True,
        "sect_id": "frozen_peak",
        "choices": [
            {"id": "mercy", "label_key": "qc_624_mercy", "result_key": "qc_624_mercy_result",
             "karma_delta": 20, "reputation_delta": 0, "stones_delta": 250, "sect_contribution_delta": 35,
             "item_gained": None, "item_lost": None},
            {"id": "justice", "label_key": "qc_624_justice", "result_key": "qc_624_justice_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 350, "sect_contribution_delta": 50,
             "item_gained": None, "item_lost": None},
            {"id": "expose", "label_key": "qc_624_expose", "result_key": "qc_624_expose_result",
             "karma_delta": -20, "reputation_delta": 0, "stones_delta": 500, "sect_contribution_delta": 25,
             "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 625,
        "name": "The Roots That Wither",
        "type": "sect",
        "description": "The Sacred Garden of Ten Thousand Herbs sickens, and every Dao-flower bows its corolla as if weeping. The Elder asks you to kneel among the beds and meditate for 30 minutes, letting your qi sink to the roots like a gentle rain. Here in Yanshan, every breath you refine nourishes the life the Thousand Bloom swore to protect.",
        "objective_type": "cultivate",
        "objective_value": 30,
        "rewards": {"spirit_stones": 300, "sect_contribution": 25},
        "emoji": "🌸",
        "is_active": True,
        "sect_id": "thousand_bloom",
    },
    {
        "id": 626,
        "name": "Foul Hands in the Garden",
        "type": "sect",
        "description": "Two wandering cultivators raid the beds to tear out the rare spirit-herbs and bleed them into the shadow markets, trampling centuries of the Thousand Bloom's cultivation. Each root they defile bears a living Dao. Find and defeat the 2 marauders, driving them off before the sacred harvest becomes coin in greedy hands.",
        "objective_type": "npc_combat",
        "objective_value": 2,
        "rewards": {"spirit_stones": 360, "sect_contribution": 30},
        "emoji": "🌿",
        "is_active": True,
        "sect_id": "thousand_bloom",
    },
    {
        "id": 627,
        "name": "The Venom Beneath the Petal",
        "type": "sect",
        "description": "The truth reeks worse than the rot: a disciple of the Thousand Bloom secretly refined the garden's healing herbs into poison and sold it to outsiders, betraying the Sect's oath to life. Confront him in a single sparring trial; once he yields, the Elder lays the verdict in your hands.",
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "⚖️",
        "is_active": True,
        "sect_id": "thousand_bloom",
        "choices": [
            {"id": "mercy", "label_key": "qc_627_mercy", "result_key": "qc_627_mercy_result",
             "karma_delta": 20, "reputation_delta": 0, "stones_delta": 250, "sect_contribution_delta": 35,
             "item_gained": None, "item_lost": None},
            {"id": "justice", "label_key": "qc_627_justice", "result_key": "qc_627_justice_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 350, "sect_contribution_delta": 50,
             "item_gained": None, "item_lost": None},
            {"id": "expose", "label_key": "qc_627_expose", "result_key": "qc_627_expose_result",
             "karma_delta": -20, "reputation_delta": 0, "stones_delta": 500, "sect_contribution_delta": 25,
             "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 628,
        "name": "The Breath That Vanishes",
        "type": "sect",
        "description": "The Palace Elder points to the mat and says nothing more: meditate on the breath for 25 minutes, until your qi runs soundless and your presence dissolves like wind among the leaves. The first lesson of the House is not to strike, but to vanish. Still the breath and sharpen the wind before the Master calls.",
        "objective_type": "cultivate",
        "objective_value": 25,
        "rewards": {"spirit_stones": 300, "sect_contribution": 25},
        "emoji": "🌬️",
        "is_active": True,
        "sect_id": "silent_wind",
    },
    {
        "id": 629,
        "name": "The Blade Before Thunder",
        "type": "sect",
        "description": "Time is short: win 3 arena duels by striking first, while the lumbering Iron Mountain still raises its guard. Prove to the Master that the wind cuts before the foe ever feels the cold at his throat, for the rival House already moves its pieces across Yanshan.",
        "objective_type": "arena_win",
        "objective_value": 3,
        "rewards": {"spirit_stones": 400, "sect_contribution": 35},
        "emoji": "🗡️",
        "is_active": True,
        "sect_id": "silent_wind",
    },
    {
        "id": 630,
        "name": "The Envoy Alone in the Mist",
        "type": "sect",
        "description": "Now: you catch a lone Iron Mountain envoy carrying secrets that could humble the rival House. Win the single duel before he reaches the gates, and with the blade already raised, decide in a single breath. Strike for glory, or stay the wind.",
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "🌬️",
        "is_active": True,
        "sect_id": "silent_wind",
        "choices": [
            {"id": "glory", "label_key": "qc_630_glory", "result_key": "qc_630_glory_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 450, "sect_contribution_delta": 40,
             "item_gained": None, "item_lost": None},
            {"id": "prudence", "label_key": "qc_630_prudence", "result_key": "qc_630_prudence_result",
             "karma_delta": 15, "reputation_delta": 0, "stones_delta": 250, "sect_contribution_delta": 50,
             "item_gained": None, "item_lost": None},
            {"id": "ruthless", "label_key": "qc_630_ruthless", "result_key": "qc_630_ruthless_result",
             "karma_delta": -20, "reputation_delta": 0, "stones_delta": 550, "sect_contribution_delta": 25,
             "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 631,
        "name": "The Noonday Sun Forgives Nothing",
        "type": "sect",
        "description": "At the peak of noon, when no shadow dares to exist, you sit upon the Blazing Sun pyre and meditate for twenty-five minutes, drawing the fire of the star down into your core until every weakness burns and crumbles to ash. The Elder watches in silence: only a qi that has endured the noonday fire deserves to carry this Sect's name across Fenghuo.",
        "objective_type": "cultivate",
        "objective_value": 25,
        "rewards": {"spirit_stones": 300, "sect_contribution": 25},
        "emoji": "☀️",
        "is_active": True,
        "sect_id": "blazing_sun",
    },
    {
        "id": 632,
        "name": "Drag the Mist Into the Light",
        "type": "sect",
        "description": "The Azure Cloud Sect hides its cowardice behind its eternal mist, refusing to face the Sun head-on. The Elder commands: go to the arena and win three duels, tearing those cultivators out of their fog and exposing them under the light where no shadow can lie.",
        "objective_type": "arena_win",
        "objective_value": 3,
        "rewards": {"spirit_stones": 420, "sect_contribution": 35},
        "emoji": "🔆",
        "is_active": True,
        "sect_id": "blazing_sun",
    },
    {
        "id": 633,
        "name": "The Cornered Shadow Beneath the Sun",
        "type": "sect",
        "description": "You have cornered the Azure Cloud disciple who spat upon the name of the Blazing Sun, and now he trembles with no mist left to hide in. Win this single duel and, with your blade at his throat, judge his fate beneath the all-seeing star.",
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "☀️",
        "is_active": True,
        "sect_id": "blazing_sun",
        "choices": [
            {"id": "glory", "label_key": "qc_633_glory", "result_key": "qc_633_glory_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 450, "sect_contribution_delta": 40,
             "item_gained": None, "item_lost": None},
            {"id": "prudence", "label_key": "qc_633_prudence", "result_key": "qc_633_prudence_result",
             "karma_delta": 15, "reputation_delta": 0, "stones_delta": 250, "sect_contribution_delta": 50,
             "item_gained": None, "item_lost": None},
            {"id": "ruthless", "label_key": "qc_633_ruthless", "result_key": "qc_633_ruthless_result",
             "karma_delta": -20, "reputation_delta": 0, "stones_delta": 550, "sect_contribution_delta": 25,
             "item_gained": None, "item_lost": None},
        ],
    },
    {
        "id": 634,
        "name": "The Echo of the Abyss",
        "type": "sect",
        "description": "A whisper of buried treasure rises from the depths of Moyu, sweet as cracked bone. What Heaven rejects, the Abyss keeps. Sink into meditation for 25 minutes and let the Abyss steer your divine sense toward the echo of forgotten gold.",
        "objective_type": "cultivate",
        "objective_value": 25,
        "rewards": {"spirit_stones": 350, "sect_contribution": 25},
        "emoji": "🌀",
        "is_active": True,
        "sect_id": "abyssal_depths",
    },
    {
        "id": 635,
        "name": "The Sealed Vault",
        "type": "sect",
        "description": "The echo ends at a vault driven shut by an ancestral seal, hungry for any hand that dares. Heaven gives a demon nothing freely: break through ten dungeon floors and tear away the seal's wards, floor by floor, until the forbidden qi within recognizes its master.",
        "objective_type": "dungeon_floor",
        "objective_value": 10,
        "rewards": {"spirit_stones": 400, "sect_contribution": 30},
        "emoji": "🔓",
        "is_active": True,
        "sect_id": "abyssal_depths",
    },
    {
        "id": 636,
        "name": "The Price of Gold",
        "type": "sect",
        "description": "The vault yawns open and the forbidden treasure pulses, but it demands a price paid in soul, and a disciple of Jade Harmony, your eternal rival, reaches for the same prize. Best them in a single confrontation, then choose: devour it all, master the thirst, or share with the House.",
        "objective_type": "npc_combat",
        "objective_value": 1,
        "rewards": {"spirit_stones": 200},
        "emoji": "💰",
        "is_active": True,
        "sect_id": "abyssal_depths",
        "choices": [
            {"id": "seize", "label_key": "qc_636_seize", "result_key": "qc_636_seize_result",
             "karma_delta": -30, "reputation_delta": 0, "stones_delta": 600, "sect_contribution_delta": 25,
             "item_gained": None, "item_lost": None},
            {"id": "restraint", "label_key": "qc_636_restraint", "result_key": "qc_636_restraint_result",
             "karma_delta": 20, "reputation_delta": 0, "stones_delta": 150, "sect_contribution_delta": 50,
             "item_gained": None, "item_lost": None},
            {"id": "share", "label_key": "qc_636_share", "result_key": "qc_636_share_result",
             "karma_delta": 0, "reputation_delta": 0, "stones_delta": 350, "sect_contribution_delta": 40,
             "item_gained": None, "item_lost": None},
        ],
    },
]


# QoL-Feedback 03/08 (report [jogador]) — ids cujo `objective_type` o seed runner tem
# autorização EXPLÍCITA para reescrever em DBs vivas (ver o bloco de SEED SYNC
# em run_quests_seeds). Hoje: as 10 quests de seita que descrevem um duelo
# contra um oponente NPC e que estavam presas em `sparring` (PvP consentido).
# MV-9 §P6 — a id 3 (daily "friendly spar") ENTRA. Ficava de fora por ser "PvP
# temático legítimo", mas a medição derrubou o argumento: 0 sparrings em 30d no
# main e 0 desde sempre no s2. Uma daily entregue a todos, todos os dias, e
# impossível de completar não é temática — é um dead-end diário (Lei §1, 4ª
# recorrência). ⚠️ Pôr a id aqui SOZINHA seria no-op: o sync só escreve quando
# `quest.objective_type != seed["objective_type"]`, portanto a seed da id 3
# (acima) mudou no MESMO commit. Como `track_quest` faz JOIN contra o CATÁLOGO,
# as PlayerQuest já materializadas em 0/1 passam a progredir na hora — sem
# migration e sem tocar em row de jogador.
_OBJECTIVE_TYPE_SYNC_IDS = (3, 602, 612, 615, 618, 621, 624, 627, 630, 633, 636)


async def run_quests_seeds(session):
    existing_ids = set((await session.execute(select(QuestCatalog.id))).scalars().all())
    added = 0

    for seed in QUEST_SEEDS:
        if seed["id"] in existing_ids:
            # Re-activate quest if it was deactivated (e.g. ID 5 — beast expedition)
            if seed["id"] == 5:
                stmt = select(QuestCatalog).where(QuestCatalog.id == seed["id"])
                quest = (await session.execute(stmt)).scalar_one_or_none()
                if quest and not quest.is_active:
                    quest.is_active = True
            continue

        quest = QuestCatalog(
            id=seed["id"],
            name=seed["name"],
            type=seed["type"],
            description=seed["description"],
            objective_type=seed["objective_type"],
            objective_value=seed["objective_value"],
            rewards=seed["rewards"],
            emoji=seed.get("emoji", "🎯"),
            is_active=seed.get("is_active", True),
            choices=seed.get("choices"),  # v16.3.5 — NULL for non-fork quests
            sect_id=seed.get("sect_id"),  # v16.4c — house tag (NULL = universal/non-sect)
        )
        session.add(quest)
        added += 1

    # v16.3.5 Karmic Crossroads — SEED SYNC for the `choices` JSONB onto EXISTING
    # rows. The loop above is insert-only for known IDs (CLAUDE.md Lei §4), so
    # without this block the live DB (quests 1-16 already present) would never
    # receive the moral forks. Idempotent: re-running only re-writes identical
    # JSONB (the `!=` guard skips no-op writes). Pattern mirrors alchemy_seeds'
    # _PILL_FORCE_UPDATES.
    choice_updates = 0
    for seed in QUEST_SEEDS:
        if "choices" not in seed or seed["id"] not in existing_ids:
            continue  # brand-new rows already got `choices` via the insert above
        quest = (await session.execute(
            select(QuestCatalog).where(QuestCatalog.id == seed["id"])
        )).scalar_one_or_none()
        if quest is not None and quest.choices != seed["choices"]:
            quest.choices = seed["choices"]
            choice_updates += 1

    # QoL-Feedback 03/08 (report [jogador]) — SEED SYNC do `objective_type` para rows
    # EXISTENTES. As 10 quests de seita com narrativa de duelo contra um NPC
    # (602 universal + as 9 de julgamento) nasceram `sparring`, que SÓ avança no
    # settle de um duelo consentido entre DOIS jogadores vivos
    # (core/pvp_duel_settle.py:187-188 · handlers/combat.py). Num servidor de 3
    # ativos isso é dead-end (Lei §1) — e a narrativa manda lutar contra um
    # discípulo NPC, exatamente o que NÃO contava. Trocado para `npc_combat`
    # (tracker da caça/desafio a NPC: pve_duel_settle.py:227 · webserver.py:16578
    # · handlers/combat.py:2518). 3ª recorrência da classe (2× já corrigidas nos
    # storylets, ambas por report do [jogador] — lição MV-6).
    #
    # O loop de cima é insert-only para ids conhecidos, logo mudar o seed NÃO
    # propaga para DBs vivas: sem este bloco a quest do jogador continuava
    # impossível. Como `track_quest` lê o objective_type do CATÁLOGO via join
    # (core/quest_engine.py:236-244), as PlayerQuest já materializadas (a do [jogador]
    # está 0/1) passam a progredir de imediato — zero migration, zero escrita em
    # row de jogador. Idempotente (guard `!=`).
    #
    # A allowlist é deliberada e não um `for` genérico: assim uma futura edição
    # de seed nunca reescreve em silêncio o objetivo de uma quest viva — quem
    # quiser propagar uma mudança tem de a declarar aqui, com data e motivo.
    objective_updates = 0
    for qid in _OBJECTIVE_TYPE_SYNC_IDS:
        seed = next((s for s in QUEST_SEEDS if s["id"] == qid), None)
        if seed is None or qid not in existing_ids:
            continue  # rows novas já nasceram certas pelo insert acima
        quest = (await session.execute(
            select(QuestCatalog).where(QuestCatalog.id == qid)
        )).scalar_one_or_none()
        if quest is not None and quest.objective_type != seed["objective_type"]:
            quest.objective_type = seed["objective_type"]
            objective_updates += 1

    # MV-9 §P6 — o TEXTO da id 3 tem de viajar com o objetivo.
    # Medido em produção depois do deploy de 06/08 20:41 UTC: o sync acima
    # converteu a quest para `npc_combat` nas 2 DBs (destravando 234 rows
    # abertas no main + 14 no s2), mas escreve APENAS `objective_type` — o
    # `name` continuava "Participate in Sparring" e a `description` continuava
    # "a friendly sparring match". O jogador lia que tinha de treinar com outra
    # pessoa e completava batendo num NPC: o objetivo passou a ser honesto e o
    # texto ficou a mentir. Não há `q_3_name`/`q_3_desc` em i18n — estas strings
    # do seed são LITERALMENTE o que a tela imprime.
    # Deliberadamente restrito à id 3: nenhuma outra quest tem o texto tocado,
    # para uma edição futura de seed nunca reescrever em silêncio o enunciado de
    # uma quest viva. Idempotente (guard `!=`).
    text_updates = 0
    _q3seed = next((s for s in QUEST_SEEDS if s["id"] == 3), None)
    if _q3seed is not None and 3 in existing_ids:
        _q3 = (await session.execute(
            select(QuestCatalog).where(QuestCatalog.id == 3)
        )).scalar_one_or_none()
        if _q3 is not None and (_q3.name != _q3seed["name"]
                                or _q3.description != _q3seed["description"]):
            _q3.name = _q3seed["name"]
            _q3.description = _q3seed["description"]
            text_updates += 1
    if text_updates:
        logger.info("⚔️ MV-9 — texto da daily id 3 alinhado ao objetivo "
                    "(dizia 'sparring', o objetivo já era npc_combat)")

    if added:
        logger.info("🎯 Seeded %d new quests (skipped %d existing)", added, len(QUEST_SEEDS) - added)
    if choice_updates:
        logger.info("⚖️ Karmic Crossroads — synced moral choices onto %d existing quest(s)", choice_updates)
    if objective_updates:
        logger.info("⚔️ QoL 03/08 — objective_type sincronizado em %d quest(s) de seita "
                    "(sparring → npc_combat: solo-completável)", objective_updates)

    # TEC-1 gate (2026-07-26) — dívida Pedra 2 paga: o Q634 (beat 1 da arc da
    # Abyssal Depths) nasceu SEM `sect_contribution` no reward (o único dos 18
    # beats não-fork; _verify_sect_library acusava). Sync pontual espelhando o
    # bloco de `choices` acima: só o 634, só se ainda faltar a key (melhoria
    # estrita — ADICIONA contribuição a quem ainda vai reivindicar; nada é
    # retirado de ninguém). Fresh worlds já nascem certos pelo seed corrigido.
    q634 = next((s for s in QUEST_SEEDS if s["id"] == 634), None)
    if q634 is not None and 634 in existing_ids:
        quest = (await session.execute(
            select(QuestCatalog).where(QuestCatalog.id == 634)
        )).scalar_one_or_none()
        if quest is not None and "sect_contribution" not in (quest.rewards or {}):
            quest.rewards = dict(q634["rewards"])
            logger.info("📿 Q634 reward sync — sect_contribution adicionada (dívida Pedra 2)")

    await session.commit()
