import { useEffect, useRef } from "react";
import { useLanguage } from "@/hooks/useLanguage";
import { Orbit, FlaskConical, Sparkles, CloudLightning, Swords, PawPrint, Infinity, Coins,
         Globe2, Building2, BookLock, Hammer } from "lucide-react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

// ─── Feature card icon + accent colour config ─────────────────────────────────
// ⚠️ Indexado por POSIÇÃO contra `t.features.items`. Um item sem config aqui
// era um crash (`cfg.color` de undefined) — por isso há fallback no acesso.
// Ordem: cultivo · mundo vivo · cidades · 天时 · tribulação · alquimia ·
//        jiānghú · bibliotecas · corpo · bestas/masmorras · ofício · economia
const featureConfig = [
  { icon: <Orbit className="w-8 h-8" />, color: "#FFD700", shadow: "rgba(255,215,0,0.55)" },
  { icon: <Globe2 className="w-8 h-8" />, color: "#4ade80", shadow: "rgba(74,222,128,0.55)" },
  { icon: <Building2 className="w-8 h-8" />, color: "#f5c97a", shadow: "rgba(245,201,122,0.55)" },
  { icon: <CloudLightning className="w-8 h-8" />, color: "#38bdf8", shadow: "rgba(56,189,248,0.55)", lightning: true },
  { icon: <Sparkles className="w-8 h-8" />, color: "#a78bfa", shadow: "rgba(167,139,250,0.55)" },
  { icon: <FlaskConical className="w-8 h-8" />, color: "#34d399", shadow: "rgba(52,211,153,0.55)" },
  { icon: <Swords className="w-8 h-8" />, color: "#f87171", shadow: "rgba(248,113,113,0.55)" },
  { icon: <BookLock className="w-8 h-8" />, color: "#818cf8", shadow: "rgba(129,140,248,0.55)" },
  { icon: <Hammer className="w-8 h-8" />, color: "#fb923c", shadow: "rgba(251,146,60,0.55)" },
  { icon: <PawPrint className="w-8 h-8" />, color: "#22d3ee", shadow: "rgba(34,211,238,0.55)" },
  { icon: <Infinity className="w-8 h-8" />, color: "#e2e8f0", shadow: "rgba(226,232,240,0.55)" },
  { icon: <Coins className="w-8 h-8" />, color: "#fbbf24", shadow: "rgba(251,191,36,0.55)" },
];
const FEATURE_FALLBACK = featureConfig[0];

// ─── Mini canvas particle burst on hover ─────────────────────────────────────
const spawnBurst = (canvas: HTMLCanvasElement, color: string) => {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  canvas.width = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;

  type P = { x: number; y: number; vx: number; vy: number; life: number; r: number };
  const pts: P[] = [];
  for (let i = 0; i < 22; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 1.5 + Math.random() * 3;
    pts.push({ x: cx, y: cy, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, life: 1, r: 1.5 + Math.random() * 2.5 });
  }

  const draw = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    pts.forEach((p) => {
      p.x += p.vx;
      p.y += p.vy;
      p.vy -= 0.04;
      p.life -= 0.03;
      if (p.life <= 0) return;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * p.life, 0, Math.PI * 2);
      ctx.fillStyle = color + Math.floor(p.life * 255).toString(16).padStart(2, "0");
      ctx.fill();
    });
    if (pts.some((p) => p.life > 0)) requestAnimationFrame(draw);
    else ctx.clearRect(0, 0, canvas.width, canvas.height);
  };
  draw();
};

const FeaturesSection = () => {
  const { t } = useLanguage();
  const sectionRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  // GSAP ScrollTrigger for staggered card entrance
  useEffect(() => {
    const ctx = gsap.context(() => {
      // Title reveal
      if (titleRef.current) {
        gsap.fromTo(
          titleRef.current,
          { y: 30, opacity: 0 },
          {
            y: 0, opacity: 1, duration: 0.8, ease: "power3.out",
            scrollTrigger: { trigger: titleRef.current, start: "top 85%", once: true },
          }
        );
      }
      // Cards stagger
      if (gridRef.current) {
        gsap.fromTo(
          gridRef.current.querySelectorAll(".feature-card"),
          { y: 50, opacity: 0, rotateX: 12 },
          {
            y: 0, opacity: 1, rotateX: 0, duration: 0.75, stagger: 0.08, ease: "power3.out",
            scrollTrigger: { trigger: gridRef.current, start: "top 80%", once: true },
          }
        );
      }
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section id="features" className="py-24 px-4 relative" ref={sectionRef}>
      {/* Ambient glows */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/3 -left-20 w-96 h-96 rounded-full bg-primary/4 blur-3xl" />
        <div className="absolute bottom-1/4 -right-20 w-96 h-96 rounded-full bg-celestial/4 blur-3xl" />
      </div>

      <div className="container mx-auto max-w-6xl relative z-10">
        <h2
          ref={titleRef}
          className="font-cinzel text-3xl sm:text-4xl md:text-5xl text-center mb-4 text-gold-gradient glow-gold"
          style={{ opacity: 0 }}
        >
          {t.features.title}
        </h2>
        <p className="text-center text-muted-foreground mb-16 max-w-2xl mx-auto text-sm sm:text-base">
          {t.features.subtitle}
        </p>

        <div ref={gridRef} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {t.features.items.map((item, i) => {
            const cfg = featureConfig[i] ?? FEATURE_FALLBACK;
            return (
              <div
                key={i}
                className="feature-card group relative p-7 rounded-2xl border border-white/8 bg-black/40 backdrop-blur-md hover:bg-black/60 transition-all duration-500 hover:-translate-y-3 overflow-hidden cursor-default"
                style={{
                  opacity: 0,
                  borderColor: "rgba(255,255,255,0.08)",
                  boxShadow: "none",
                  transition: "transform 0.4s cubic-bezier(0.2,0.8,0.2,1), box-shadow 0.4s ease, border-color 0.4s ease",
                }}
                onMouseEnter={(e) => {
                  const el = e.currentTarget as HTMLElement;
                  el.style.borderColor = cfg.color + "50";
                  el.style.boxShadow = `0 0 35px ${cfg.shadow}, 0 20px 40px rgba(0,0,0,0.4)`;
                  const canvas = el.querySelector("canvas") as HTMLCanvasElement;
                  if (canvas) spawnBurst(canvas, cfg.color);
                }}
                onMouseLeave={(e) => {
                  const el = e.currentTarget as HTMLElement;
                  el.style.borderColor = "rgba(255,255,255,0.08)";
                  el.style.boxShadow = "none";
                }}
              >
                {/* Glass reflection */}
                <div className="absolute inset-0 bg-gradient-to-br from-white/8 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none" />

                {/* Particle burst canvas */}
                <canvas className="absolute inset-0 w-full h-full pointer-events-none" aria-hidden="true" />

                {/* Icon */}
                <div className="relative z-10 flex justify-center mb-6 group-hover:scale-110 group-hover:-rotate-3 transition-transform duration-500">
                  <div
                    className="p-4 rounded-full bg-black/60 border border-white/5 backdrop-blur-md shadow-inner"
                    style={{ color: cfg.color, filter: `drop-shadow(0 0 12px ${cfg.shadow})` }}
                  >
                    {/* Lightning flicker for Heavenly Tribulations */}
                    <div className={cfg.lightning ? "lightning-flicker" : ""}>
                      {cfg.icon}
                    </div>
                  </div>
                </div>

                <h3 className="font-cinzel text-lg font-bold text-foreground mb-2 relative z-10">{item.title}</h3>
                <p className="text-muted-foreground text-sm leading-relaxed relative z-10">{item.description}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;
