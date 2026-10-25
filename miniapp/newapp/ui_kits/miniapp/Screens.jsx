// Nivrael Miniapp UI Kit — Tab Screens
// CultivationTab, SectTab, LeaderboardTab, InventoryTab, WorldBossTab, QuestsTab, AnnouncementsTab

const { useState, useEffect, useMemo } = React;

// ─── Mock Data ────────────────────────────────────────────────────────────────
const MOCK_PLAYER = {
  dao_name: "劍天明 · Jian Tianming",
  active_title: "Arcanista dos Picos Nevados",
  realm: 4, sub_layer: 7,
  spirit_jade: 1240, spirit_stones: 340000, celestial_fragments: 88,
  spirit_root: "Raiz Celestial",
  battle_power: 2400000, soul_strength: 180000, perception: 94000, luck: 12000,
  body_tempering_level: 3, prestige_level: 2,
};

const MOCK_CULT = {
  realm: 4, sub_layer: 7, is_meditating: false,
  cultivation_base: 720000, cb_threshold: 995000,
  qi: 5500, qi_capacity: 10000, qi_regen_mult: 2.5,
  meditation_type: "deep", meditation_multiplier: 3,
  meditation_end_ms: Date.now() + 2.5*3600*1000,
};

const MOCK_CULT_MED = { ...MOCK_CULT, is_meditating: true };

const MOCK_SECT = {
  sect: {
    name: "Seita dos Picos Nevados",
    bulletin: "O Caminho é longo. A vontade, eterna.",
    member_count: 18, max_members: 30,
    spirit_stones: 2800000,
    your_contribution: 145000,
    your_rank: "elder",
    buildings: { training:4, herb_garden:3, forge:2, library:3, defense:2, spirit_vein:1 },
  },
  members: [
    { name:"劍天明", rank:"master", realm:7, sub_layer:9, contribution:980000 },
    { name:"Lírio do Abismo", rank:"elder", realm:6, sub_layer:4, contribution:420000 },
    { name:"Jian Tianming", rank:"elder", realm:4, sub_layer:7, contribution:145000 },
    { name:"Espada Eterna", rank:"member", realm:3, sub_layer:2, contribution:88000 },
    { name:"Vento das Alturas", rank:"member", realm:2, sub_layer:9, contribution:52000 },
    { name:"Nuvem Solitária", rank:"member", realm:1, sub_layer:5, contribution:21000 },
  ],
};

const MOCK_BOSS = {
  boss: { name:"Dragão Celestial do Caos Primordial", emoji:"🐲", tier:"Ancestral", phase:"Fase II", hp:3500000000, current_hp:1190000000, expires_at_ms: Date.now()+4.37*3600*1000 },
  your_damage: 48200000,
  ranking: [
    { rank:1, name:"劍天明", total_damage:820000000, hits:1240, is_you:false },
    { rank:2, name:"Lírio do Abismo", total_damage:610000000, hits:980, is_you:false },
    { rank:3, name:"Espada Imortal", total_damage:390000000, hits:720, is_you:false },
    { rank:4, name:"Tu", total_damage:48200000, hits:94, is_you:true },
    { rank:5, name:"Nuvem das Estrelas", total_damage:32000000, hits:61, is_you:false },
  ],
};

const MOCK_LB = {
  cultivation: [
    { rank:1, name:"劍天明", realm_emoji:"仙", sub_layer:9, cultivation_base:12400000, prestige:3 },
    { rank:2, name:"Lírio do Abismo", realm_emoji:"渡", sub_layer:8, cultivation_base:9100000, prestige:2 },
    { rank:3, name:"Espada Imortal", realm_emoji:"大", sub_layer:6, cultivation_base:7800000, prestige:1 },
    { rank:4, name:"Vento Eterno", realm_emoji:"虛", sub_layer:4, cultivation_base:5200000, prestige:0 },
    { rank:5, name:"Nuvem das Alturas", realm_emoji:"合", sub_layer:2, cultivation_base:3900000, prestige:0 },
    { rank:47, name:"Jian Tianming", realm_emoji:"嬰", sub_layer:7, cultivation_base:720000, prestige:0 },
  ],
};

const MOCK_QUESTS = [
  { id:1, type:"daily", name:"Meditar 2 horas", emoji:"🧘", description:"Entra em estado de meditação por 2 horas seguidas.", objective_value:2, progress:2, is_completed:true, claimed:false, rewards:"500 Pedras" },
  { id:2, type:"daily", name:"Atacar o Chefe Mundial", emoji:"⚔️", description:"Inflige dano ao chefe mundial activo.", objective_value:1, progress:1, is_completed:true, claimed:true, rewards:"1.000 Pedras" },
  { id:3, type:"daily", name:"Contribuir para a Seita", emoji:"🏯", description:"Doa pedras de espírito à seita.", objective_value:5000, progress:3200, is_completed:false, claimed:false, rewards:"250 Pedras" },
  { id:4, type:"weekly", name:"Ascender de Camada", emoji:"✦", description:"Sobe pelo menos uma camada nesta semana.", objective_value:1, progress:0, is_completed:false, claimed:false, rewards:"5.000 Pedras + 💎10" },
];

const MOCK_ANNS = [
  { id:1, icon:"⚔️", rendered:"劍天明 ascendeu ao reino Imortal Verdadeiro!", created_at_ms: Date.now()-7200000 },
  { id:2, icon:"🐉", rendered:"Novo Chefe Mundial invocado: Dragão Celestial do Caos Primordial.", created_at_ms: Date.now()-18000000 },
  { id:3, icon:"🏯", rendered:"Seita Picos Nevados conquistou o 1º lugar no ranking de seitas!", created_at_ms: Date.now()-86400000 },
  { id:4, icon:"💊", rendered:"Nova pílula disponível na loja: Pílula da Grande Longevidade (Grau 6).", created_at_ms: Date.now()-2*86400000 },
  { id:5, icon:"✨", rendered:"Evento de Duplo Qi activo até domingo às 23h59.", created_at_ms: Date.now()-3*86400000 },
];

const MOCK_INV = {
  artifacts: [
    { id:1, grade:6, slot:"weapon", is_equipped:true },
    { id:2, grade:5, slot:"armor", is_equipped:true },
    { id:3, grade:4, slot:"ring", is_equipped:true },
    { id:4, grade:3, slot:"weapon", is_equipped:false },
    { id:5, grade:3, slot:"armor", is_equipped:false },
    { id:6, grade:2, slot:"ring", is_equipped:false },
    { id:7, grade:4, slot:"weapon", is_equipped:false },
    { id:8, grade:1, slot:"armor", is_equipped:false },
    { id:9, grade:2, slot:"ring", is_equipped:false },
  ],
  items: [
    { type:"pill", catalog_id:"great_longevity", quantity:12 },
    { type:"herb", catalog_id:"spirit_grass", quantity:8 },
    { type:"ore", catalog_id:"star_iron", quantity:3 },
    { type:"pill", catalog_id:"qi_recovery", quantity:1 },
    { type:"herb", catalog_id:"jade_lotus", quantity:24 },
    { type:"pill", catalog_id:"breakthrough", quantity:2 },
  ],
};

// ─── Cultivation Tab ──────────────────────────────────────────────────────────
function CultivationTab({ player, meditating: extMeditating }) {
  const [meditating, setMeditating] = useState(extMeditating !== undefined ? extMeditating : false);
  const data = meditating ? MOCK_CULT_MED : MOCK_CULT;
  const cbPct = (data.cultivation_base / data.cb_threshold) * 100;
  const qiPct = (data.qi / data.qi_capacity) * 100;
  const remainMs = meditating ? (data.meditation_end_ms - Date.now()) : 0;

  const medTypes = { light:"🧘 Leve", deep:"🔮 Profunda", void:"💜 Vazio", celestial_dao:"🌠 Celestial" };

  return (
    <div>
      <CultivationOrb realm={player.realm} meditating={meditating} />

      <Card>
        <CardTitle left="Cultivo" right={cbPct.toFixed(1)+"%"} />
        <ProgressBar pct={cbPct} variant="cult" />
        <div style={{ display:"flex", justifyContent:"space-between", marginTop:6, fontSize:11, color:"var(--muted)" }}>
          <span>{fmtNum(data.cultivation_base)} / {fmtNum(data.cb_threshold)}</span>
          <span>{REALM_NAMES[data.realm]}</span>
        </div>
      </Card>

      <Card>
        <CardTitle left="Qi" right={qiPct.toFixed(0)+"%"} />
        <ProgressBar pct={qiPct} variant="qi" />
        <div style={{ display:"flex", justifyContent:"space-between", marginTop:6, fontSize:11, color:"var(--muted)" }}>
          <span>{fmtNum(data.qi)} / {fmtNum(data.qi_capacity)}</span>
          {meditating && <Badge variant="jade">×{data.meditation_multiplier} qi/s</Badge>}
        </div>
      </Card>

      <Card>
        <CardTitle left="Meditação" />
        {meditating ? (
          <div>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <span style={{ fontSize:13, fontWeight:600 }}>{medTypes[data.meditation_type]}</span>
              <Badge variant="gold">×{data.meditation_multiplier}</Badge>
            </div>
            <div style={{ display:"flex", justifyContent:"space-between", marginTop:8, fontSize:12, color:"var(--muted)" }}>
              <span>Termina em</span>
              <b style={{ color:"var(--gold2)" }}>{fmtDuration(remainMs)}</b>
            </div>
            <button onClick={() => setMeditating(false)} style={{
              marginTop:12, width:"100%", padding:"9px", borderRadius:10,
              border:"1px solid rgba(229,83,75,.4)", background:"rgba(229,83,75,.12)",
              color:"#e5534b", fontFamily:"'Cinzel',serif", fontSize:12, cursor:"pointer",
            }}>Interromper Meditação</button>
          </div>
        ) : (
          <div>
            <div style={{ fontSize:12, color:"var(--muted)", marginBottom:10, textAlign:"center" }}>
              Escolhe o tipo de meditação para cultivar
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
              {Object.entries(medTypes).map(([k, label]) => (
                <button key={k} onClick={() => setMeditating(true)} style={{
                  padding:"8px", borderRadius:10, border:"1px solid var(--border)",
                  background:"linear-gradient(180deg,rgba(40,60,110,.6),rgba(20,32,60,.85))",
                  color:"var(--text)", fontSize:12, cursor:"pointer", fontFamily:"'Noto Sans',sans-serif",
                }}>{label}</button>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Card>
        <CardTitle left="Atributos" />
        <StatGrid stats={[
          { label:"Poder de Combate", value: fmtNum(player.battle_power) },
          { label:"Força da Alma", value: fmtNum(player.soul_strength) },
          { label:"Percepção", value: fmtNum(player.perception) },
          { label:"Sorte", value: fmtNum(player.luck) },
          { label:"Têmpera Corporal", value: "Nv "+player.body_tempering_level },
          { label:"Prestígio", value: "Nv "+player.prestige_level },
        ]} />
      </Card>
    </div>
  );
}

// ─── Sect Tab ─────────────────────────────────────────────────────────────────
function SectTab() {
  const s = MOCK_SECT.sect;
  const members = MOCK_SECT.members;
  const BUILDING_ICONS = { training:"⚔️", herb_garden:"🌿", forge:"⚒️", library:"📜", defense:"🛡️", spirit_vein:"💫" };
  const BUILDING_NAMES = { training:"Treino", herb_garden:"Jardim", forge:"Forja", library:"Biblioteca", defense:"Defesa", spirit_vein:"Veia Esp." };

  return (
    <div>
      <Card>
        <CardTitle left={s.name} right={`${s.member_count}/${s.max_members}`} />
        {s.bulletin && (
          <div style={{ fontSize:12, color:"var(--muted)", fontStyle:"italic", padding:"2px 0 10px", borderBottom:"1px dashed rgba(60,90,180,.2)", marginBottom:10 }}>
            "{s.bulletin}"
          </div>
        )}
        <StatGrid stats={[
          { label:"Tesouro", value:"🪨 "+fmtNum(s.spirit_stones) },
          { label:"Tua Contribuição", value: fmtNum(s.your_contribution) },
          { label:"Tua Posição", value: s.your_rank==="master"?"Mestre":s.your_rank==="elder"?"Ancião":"Membro" },
          { label:"Edifícios", value: Object.values(s.buildings).reduce((a,b)=>a+b,0) + " total" },
        ]} />
      </Card>

      <Card>
        <CardTitle left="Edifícios" />
        <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:8 }}>
          {Object.entries(s.buildings).map(([k, lvl]) => (
            <div key={k} style={{
              background:"rgba(0,0,0,.3)", border:"1px solid rgba(60,90,180,.18)",
              borderRadius:10, padding:"10px 8px", textAlign:"center",
            }}>
              <div style={{ fontSize:22 }}>{BUILDING_ICONS[k]}</div>
              <div style={{ fontSize:10, color:"var(--muted)", marginTop:4, textTransform:"uppercase", letterSpacing:.5 }}>{BUILDING_NAMES[k]}</div>
              <div style={{ fontSize:13, fontWeight:600, color: lvl>0?"var(--gold2)":"var(--muted2)", marginTop:2 }}>
                {lvl>0 ? "Nv "+lvl : "—"}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <CardTitle left="Membros" right={members.length} />
        {members.map((m, i) => (
          <div key={i} style={{
            display:"flex", alignItems:"center", gap:10, padding:"9px 4px",
            borderBottom: i<members.length-1 ? "1px dashed rgba(60,90,180,.15)" : "none",
          }}>
            <div style={{ fontFamily:"'Cinzel',serif", fontSize:13, fontWeight:600, color:[1,2,3].includes(i+1)?["#ffd700","#c0c0c0","#cd7f32"][i]:"var(--gold2)", width:26, textAlign:"center" }}>#{i+1}</div>
            <div style={{ flex:1, fontSize:13, fontWeight:500 }}>
              {m.name}{" "}
              {m.rank==="master" && <Badge variant="gold">Mestre</Badge>}
              {m.rank==="elder" && <Badge variant="warn">Ancião</Badge>}
            </div>
            <div style={{ fontSize:11, color:"var(--muted)", textAlign:"right" }}>
              {REALM_GLYPHS[m.realm]} {m.sub_layer} · {fmtNum(m.contribution)}
            </div>
          </div>
        ))}
      </Card>
    </div>
  );
}

// ─── Leaderboard Tab ──────────────────────────────────────────────────────────
function LeaderboardTab() {
  const [type, setType] = useState("cultivation");
  const entries = MOCK_LB.cultivation;
  return (
    <div>
      <SegControl value={type} onChange={setType} options={[
        { value:"cultivation", label:"Cultivo" },
        { value:"power", label:"Poder" },
        { value:"sects", label:"Seitas" },
      ]} />
      <Card>
        {entries.map((e, i) => (
          <div key={i}>
            <LeaderRow
              rank={e.rank}
              name={<span>{e.name}{e.prestige>0&&<Badge variant="jade" style={{marginLeft:6}}>P{e.prestige}</Badge>}</span>}
              meta={`${e.realm_emoji}${e.sub_layer} · ☯️ ${fmtNum(e.cultivation_base)}`}
              isYou={e.rank===47}
            />
          </div>
        ))}
      </Card>
    </div>
  );
}

// ─── Inventory Tab ────────────────────────────────────────────────────────────
function InventoryTab() {
  const [tooltip, setTooltip] = useState(null);
  const equipped = MOCK_INV.artifacts.filter(a=>a.is_equipped);
  const stash = MOCK_INV.artifacts.filter(a=>!a.is_equipped);
  const GRADE_COLORS = ["#9ca3af","#60a5fa","#3ecf7e","#a855f7","#f59e0b","#f472b6","#38bdf8","#f5c97a","#f472b6"];
  const SLOT_ICONS = { weapon:"🗡️", armor:"🛡️", ring:"💍" };

  return (
    <div>
      <Card>
        <CardTitle left="Equipado" right={`${equipped.length}/6`} />
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:6 }}>
          {equipped.map(a => (
            <div key={a.id} onClick={()=>setTooltip(tooltip===a.id?null:a.id)} style={{
              aspectRatio:1, background:"linear-gradient(180deg,rgba(40,55,90,.7),rgba(20,30,55,.9))",
              border:`1px solid var(--gold)`, borderRadius:8, display:"grid", placeItems:"center",
              position:"relative", boxShadow:"inset 0 0 8px rgba(201,144,58,.3)", cursor:"pointer",
            }}>
              <span style={{ fontSize:22 }}>{SLOT_ICONS[a.slot]||"🗡️"}</span>
              <span style={{ position:"absolute", left:4, top:2, fontSize:9, fontWeight:700, color:GRADE_COLORS[a.grade] }}>G{a.grade}</span>
              {tooltip===a.id && (
                <div style={{
                  position:"absolute", bottom:"110%", left:"50%", transform:"translateX(-50%)",
                  background:"rgba(13,20,34,.97)", border:"1px solid var(--gold)", borderRadius:10,
                  padding:"8px 12px", zIndex:10, whiteSpace:"nowrap", fontSize:11, color:"var(--text)",
                  boxShadow:"0 4px 20px rgba(0,0,0,.5)",
                }}>
                  <div style={{ fontFamily:"'Cinzel',serif", fontSize:12, color:"var(--gold2)", marginBottom:4 }}>Artefacto Grau {a.grade}</div>
                  <div style={{ color:"var(--muted)" }}>Slot: {a.slot}</div>
                  <div style={{ color:"var(--jade)", marginTop:2 }}>✦ Equipado</div>
                </div>
              )}
            </div>
          ))}
          {Array.from({length:6-equipped.length}).map((_,i)=>(
            <div key={i} style={{
              aspectRatio:1, background:"rgba(0,0,0,.2)", border:"1px dashed rgba(60,90,180,.3)",
              borderRadius:8, opacity:.3,
            }} />
          ))}
        </div>
      </Card>

      <Card>
        <CardTitle left="Anel Espacial — Artefactos" right={stash.length} />
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:6 }}>
          {stash.map(a=>(
            <div key={a.id} style={{
              aspectRatio:1, background:"linear-gradient(180deg,rgba(40,55,90,.7),rgba(20,30,55,.9))",
              border:"1px solid var(--border)", borderRadius:8, display:"grid", placeItems:"center", position:"relative",
            }}>
              <span style={{ fontSize:20 }}>{SLOT_ICONS[a.slot]||"🗡️"}</span>
              <span style={{ position:"absolute", left:4, top:2, fontSize:9, fontWeight:700, color:GRADE_COLORS[a.grade] }}>G{a.grade}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <CardTitle left="Itens" right={MOCK_INV.items.length} />
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:6 }}>
          {MOCK_INV.items.map((it,i)=>(
            <div key={i} style={{
              aspectRatio:1, background:"linear-gradient(180deg,rgba(40,55,90,.7),rgba(20,30,55,.9))",
              border:"1px solid var(--border)", borderRadius:8, display:"grid", placeItems:"center", position:"relative",
            }}>
              <span style={{ fontSize:20 }}>{it.type==="pill"?"💊":it.type==="herb"?"🌿":"⚒️"}</span>
              <span style={{ position:"absolute", right:4, bottom:2, fontSize:10, fontWeight:700, color:"var(--gold2)" }}>{it.quantity}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── World Boss Tab ───────────────────────────────────────────────────────────
function WorldBossTab() {
  const b = MOCK_BOSS.boss;
  const hpPct = (b.current_hp / b.hp) * 100;
  const remainMs = b.expires_at_ms - Date.now();

  return (
    <div>
      <Card>
        <div style={{ textAlign:"center", padding:"14px 0 8px" }}>
          <div style={{ fontSize:56, filter:"drop-shadow(0 0 16px rgba(255,80,80,.55))", lineHeight:1.1 }}>{b.emoji}</div>
          <div style={{ fontFamily:"'Cinzel',serif", fontSize:17, marginTop:8, letterSpacing:.3 }}>{b.name}</div>
          <div style={{ fontSize:10, color:"var(--gold2)", letterSpacing:1, textTransform:"uppercase", marginTop:3 }}>{b.tier} · {b.phase}</div>
        </div>
        <div style={{ marginTop:12, height:11, background:"rgba(255,255,255,.05)", borderRadius:8, overflow:"hidden", border:"1px solid rgba(229,83,75,.3)" }}>
          <div style={{ height:"100%", width:hpPct+"%", background:"linear-gradient(90deg,#991b1b,#dc2626,#ef4444)", borderRadius:8, transition:"width .5s ease" }} />
        </div>
        <div style={{ display:"flex", justifyContent:"space-between", marginTop:6, fontSize:12, color:"var(--muted)" }}>
          <span>{fmtNum(b.current_hp)} / {fmtNum(b.hp)} HP</span>
          <span>⏱️ {fmtDuration(remainMs)}</span>
        </div>
        <div style={{ display:"flex", justifyContent:"space-between", marginTop:12 }}>
          <span style={{ fontSize:12, color:"var(--muted)" }}>Teu dano</span>
          <b style={{ color:"var(--gold2)" }}>⚔️ {fmtNum(MOCK_BOSS.your_damage)}</b>
        </div>
      </Card>

      <Card>
        <CardTitle left="Top Cultivadores" />
        {MOCK_BOSS.ranking.map(r=>(
          <LeaderRow key={r.rank} rank={r.rank} name={r.name}
            meta={`⚔️ ${fmtNum(r.total_damage)} · ${r.hits}x`}
            isYou={r.is_you} />
        ))}
      </Card>
    </div>
  );
}

// ─── Quests Tab ───────────────────────────────────────────────────────────────
function QuestsTab() {
  const dailies = MOCK_QUESTS.filter(q=>q.type==="daily");
  const weeklies = MOCK_QUESTS.filter(q=>q.type==="weekly");

  function QuestRow({ q }) {
    const pct = q.objective_value>0 ? Math.min(100,(q.progress/q.objective_value)*100) : 0;
    return (
      <div style={{ display:"flex", flexDirection:"column", gap:5, padding:"10px 4px", borderBottom:"1px dashed rgba(60,90,180,.2)" }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <span style={{ fontSize:18 }}>{q.emoji}</span>
          <span style={{ flex:1, fontSize:13, fontWeight:600 }}>{q.name}</span>
          {q.claimed ? <Badge variant="jade">✓</Badge>
           : q.is_completed ? <Badge variant="warn">Pronta</Badge>
           : null}
        </div>
        <div style={{ fontSize:11, color:"var(--muted)" }}>{q.description}</div>
        <ProgressBar pct={pct} variant="cult" />
        <div style={{ fontSize:11, color:"var(--muted)", textAlign:"right" }}>
          {fmtNum(q.progress)} / {fmtNum(q.objective_value)}
        </div>
      </div>
    );
  }

  return (
    <div>
      {dailies.length>0 && (
        <Card>
          <CardTitle left="Diárias" right={`${dailies.filter(q=>q.is_completed).length}/${dailies.length}`} />
          {dailies.map(q=><QuestRow key={q.id} q={q} />)}
        </Card>
      )}
      {weeklies.length>0 && (
        <Card>
          <CardTitle left="Semanais" right={`${weeklies.filter(q=>q.is_completed).length}/${weeklies.length}`} />
          {weeklies.map(q=><QuestRow key={q.id} q={q} />)}
        </Card>
      )}
    </div>
  );
}

// ─── Announcements Tab ────────────────────────────────────────────────────────
function AnnouncementsTab() {
  function timeAgo(ms) {
    const diff = Date.now()-ms, s=Math.floor(diff/1000);
    if(s<60) return "agora";
    if(s<3600) return `há ${Math.floor(s/60)}min`;
    if(s<86400) return `há ${Math.floor(s/3600)}h`;
    return `há ${Math.floor(s/86400)}d`;
  }
  return (
    <div>
      <Card>
        <CardTitle left="Anúncios Globais" right={MOCK_ANNS.length} />
        {MOCK_ANNS.map(a=>(
          <div key={a.id} style={{ display:"flex", gap:10, padding:"10px 2px", borderBottom:"1px dashed rgba(60,90,180,.18)", animation:"fade-up .3s ease" }}>
            <span style={{ fontSize:20, flexShrink:0 }}>{a.icon}</span>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:12.5, lineHeight:1.4 }}>{a.rendered}</div>
              <div style={{ fontSize:10, color:"var(--muted)", marginTop:3 }}>{timeAgo(a.created_at_ms)}</div>
            </div>
          </div>
        ))}
      </Card>
    </div>
  );
}

// Export all
Object.assign(window, {
  MOCK_PLAYER,
  CultivationTab, SectTab, LeaderboardTab, InventoryTab,
  WorldBossTab, QuestsTab, AnnouncementsTab,
});
