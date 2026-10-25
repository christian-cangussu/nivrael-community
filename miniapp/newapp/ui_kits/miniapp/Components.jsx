// Nivrael Miniapp UI Kit — Shared Components v2
// Immortal Idle Taoist-inspired aesthetic: ornate gold borders, warm parchment cards,
// atmospheric depth, icons BELOW labels in nav

const { useState, useEffect, useMemo } = React;

// ─── Helpers ─────────────────────────────────────────────────────────────────
function fmtNum(n) {
  n = Number(n) || 0;
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(2) + "B";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return Math.round(n).toString();
}
function fmtDuration(ms) {
  if (ms <= 0) return "—";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}
function realmColor(r) { return `var(--realm-${Math.min(r||0,10)})`; }
const REALM_GLYPHS = ["凡","氣","築","核","嬰","化","虛","合","大","渡","仙"];
const REALM_NAMES = ["Mortal","Qi Condensation","Foundation","Core Formation","Nascent Soul","Soul Transformation","Void Refinement","Body Integration","Mahayana","Tribulation","True Immortal"];

// ─── Background Glyphs ───────────────────────────────────────────────────────
function BgGlyphs() {
  return (
    <div style={{ position:"absolute", inset:0, pointerEvents:"none", overflow:"hidden", zIndex:0, fontFamily:"'Noto Serif SC',serif" }}>
      {[
        { g:"道", size:120, top:"6%",  left:"3%",  delay:0,   dur:16 },
        { g:"仙", size:150, top:"28%", right:"2%", delay:-6,  dur:19 },
        { g:"氣", size:95,  bottom:"20%", left:"6%", delay:-10, dur:13 },
        { g:"劍", size:130, bottom:"6%",  right:"8%", delay:-3,  dur:17 },
        { g:"龍", size:80,  top:"55%", left:"45%", delay:-7,  dur:22, opacity:.035 },
      ].map((s, i) => (
        <span key={i} style={{
          position:"absolute",
          color:`rgba(201,144,58,${s.opacity||.05})`,
          fontSize:s.size,
          fontWeight:700,
          animation:`drift-bg ${s.dur}s ease-in-out infinite`,
          animationDelay:s.delay+"s",
          top:s.top, bottom:s.bottom,
          left:s.left, right:s.right,
          lineHeight:1,
        }}>{s.g}</span>
      ))}
    </div>
  );
}

// ─── Atmospheric Background ───────────────────────────────────────────────────
function AtmoBg() {
  const stars = useMemo(() => Array.from({length:30},(_,i)=>({
    x:(((i*137.508)%1)*100).toFixed(2),
    y:(((i*73.13)%1)*55).toFixed(2),
    s:(.5+((i*31.7)%1)*.9).toFixed(2),
    d:((i*.7)%4).toFixed(1),
    dur:(1.5+i%3).toFixed(1),
  })),[]);

  return (
    <div style={{ position:"absolute", inset:0, pointerEvents:"none", zIndex:0, overflow:"hidden" }}>
      {/* Stars */}
      {stars.map((star,i)=>(
        <div key={i} style={{
          position:"absolute", left:star.x+"%", top:star.y+"%",
          width:star.s+"px", height:star.s+"px", borderRadius:"50%",
          background:"rgba(255,240,200,.7)",
          animation:`constellation-twinkle ${star.dur}s ease-in-out infinite`,
          animationDelay:star.d+"s",
        }} />
      ))}
      {/* Distant mountain silhouettes — 3 layers */}
      <svg viewBox="0 0 480 180" preserveAspectRatio="xMidYMax slice"
        style={{ position:"absolute", bottom:72, left:0, width:"100%", opacity:.18, pointerEvents:"none" }}>
        <path d="M0,180 L50,80 L90,110 L140,45 L190,90 L230,55 L275,85 L315,25 L360,65 L400,40 L445,70 L480,50 L480,180Z"
          fill="rgba(100,130,200,.5)" />
        <path d="M0,180 L35,100 L75,120 L120,70 L165,105 L205,78 L250,100 L295,60 L340,88 L385,62 L430,85 L480,72 L480,180Z"
          fill="rgba(70,100,170,.45)" />
        <path d="M0,180 L25,125 L65,140 L105,95 L150,128 L195,108 L240,125 L285,88 L325,112 L370,92 L415,108 L480,95 L480,180Z"
          fill="rgba(40,65,130,.5)" />
        {/* Floating pagoda silhouette */}
        <g transform="translate(320,20)" opacity=".5" fill="rgba(80,110,180,.6)">
          <rect x="-2" y="30" width="4" height="20"/>
          <polygon points="-10,30 10,30 5,20 -5,20"/>
          <polygon points="-14,20 14,20 8,8 -8,8"/>
          <polygon points="-8,8 8,8 4,0 -4,0"/>
        </g>
      </svg>
      {/* Top aurora glow */}
      <div style={{ position:"absolute", top:0, left:0, right:0, height:220,
        background:"radial-gradient(ellipse at 50% -10%,rgba(80,110,210,.22),transparent 65%)" }} />
      {/* Bottom warm glow */}
      <div style={{ position:"absolute", bottom:0, left:0, right:0, height:250,
        background:"radial-gradient(ellipse at 50% 110%,rgba(160,90,20,.14),transparent 60%)" }} />
      {/* Side vignette */}
      <div style={{ position:"absolute", inset:0,
        background:"radial-gradient(ellipse at 50% 50%,transparent 55%,rgba(0,0,0,.35) 100%)" }} />
    </div>
  );
}

// ─── Ornate Corner SVG ────────────────────────────────────────────────────────
function OrnateCorners({ color="rgba(201,144,58,.5)", size=14 }) {
  const c = color;
  const s = size;
  const corners = [
    { style:{ top:0, left:0 }, rotate:"0" },
    { style:{ top:0, right:0 }, rotate:"90" },
    { style:{ bottom:0, right:0 }, rotate:"180" },
    { style:{ bottom:0, left:0 }, rotate:"270" },
  ];
  return (
    <>
      {corners.map((corner, i) => (
        <svg key={i} width={s} height={s} viewBox="0 0 14 14"
          style={{ position:"absolute", ...corner.style, pointerEvents:"none", zIndex:1 }}>
          <g transform={`rotate(${corner.rotate},7,7)`} stroke={c} strokeWidth="1" fill="none">
            <path d="M1,7 L1,1 L7,1"/>
            <path d="M1,4 L4,1"/>
            <circle cx="1" cy="1" r="1" fill={c} stroke="none"/>
          </g>
        </svg>
      ))}
    </>
  );
}

// ─── Player Header ────────────────────────────────────────────────────────────
function PlayerHeader({ player }) {
  if (!player) return null;
  const rc = realmColor(player.realm);
  return (
    <div style={{
      position:"relative", zIndex:2,
      padding:"14px 16px 11px",
      display:"flex", flexDirection:"column", gap:9,
      borderBottom:"1px solid rgba(201,144,58,.2)",
      background:"linear-gradient(180deg,rgba(10,14,28,.95) 0%,rgba(10,14,28,.75) 80%,transparent 100%)",
    }}>
      {/* Top ornamental line */}
      <div style={{ position:"absolute", top:0, left:16, right:16, height:1,
        background:"linear-gradient(90deg,transparent,rgba(201,144,58,.5),rgba(201,144,58,.8),rgba(201,144,58,.5),transparent)" }} />

      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", gap:10 }}>
        <div style={{ minWidth:0 }}>
          <div style={{
            fontFamily:"'Cinzel',serif", fontSize:17, fontWeight:700, letterSpacing:.6,
            background:"linear-gradient(90deg,#fde68a,#f5c97a,#c9903a)",
            WebkitBackgroundClip:"text", backgroundClip:"text", WebkitTextFillColor:"transparent",
          }}>{player.dao_name}</div>
          {player.active_title && (
            <div style={{ fontFamily:"'Noto Serif SC',serif", fontSize:10, color:"rgba(201,144,58,.7)", marginTop:2 }}>
              ✦ {player.active_title}
            </div>
          )}
        </div>
        {/* Realm pill — ornate */}
        <div style={{
          display:"inline-flex", flexDirection:"column", alignItems:"center",
          padding:"5px 12px 4px",
          borderRadius:4, border:`1px solid ${rc}`,
          background:"rgba(0,0,0,.5)",
          boxShadow:`0 0 12px ${rc}44`,
          whiteSpace:"nowrap", gap:1,
          position:"relative", overflow:"hidden",
        }}>
          <div style={{ fontSize:15, fontFamily:"'Noto Serif SC',serif", fontWeight:700, color:rc, lineHeight:1 }}>
            {REALM_GLYPHS[player.realm||0]}
          </div>
          <div style={{ fontSize:9, color:rc, letterSpacing:.5, fontFamily:"'Cinzel',serif", fontWeight:600 }}>
            {REALM_NAMES[player.realm||0].split(" ")[0]} {player.sub_layer}
          </div>
        </div>
      </div>

      {/* Currencies row */}
      <div style={{ display:"flex", gap:12, fontSize:12, flexWrap:"wrap", alignItems:"center" }}>
        {[
          { ico:"💎", val:player.spirit_jade },
          { ico:"🪨", val:player.spirit_stones },
          ...(player.celestial_fragments>0 ? [{ ico:"✨", val:player.celestial_fragments }] : []),
        ].map((c,i)=>(
          <span key={i} style={{ display:"inline-flex", alignItems:"center", gap:4, color:"rgba(200,220,255,.6)" }}>
            {c.ico} <b style={{ color:"#e2eaff", fontWeight:600 }}>{fmtNum(c.val)}</b>
          </span>
        ))}
        <span style={{ marginLeft:"auto", fontSize:10, fontFamily:"'Cinzel',serif", color:"#f5c97a", letterSpacing:.3 }}>
          ✦ {player.spirit_root}
        </span>
      </div>

      {/* Bottom ornamental line */}
      <div style={{ position:"absolute", bottom:0, left:16, right:16, height:1,
        background:"linear-gradient(90deg,transparent,rgba(201,144,58,.3),rgba(201,144,58,.5),rgba(201,144,58,.3),transparent)" }} />
    </div>
  );
}

// ─── Bottom Nav ───────────────────────────────────────────────────────────────
const TAB_DEFS = [
  { key:"cultivation", ico:"☯️", label:"Cultivo" },
  { key:"sect",        ico:"🏯", label:"Seita" },
  { key:"world_boss",  ico:"🐉", label:"Chefe" },
  { key:"leaderboard", ico:"🏆", label:"Ranking" },
  { key:"inventory",   ico:"🎒", label:"Anel" },
  { key:"quests",      ico:"🎯", label:"Missões" },
  { key:"announcements",ico:"📜",label:"Notícias" },
];

function BottomNav({ tab, setTab }) {
  return (
    <div style={{
      position:"absolute", bottom:0, left:0, right:0, zIndex:5,
      flexDirection:"column",
    }}>
      {/* Ornate top divider — cloud/wave pattern */}
      <div style={{ position:"relative", height:20, overflow:"hidden", pointerEvents:"none" }}>
        <svg viewBox="0 0 375 20" preserveAspectRatio="none"
          style={{ position:"absolute", bottom:0, left:0, width:"100%", height:"100%" }}>
          <defs>
            <linearGradient id="divGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="rgba(201,144,58,0)"/>
              <stop offset="20%" stopColor="rgba(201,144,58,0.6)"/>
              <stop offset="50%" stopColor="rgba(245,201,122,0.9)"/>
              <stop offset="80%" stopColor="rgba(201,144,58,0.6)"/>
              <stop offset="100%" stopColor="rgba(201,144,58,0)"/>
            </linearGradient>
          </defs>
          <path d="M0,20 C30,14 55,6 80,10 C100,13 115,18 140,15 C158,12 172,5 188,8 C204,11 216,18 235,15 C255,12 270,5 290,8 C310,11 330,18 355,14 C368,11 375,8 375,8 L375,20Z"
            fill="rgba(10,14,28,0.97)"/>
          <path d="M0,20 C30,14 55,6 80,10 C100,13 115,18 140,15 C158,12 172,5 188,8 C204,11 216,18 235,15 C255,12 270,5 290,8 C310,11 330,18 355,14 C368,11 375,8 375,8"
            fill="none" stroke="url(#divGrad)" strokeWidth="1.2"/>
          {/* Small ornamental dots at peaks */}
          {[[80,10],[140,15],[188,8],[235,15],[290,8]].map(([x,y],i)=>(
            <circle key={i} cx={x} cy={y} r="1.5" fill="rgba(245,201,122,0.7)"/>
          ))}
        </svg>
      </div>

      {/* Tab bar */}
      <div style={{
        display:"flex", justifyContent:"space-around",
        padding:"4px 2px 12px",
        background:"rgba(10,14,28,.97)",
        borderTop:"1px solid rgba(201,144,58,.18)",
      }}>
        {TAB_DEFS.map(td => {
          const active = tab === td.key;
          return (
            <button key={td.key} onClick={() => setTab(td.key)} style={{
              flex:"0 0 auto", minWidth:48, background:"none", border:"none",
              display:"flex", flexDirection:"column", gap:2, alignItems:"center",
              cursor:"pointer", padding:"4px 2px", borderRadius:8,
              transition:"all .15s",
              position:"relative",
            }}>
              {/* Label ABOVE */}
              <div style={{
                fontSize:9, fontWeight:600, letterSpacing:.4,
                color: active ? "#f5c97a" : "#3d5a9e",
                fontFamily:"'Noto Sans',sans-serif",
                transition:"color .15s",
              }}>{td.label}</div>
              {/* Icon BELOW */}
              <div style={{
                fontSize:20, lineHeight:1,
                filter: active
                  ? "drop-shadow(0 0 6px rgba(245,201,122,.7)) drop-shadow(0 0 12px rgba(201,144,58,.4))"
                  : "opacity(.5)",
                opacity: active ? 1 : 0.45,
                transition:"filter .15s, opacity .15s",
              }}>{td.ico}</div>
              {/* Active indicator dot */}
              {active && (
                <div style={{
                  position:"absolute", bottom:-2, left:"50%", transform:"translateX(-50%)",
                  width:3, height:3, borderRadius:"50%", background:"#f5c97a",
                  boxShadow:"0 0 6px rgba(245,201,122,.8)",
                }} />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Card wrapper ─────────────────────────────────────────────────────────────
function Card({ children, style, ornate=true }) {
  return (
    <div style={{
      position:"relative",
      background:"linear-gradient(160deg,rgba(20,28,50,.92) 0%,rgba(12,16,30,.95) 100%)",
      border:"1px solid rgba(201,144,58,.25)",
      borderRadius:10,
      padding:"14px 14px 12px",
      marginBottom:10,
      animation:"fade-up .35s ease",
      overflow:"hidden",
      ...style,
    }}>
      {/* Inner top shimmer */}
      <div style={{ position:"absolute", top:0, left:0, right:0, height:1,
        background:"linear-gradient(90deg,transparent,rgba(201,144,58,.4),transparent)",
        pointerEvents:"none" }} />
      {/* Subtle texture overlay */}
      <div style={{ position:"absolute", inset:0, opacity:.025, pointerEvents:"none",
        backgroundImage:"repeating-linear-gradient(0deg,rgba(201,144,58,.5) 0px,transparent 1px,transparent 4px)",
        backgroundSize:"100% 4px" }} />
      {ornate && <OrnateCorners color="rgba(201,144,58,.4)" size={13} />}
      <div style={{ position:"relative", zIndex:1 }}>{children}</div>
    </div>
  );
}

function CardTitle({ left, right }) {
  return (
    <div style={{
      display:"flex", justifyContent:"space-between", alignItems:"center",
      marginBottom:10, paddingBottom:8,
      borderBottom:"1px solid rgba(201,144,58,.15)",
    }}>
      <span style={{
        fontFamily:"'Cinzel',serif", fontSize:11, letterSpacing:1.2,
        textTransform:"uppercase", color:"rgba(201,144,58,.8)",
      }}>{left}</span>
      {right && (
        <span style={{
          fontFamily:"'Cinzel',serif", fontSize:11, fontWeight:600,
          color:"#f5c97a",
        }}>{right}</span>
      )}
    </div>
  );
}

// ─── Stat Grid ────────────────────────────────────────────────────────────────
function StatGrid({ stats }) {
  return (
    <div style={{ display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:7 }}>
      {stats.map((s, i) => (
        <div key={i} style={{
          background:"rgba(0,0,0,.35)",
          border:"1px solid rgba(201,144,58,.12)",
          borderRadius:7, padding:"8px 10px",
          position:"relative", overflow:"hidden",
        }}>
          <div style={{ position:"absolute", top:0, left:0, right:0, height:1,
            background:"linear-gradient(90deg,transparent,rgba(201,144,58,.2),transparent)" }} />
          <div style={{ fontSize:9.5, color:"rgba(110,137,191,.8)", textTransform:"uppercase", letterSpacing:.8, fontFamily:"'Noto Sans',sans-serif" }}>{s.label}</div>
          <div style={{ fontSize:14, fontWeight:600, marginTop:3, color: s.color || "#e2eaff", fontFamily:"'Noto Sans',sans-serif" }}>
            {s.value}{s.sub && <small style={{ color:"#6e89bf", fontSize:10.5, fontWeight:400 }}> {s.sub}</small>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Progress Bar ─────────────────────────────────────────────────────────────
function ProgressBar({ pct, variant="cult", height=8 }) {
  const grad = {
    cult: "linear-gradient(90deg,#a06020,#c9903a,#f5c97a)",
    qi:   "linear-gradient(90deg,#1e7a9e,#4cc4ff,#7be3ff)",
    hp:   "linear-gradient(90deg,#7f1d1d,#dc2626,#fca5a5)",
  }[variant];
  return (
    <div style={{ width:"100%", height, background:"rgba(0,0,0,.5)", borderRadius:height/2,
      overflow:"hidden", border:"1px solid rgba(201,144,58,.18)", position:"relative" }}>
      <div style={{ height:"100%", borderRadius:height/2, transition:"width .4s ease",
        width:Math.min(100,Math.max(0,pct))+"%", background:grad, position:"relative" }}>
        {/* Sheen */}
        <div style={{ position:"absolute", top:0, left:0, right:0, height:"50%",
          background:"rgba(255,255,255,.15)", borderRadius:height/2 }} />
      </div>
    </div>
  );
}

// ─── Badge ────────────────────────────────────────────────────────────────────
function Badge({ children, variant="jade" }) {
  const styles = {
    jade: { bg:"rgba(62,207,126,.15)", color:"#3ecf7e", border:"rgba(62,207,126,.3)" },
    warn: { bg:"rgba(245,158,11,.14)", color:"#f59e0b", border:"rgba(245,158,11,.3)" },
    red:  { bg:"rgba(229,83,75,.14)",  color:"#e5534b", border:"rgba(229,83,75,.3)" },
    gold: { bg:"rgba(201,144,58,.15)", color:"#f5c97a", border:"rgba(201,144,58,.35)" },
  }[variant] || {};
  return (
    <span style={{
      display:"inline-block", padding:"2px 8px", borderRadius:3,
      fontSize:9.5, fontWeight:600, letterSpacing:.3,
      background:styles.bg, color:styles.color, border:`1px solid ${styles.border}`,
      fontFamily:"'Cinzel',serif",
    }}>{children}</span>
  );
}

// ─── Cultivation Orb ──────────────────────────────────────────────────────────
function CultivationOrb({ realm=1, meditating=false }) {
  const r = Math.min(realm, 10);
  const rc = `var(--realm-${r})`;
  const glyph = meditating ? "氣" : "道";

  const orbGradients = {
    0: `radial-gradient(circle at 35% 30%,rgba(200,210,220,.4),transparent 45%),radial-gradient(circle at 50% 50%,#9ca3af,#4b5563 70%,#1f2937)`,
    1: `radial-gradient(circle at 35% 30%,rgba(200,230,255,.5),transparent 45%),radial-gradient(circle at 50% 50%,#60a5fa,#1d4ed8 70%,#0c1a4a)`,
    2: `radial-gradient(circle at 35% 30%,rgba(255,240,180,.5),transparent 45%),radial-gradient(circle at 50% 50%,#fbbf24,#92400e 70%,#3a1a05)`,
    3: `radial-gradient(circle at 35% 30%,rgba(230,200,255,.5),transparent 45%),radial-gradient(circle at 50% 50%,#a855f7,#6b21a8 70%,#2d0a5c)`,
    4: `radial-gradient(circle at 35% 30%,rgba(180,255,240,.5),transparent 45%),radial-gradient(circle at 50% 50%,#2dd4bf,#0f766e 70%,#042f2e)`,
    5: `radial-gradient(circle at 35% 30%,rgba(180,210,255,.5),transparent 45%),radial-gradient(circle at 50% 50%,#3b82f6,#1e3a8a 70%,#0a1a4a)`,
    6: `radial-gradient(circle at 35% 30%,rgba(200,185,255,.5),transparent 45%),radial-gradient(circle at 50% 50%,#8b5cf6,#4c1d95 70%,#1e0a40)`,
    7: `radial-gradient(circle at 35% 30%,rgba(255,230,170,.5),transparent 45%),radial-gradient(circle at 50% 50%,#f59e0b,#92400e 70%,#3a1505)`,
    8: `radial-gradient(circle at 35% 30%,rgba(180,240,255,.5),transparent 45%),radial-gradient(circle at 50% 50%,#38bdf8,#0369a1 70%,#022d4a)`,
    9: `radial-gradient(circle at 35% 30%,rgba(255,240,150,.5),transparent 45%),radial-gradient(circle at 50% 50%,#eab308,#854d0e 70%,#362003)`,
    10:`radial-gradient(circle at 35% 30%,rgba(255,200,230,.6),transparent 40%),radial-gradient(circle at 70% 70%,rgba(201,144,58,.5),transparent 55%),radial-gradient(circle at 50% 50%,#f9a8d4,#c9903a 60%,#7c2d12)`,
  };

  const medOrb = `radial-gradient(circle at 35% 30%,rgba(255,255,255,.6),transparent 45%),radial-gradient(circle at 70% 70%,rgba(168,85,247,.55),transparent 60%),radial-gradient(circle at 50% 50%,#b478ff,#5f2da3 70%,#2a0e5e)`;

  const orbBg = meditating ? medOrb : (orbGradients[r] || orbGradients[1]);
  const orbGlow = meditating
    ? "0 0 60px rgba(168,85,247,.6),0 0 100px rgba(168,85,247,.25),inset 0 0 24px rgba(220,200,255,.4)"
    : r===10
      ? "0 0 60px rgba(244,114,182,.5),0 0 90px rgba(201,144,58,.3),inset 0 0 24px rgba(255,240,200,.4)"
      : `0 0 45px ${rc}77,0 0 70px ${rc}33,inset 0 0 18px rgba(255,255,255,.2)`;

  const particles = useMemo(() =>
    Array.from({length:16},() => ({
      left: 26+Math.random()*48+"%",
      dx: (Math.random()*70-35)+"px",
      delay: -(Math.random()*3)+"s",
      size: 2.5+Math.random()*2.5,
      color: meditating ? "rgba(200,160,255,.9)" : "rgba(170,210,255,.85)",
    })), [meditating]);

  return (
    <div style={{ position:"relative", width:200, height:200, margin:"6px auto 14px", display:"grid", placeItems:"center" }}>
      {/* Outer rotating ring */}
      <div style={{
        position:"absolute", inset:0, borderRadius:"50%",
        border:"1px solid rgba(201,144,58,.15)",
        animation:"orb-ring-out 6s ease-in-out infinite",
      }} />
      {/* Meditation rings */}
      {meditating && [0,1,2].map(i=>(
        <div key={i} style={{
          position:"absolute", inset:0, borderRadius:"50%",
          border:`1px solid rgba(${meditating?"168,85,247":"180,200,255"},.25)`,
          animation:`orb-ring-out 3s ease-out ${i}s infinite`,
        }} />
      ))}
      {/* Outer decorative ring — octagram-like ticks */}
      <svg style={{ position:"absolute", inset:0, width:"100%", height:"100%", opacity:.35 }}
        viewBox="0 0 200 200">
        <circle cx="100" cy="100" r="96" stroke="rgba(201,144,58,.4)" strokeWidth=".5" fill="none" strokeDasharray="4 8"/>
        {Array.from({length:8},(_,i)=>{
          const angle=(i/8)*Math.PI*2, r1=88, r2=96;
          const x1=100+r1*Math.cos(angle), y1=100+r1*Math.sin(angle);
          const x2=100+r2*Math.cos(angle), y2=100+r2*Math.sin(angle);
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(245,201,122,.7)" strokeWidth="1.5"/>;
        })}
      </svg>
      {/* The orb */}
      <div style={{
        position:"absolute", inset:22, borderRadius:"50%",
        background:orbBg,
        boxShadow:orbGlow,
        animation:`orb-breathe ${meditating?"2.6":"4"}s ease-in-out infinite`,
      }} />
      {/* Qi particles */}
      <div style={{ position:"absolute", inset:0, pointerEvents:"none" }}>
        {meditating && particles.map((p,i)=>(
          <span key={i} style={{
            position:"absolute", bottom:"50%", left:p.left,
            width:p.size, height:p.size, borderRadius:"50%",
            background:p.color, boxShadow:`0 0 5px ${p.color}`,
            animation:`qi-rise 3s ease-out ${p.delay} infinite`,
            "--dx": p.dx,
          }} />
        ))}
      </div>
      {/* Central glyph */}
      <div style={{
        position:"relative", zIndex:2,
        fontFamily:"'Noto Serif SC',serif", fontSize:50, fontWeight:700,
        color:"rgba(255,255,255,.92)", lineHeight:1,
        textShadow:`0 0 16px rgba(255,255,255,.6), 0 0 30px ${rc}`,
        pointerEvents:"none",
      }}>{glyph}</div>
    </div>
  );
}

// ─── Leaderboard Row ──────────────────────────────────────────────────────────
function LeaderRow({ rank, name, meta, isYou }) {
  const rankColors = { 1:"#ffd700", 2:"#c0c0c0", 3:"#cd7f32" };
  return (
    <div style={{
      display:"flex", alignItems:"center", gap:10,
      padding:"9px 6px 8px",
      borderBottom:"1px solid rgba(201,144,58,.1)",
      background: isYou ? "linear-gradient(90deg,rgba(201,144,58,.12),transparent)" : "transparent",
      borderRadius: isYou ? 6 : 0,
    }}>
      <div style={{ fontFamily:"'Cinzel',serif", fontSize:12, fontWeight:700,
        color: rankColors[rank]||"rgba(201,144,58,.7)", width:26, textAlign:"center" }}>
        {rank<=3 ? ["①","②","③"][rank-1] : `#${rank}`}
      </div>
      <div style={{ flex:1, fontSize:12.5, fontWeight:500, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{name}</div>
      <div style={{ fontSize:10.5, color:"#6e89bf", textAlign:"right", whiteSpace:"nowrap" }}>{meta}</div>
    </div>
  );
}

// ─── Loading ──────────────────────────────────────────────────────────────────
function Loading() {
  return (
    <div style={{ display:"grid", placeItems:"center", height:"100%", gap:14 }}>
      <div style={{
        fontFamily:"'Noto Serif SC',serif", fontSize:60,
        background:"linear-gradient(90deg,#c9903a,#f5c97a,#fde68a,#f5c97a,#c9903a)",
        backgroundSize:"200% 100%",
        WebkitBackgroundClip:"text", backgroundClip:"text", WebkitTextFillColor:"transparent",
        animation:"shimmer 2.5s linear infinite",
      }}>道</div>
      <div style={{ fontSize:11, letterSpacing:2, color:"rgba(201,144,58,.6)", textTransform:"uppercase",
        fontFamily:"'Cinzel',serif" }}>A canalizar Qi…</div>
    </div>
  );
}

// ─── Seg Control ─────────────────────────────────────────────────────────────
function SegControl({ options, value, onChange }) {
  return (
    <div style={{
      display:"flex", gap:3,
      background:"rgba(0,0,0,.4)",
      border:"1px solid rgba(201,144,58,.2)",
      borderRadius:7, padding:3, marginBottom:10,
    }}>
      {options.map(o => (
        <button key={o.value} onClick={() => onChange(o.value)} style={{
          flex:1,
          background: value===o.value
            ? "linear-gradient(180deg,rgba(201,144,58,.28),rgba(120,80,30,.4))"
            : "none",
          border: value===o.value ? "1px solid rgba(201,144,58,.35)" : "1px solid transparent",
          color: value===o.value ? "#f5c97a" : "#3d5a9e",
          fontSize:10.5, fontWeight:600, padding:"7px 0",
          borderRadius:5, cursor:"pointer", letterSpacing:.5,
          fontFamily:"'Cinzel',serif", transition:"all .15s",
        }}>{o.label}</button>
      ))}
    </div>
  );
}

// Export all to window
Object.assign(window, {
  fmtNum, fmtDuration, realmColor, REALM_GLYPHS, REALM_NAMES,
  BgGlyphs, AtmoBg, OrnateCorners,
  PlayerHeader, BottomNav, TAB_DEFS,
  Card, CardTitle, StatGrid, ProgressBar, Badge,
  CultivationOrb, LeaderRow, Loading, SegControl,
});
