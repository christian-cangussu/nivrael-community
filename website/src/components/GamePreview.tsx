import { useEffect, useRef, useState, useCallback } from "react";
import { useLanguage } from "@/hooks/useLanguage";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const CB_MAX = 2300;

const GamePreview = () => {
  const { t } = useLanguage();
  const ACTIONS = t.gamePreview.actions;
  const ESTADOS = t.gamePreview.estados;
  const sectionRef = useRef<HTMLDivElement>(null);
  const tiltRef = useRef<HTMLDivElement>(null);
  const [cbVal, setCbVal] = useState(1800);
  const [estadoIdx, setEstadoIdx] = useState(0);
  const [activeBtn, setActiveBtn] = useState(0);
  const isVisible = useRef(false);

  const pct = Math.round((cbVal / CB_MAX) * 100);

  // IntersectionObserver — only run timers when section is in view
  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { isVisible.current = entry.isIntersecting; },
      { threshold: 0.1 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Combat counter — slowed to 1000ms, only runs when visible
  useEffect(() => {
    const iv = setInterval(() => {
      if (!isVisible.current) return;
      setCbVal(v => v + 50 >= CB_MAX ? 1000 : v + 50);
    }, 1000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    const iv = setInterval(() => {
      if (!isVisible.current) return;
      setEstadoIdx(i => (i + 1) % ESTADOS.length);
    }, 2800);
    return () => clearInterval(iv);
  }, [ESTADOS.length]);

  useEffect(() => {
    const iv = setInterval(() => {
      if (!isVisible.current) return;
      setActiveBtn(i => (i + 1) % ACTIONS.length);
    }, 1600);
    return () => clearInterval(iv);
  }, [ACTIONS.length]);

  // CSS-based tilt on mousemove — no RAF loop
  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!sectionRef.current || !tiltRef.current) return;
    const r = sectionRef.current.getBoundingClientRect();
    const mx = (e.clientX - r.left - r.width / 2) / r.width;
    const my = (e.clientY - r.top - r.height / 2) / r.height;
    const rx = my * 10;
    const ry = mx * -10;
    tiltRef.current.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg) scale(1.015)`;
  }, []);

  const handleMouseLeave = useCallback(() => {
    if (tiltRef.current) tiltRef.current.style.transform = `perspective(900px) rotateX(0deg) rotateY(0deg) scale(1)`;
  }, []);

  useEffect(() => {
    const ctx = gsap.context(() => {
      if (sectionRef.current)
        gsap.fromTo(sectionRef.current.querySelectorAll(".preview-reveal"),
          { y: 40, opacity: 0 },
          {
            y: 0, opacity: 1, duration: 0.85, stagger: 0.15, ease: "power3.out",
            scrollTrigger: { trigger: sectionRef.current, start: "top 75%", once: true }
          });
    });
    return () => ctx.revert();
  }, []);

  const btn = (color: string) => ({
    background: `rgba(${color},0.15)`,
    border: `1px solid rgba(${color},0.4)`,
    color: `rgba(${color},1)`,
    boxShadow: `0 0 8px rgba(${color},0.2)`,
  });

  return (
    <section
      className="py-24 px-4 relative overflow-hidden"
      ref={sectionRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      {/* Background Dao rings */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-[0.04]">
        <svg className="w-full h-full" viewBox="0 0 800 600" preserveAspectRatio="xMidYMid slice">
          <circle cx="400" cy="300" r="200" fill="none" stroke="#00D4AA" strokeWidth="1" strokeDasharray="8 4">
            <animateTransform attributeName="transform" type="rotate" from="0 400 300" to="360 400 300" dur="30s" repeatCount="indefinite" />
          </circle>
          <circle cx="400" cy="300" r="290" fill="none" stroke="#FFD700" strokeWidth="0.5" strokeDasharray="4 8">
            <animateTransform attributeName="transform" type="rotate" from="360 400 300" to="0 400 300" dur="50s" repeatCount="indefinite" />
          </circle>
        </svg>
      </div>

      <div className="container mx-auto max-w-4xl relative z-10">
        <h2 className="preview-reveal font-cinzel text-3xl sm:text-4xl text-center mb-4 text-gold-gradient glow-gold" style={{ opacity: 0 }}>
          {t.preview.title}
        </h2>
        <p className="preview-reveal text-center text-muted-foreground mb-12 max-w-2xl mx-auto" style={{ opacity: 0 }}>
          {t.preview.subtitle}
        </p>

        <div className="relative mx-auto max-w-xs preview-reveal" style={{ opacity: 0 }}>
          <div ref={tiltRef} style={{ transformStyle: "preserve-3d", transition: "transform 0.15s ease-out" }}>
            <div className="rounded-[2rem] border overflow-hidden"
              style={{ borderColor: "rgba(0,212,170,0.18)", background: "#17212b", boxShadow: "0 0 60px rgba(0,212,170,0.07),0 30px 70px rgba(0,0,0,0.7)" }}>

              {/* Status bar */}
              <div className="flex items-center justify-between px-4 py-1.5 border-b" style={{ background: "#0f1923", borderColor: "rgba(255,255,255,0.05)" }}>
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
                  <span className="text-[9px] font-mono" style={{ color: "rgba(255,255,255,0.35)" }}>Telegram</span>
                </div>
                <span className="text-[9px]" style={{ color: "rgba(255,255,255,0.25)" }}>⚡ 📶</span>
              </div>

              {/* Chat header */}
              <div className="flex items-center gap-2.5 px-3 py-2 border-b" style={{ background: "#0f1923", borderColor: "rgba(255,255,255,0.05)" }}>
                <div className="w-9 h-9 rounded-full flex items-center justify-center text-base flex-shrink-0"
                  style={{ background: "linear-gradient(135deg,rgba(255,215,0,0.55),rgba(123,47,190,0.55))" }}>☯️</div>
                <div>
                  <p className="text-xs font-bold" style={{ color: "#e2e8f0" }}>Nivrael: Path of Immortals</p>
                  <p className="text-[9px]" style={{ color: "rgba(0,212,170,0.8)" }}>bot • online</p>
                </div>
              </div>

              {/* Bot message bubble */}
              <div className="p-3 space-y-2 font-mono text-[10.5px]" style={{ background: "#17212b" }}>
                <div className="rounded-xl p-3 space-y-1.5" style={{ background: "#1e2b38", border: "1px solid rgba(255,255,255,0.06)" }}>

                  {/* Name + VIP */}
                  <div className="flex items-center justify-between">
                    <span className="font-bold" style={{ color: "#e2e8f0" }}>✦ White VIP 1</span>
                    <span className="text-[8px] px-1.5 py-0.5 rounded-full font-bold"
                      style={{ background: "rgba(255,215,0,0.12)", color: "#FFD700", border: "1px solid rgba(255,215,0,0.28)" }}>VIP 1</span>
                  </div>

                  <div className="flex items-center gap-1.5" style={{ color: "rgba(255,255,255,0.6)" }}>
                    <span>🏔️</span>
                    <span>{t.gamePreview.realm}: <span style={{ color: "#a78bfa" }}>Mortal VI</span></span>
                  </div>

                  <hr style={{ borderColor: "rgba(255,255,255,0.06)" }} />

                  {/* CB bar */}
                  <div className="space-y-1">
                    <div className="flex justify-between" style={{ color: "rgba(255,255,255,0.6)" }}>
                      <span>⚡ CB:</span>
                      <span style={{ color: "#00d4aa" }}>
                        {(cbVal / 1000).toFixed(1)}K / {(CB_MAX / 1000).toFixed(1)}K
                        <span className="ml-1" style={{ color: "rgba(255,255,255,0.35)" }}>({pct}%)</span>
                      </span>
                    </div>
                    <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.08)" }}>
                      <div className="h-full rounded-full transition-all duration-1000 ease-linear" style={{ width: `${pct}%`, background: "linear-gradient(90deg,#00d4aa,#FFD700)", boxShadow: "0 0 6px rgba(0,212,170,0.6)" }} />
                    </div>
                  </div>

                  <div style={{ color: "rgba(255,255,255,0.55)" }}>
                    <div className="flex gap-1.5"><span>🌿</span><span>{t.gamePreview.spiritRoot}: <span style={{ color: "#94a3b8" }}>{t.gamePreview.spiritRootLow}</span></span></div>
                    <div className="flex gap-1.5 mt-0.5"><span>📈</span><span>{t.gamePreview.cbPerHour}: <span style={{ color: "#fbbf24" }}>1.2K</span> <span style={{ color: "rgba(255,255,255,0.25)" }}>(✨ 🌿1.02)</span></span></div>
                  </div>

                  <hr style={{ borderColor: "rgba(255,255,255,0.06)" }} />

                  {/* Stats */}
                  <div className="grid grid-cols-2 gap-x-3 gap-y-0.5" style={{ color: "rgba(255,255,255,0.5)" }}>
                    <span>⚔️ {t.gamePreview.power}: <span style={{ color: "#f87171" }}>37</span></span>
                    <span>👻 {t.gamePreview.soul}: <span style={{ color: "#a78bfa" }}>10</span></span>
                    <span>👁️ {t.gamePreview.perception}: <span style={{ color: "#60a5fa" }}>10</span></span>
                    <span>🍀 {t.gamePreview.luck}: <span style={{ color: "#34d399" }}>10</span></span>
                  </div>

                  <hr style={{ borderColor: "rgba(255,255,255,0.06)" }} />

                  {/* Currencies */}
                  <div className="space-y-0.5" style={{ color: "rgba(255,255,255,0.5)" }}>
                    <div className="flex gap-1.5"><span>💎</span><span>{t.gamePreview.spiritualJade}: <span style={{ color: "#818cf8" }}>20</span></span></div>
                    <div className="flex gap-1.5"><span>🔮</span><span>{t.gamePreview.stones}: <span style={{ color: "#94a3b8" }}>931</span></span></div>
                    <div className="flex gap-1.5"><span>☯️</span><span>Qi: <span style={{ color: "#00d4aa" }}>100</span> / 100</span></div>
                  </div>

                  <hr style={{ borderColor: "rgba(255,255,255,0.06)" }} />

                  {/* Estado */}
                  <div className="space-y-0.5" style={{ color: "rgba(255,255,255,0.5)" }}>
                    <div className="flex gap-1.5">
                      <span>🏃</span>
                      <span>{t.gamePreview.status}: <span className="animate-pulse" style={{ color: "#fbbf24" }}>{ESTADOS[estadoIdx]}</span></span>
                    </div>
                    <div className="flex gap-1.5"><span>🐂</span><span>{t.gamePreview.companion}: <span style={{ color: "#34d399" }}>Thunder Ox (Lv.3)</span></span></div>
                    <div className="flex gap-1.5 text-[9.5px]"><span>⏳</span><span>{t.gamePreview.nextAdvance}: <span style={{ color: "#a78bfa" }}>≈24m 28s</span></span></div>
                  </div>
                </div>

                {/* Action buttons — exact bot layout */}
                <div className="space-y-1.5 mt-1">
                  {ACTIONS.map((label, idx) => (
                    <button key={label} className="w-full rounded-lg py-2 text-center text-[10px] font-bold transition-all duration-300"
                      style={activeBtn === idx
                        ? btn("0,212,170")
                        : { background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.07)", color: "rgba(255,255,255,0.6)" }}>
                      {label}
                    </button>
                  ))}
                  <div className="grid grid-cols-2 gap-1.5">
                    <button className="rounded-lg py-2 text-center text-[9px] font-bold" style={{ background: "rgba(255,215,0,0.1)", border: "1px solid rgba(255,215,0,0.25)", color: "#FFD700" }}>
                      {t.gamePreview.premium}
                    </button>
                    <button className="rounded-lg py-2 text-center text-[9px] font-bold" style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.55)" }}>
                      {t.gamePreview.ranking}
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    <button className="rounded-lg py-2 text-center text-[9px] font-bold" style={{ background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.2)", color: "#f87171" }}>
                      {t.gamePreview.celestialAnomalies}
                    </button>
                    <button className="rounded-lg py-2 text-center text-[9px] font-bold" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.4)" }}>
                      {t.gamePreview.help}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Floating labels */}
          <div className="hidden lg:flex absolute -right-48 top-20 items-center gap-2">
            <div className="w-12 h-px" style={{ background: "linear-gradient(90deg,rgba(0,212,170,0.5),transparent)" }} />
            <span className="text-[10px] font-mono whitespace-nowrap" style={{ color: "rgba(0,212,170,0.65)" }}>{t.gamePreview.cbTracking}</span>
          </div>
          <div className="hidden lg:flex absolute -left-44 top-40 items-center gap-2">
            <span className="text-[10px] font-mono whitespace-nowrap" style={{ color: "rgba(255,215,0,0.6)" }}>Thunder Ox companion</span>
            <div className="w-12 h-px" style={{ background: "linear-gradient(270deg,rgba(255,215,0,0.5),transparent)" }} />
          </div>
          <div className="hidden lg:flex absolute -right-40 bottom-48 items-center gap-2">
            <div className="w-12 h-px" style={{ background: "linear-gradient(90deg,rgba(192,132,252,0.5),transparent)" }} />
            <span className="text-[10px] font-mono whitespace-nowrap" style={{ color: "rgba(192,132,252,0.65)" }}>{t.gamePreview.idleProgress}</span>
          </div>
        </div>
      </div>
    </section>
  );
};

export default GamePreview;
