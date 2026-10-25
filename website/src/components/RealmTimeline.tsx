import { useEffect, useRef, useState } from "react";
import { useLanguage } from "@/hooks/useLanguage";
import { Sprout, Droplet, Layers, CircleDot, Ghost, Wind, Tornado, Zap, Sun, CloudLightning, Crown } from "lucide-react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import LazyImage from "./LazyImage";

gsap.registerPlugin(ScrollTrigger);

interface RealmColor {
  border: string;
  glowColor: string;
  text: string;
  bg: string;
  imgUrl?: string;
  progressColor: string;
}

const realmColors: RealmColor[] = [
  { border: "rgba(160,160,160,0.3)", glowColor: "rgba(200,200,200,0.3)", text: "#cbd5e1", bg: "rgba(100,100,100,0.08)", imgUrl: "/realm-mortal.png", progressColor: "#94a3b8" },
  { border: "rgba(0,212,170,0.35)", glowColor: "rgba(0,212,170,0.35)", text: "#00d4aa", bg: "rgba(0,212,170,0.07)", imgUrl: "/realm-qi.png", progressColor: "#00d4aa" },
  { border: "rgba(96,165,250,0.35)", glowColor: "rgba(96,165,250,0.35)", text: "#60a5fa", bg: "rgba(96,165,250,0.07)", imgUrl: "/realm-foundation.png", progressColor: "#60a5fa" },
  { border: "rgba(167,139,250,0.4)", glowColor: "rgba(167,139,250,0.45)", text: "#a78bfa", bg: "rgba(167,139,250,0.07)", imgUrl: "/realm-core.png", progressColor: "#a78bfa" },
  { border: "rgba(196,181,253,0.35)", glowColor: "rgba(196,181,253,0.35)", text: "#c4b5fd", bg: "rgba(196,181,253,0.07)", imgUrl: "/realm-nascent-soul.png", progressColor: "#c4b5fd" },
  { border: "rgba(232,121,249,0.35)", glowColor: "rgba(232,121,249,0.35)", text: "#e879f9", bg: "rgba(232,121,249,0.07)", imgUrl: "/realm-soul-transformation.png", progressColor: "#e879f9" },
  { border: "rgba(45,212,191,0.35)", glowColor: "rgba(45,212,191,0.35)", text: "#2dd4bf", bg: "rgba(45,212,191,0.07)", imgUrl: "/realm-void-refinement.png", progressColor: "#2dd4bf" },
  { border: "rgba(255,215,0,0.35)", glowColor: "rgba(255,215,0,0.35)", text: "#FFD700", bg: "rgba(255,215,0,0.07)", imgUrl: "/realm-body-integration.png", progressColor: "#FFD700" },
  { border: "rgba(251,191,36,0.35)", glowColor: "rgba(251,191,36,0.35)", text: "#fbbf24", bg: "rgba(251,191,36,0.07)", imgUrl: "/realm-mahayana.png", progressColor: "#fbbf24" },
  { border: "rgba(249,115,22,0.45)", glowColor: "rgba(249,115,22,0.55)", text: "#fb923c", bg: "rgba(249,115,22,0.09)", imgUrl: "/realm-tribulation.png", progressColor: "#fb923c" },
  // True Immortal — special
  { border: "rgba(255,215,0,0.6)", glowColor: "rgba(255,215,0,0.6)", text: "#FFD700", bg: "rgba(255,215,0,0.1)", imgUrl: "/realm-true-immortal.png", progressColor: "#FFD700" },
];

const RealmTimeline = () => {
  const { t } = useLanguage();
  const [expandedRealm, setExpandedRealm] = useState<number | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLDivElement>(null);

  const realmIcons = [
    <Sprout key="0" className="w-9 h-9" />,
    <Droplet key="1" className="w-9 h-9" />,
    <Layers key="2" className="w-9 h-9" />,
    <CircleDot key="3" className="w-9 h-9" />,
    <Ghost key="4" className="w-9 h-9" />,
    <Wind key="5" className="w-9 h-9" />,
    <Tornado key="6" className="w-9 h-9" />,
    <Zap key="7" className="w-9 h-9" />,
    <Sun key="8" className="w-9 h-9" />,
    <CloudLightning key="9" className="w-9 h-9" />,
    <Crown key="10" className="w-9 h-9" />,
  ];

  // GSAP: cards ascend into view like climbing a heavenly ladder
  useEffect(() => {
    const ctx = gsap.context(() => {
      if (titleRef.current) {
        gsap.fromTo(titleRef.current, { y: 30, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.8, ease: "power3.out",
          scrollTrigger: { trigger: titleRef.current, start: "top 85%", once: true },
        });
      }
      if (gridRef.current) {
        const cards = gridRef.current.querySelectorAll(".realm-card-wrapper");
        cards.forEach((card, i) => {
          gsap.fromTo(
            card,
            { y: 80, opacity: 0, scale: 0.9 },
            {
              y: 0, opacity: 1, scale: 1, duration: 0.7, ease: "power3.out",
              scrollTrigger: { trigger: card, start: "top 88%", once: true },
              delay: i * 0.04,
            }
          );
        });
      }
    });
    return () => ctx.revert();
  }, []);

  return (
    <section id="realms" className="py-24 px-4 relative overflow-hidden">
      {/* Ambient */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full bg-celestial/4 blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 rounded-full bg-primary/4 blur-3xl" />
      </div>

      <div className="container mx-auto max-w-6xl relative z-10">
        <div ref={titleRef} className="text-center mb-4" style={{ opacity: 0 }}>
          <div className="flex items-center justify-center gap-3 mb-4">
            <span className="text-2xl animate-pulse" aria-hidden="true">🌌</span>
            <h2 className="font-cinzel text-3xl sm:text-4xl md:text-5xl text-gold-gradient glow-gold inline-block">
              {t.realms.title}
            </h2>
            <span className="text-2xl animate-pulse" style={{ animationDelay: "0.7s" }} aria-hidden="true">🌌</span>
          </div>
          <p className="text-muted-foreground max-w-3xl mx-auto leading-relaxed">
            {t.realms.subtitle}
          </p>
        </div>

        {/* Realm grid */}
        <div ref={gridRef} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8 mt-16">
          {t.realms.names.map((name, i) => {
            const colors = realmColors[i];
            const isExpanded = expandedRealm === i;
            const isLast = i === t.realms.names.length - 1;

            // Parse description into parts for rich back face
            const desc = t.realms.descriptions[i] ?? "";
            const [loreRaw = "", statsLine = ""] = desc.split("\n\n");
            const dotIdx = loreRaw.indexOf(" · ");
            const chName = dotIdx > -1 ? loreRaw.slice(0, dotIdx) : "";
            const loreBody = dotIdx > -1 ? loreRaw.slice(dotIdx + 3) : loreRaw;

            if (isLast) {
              // ── TRUE IMMORTAL — Special card ───────────────────────────────
              return (
                <div
                  key={i}
                  className="realm-card-wrapper sm:col-span-2 lg:col-span-3 flex justify-center"
                  style={{ opacity: 0 }}
                >
                  <div
                    className="relative w-full max-w-md cursor-pointer group"
                    style={{ perspective: "1000px" }}
                    role="button"
                    tabIndex={0}
                    aria-label={`View details for ${name}`}
                    onClick={() => setExpandedRealm(isExpanded ? null : i)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setExpandedRealm(isExpanded ? null : i);
                      }
                    }}
                  >
                    {/* Animated golden particle ring */}
                    <div className="absolute inset-0 rounded-2xl pointer-events-none z-0">
                      <div className="true-immortal-particles" />
                    </div>

                    <div
                      className="w-full h-72 transform-style-3d transition-all duration-700"
                      style={{ transform: isExpanded ? "rotateY(180deg)" : "rotateY(0deg)" }}
                    >
                      {/* Front */}
                      <div
                        className="absolute inset-0 backface-hidden rounded-2xl overflow-hidden flex flex-col justify-end p-6 true-immortal-bob"
                        style={{
                          border: "1.5px solid rgba(255,215,0,0.7)",
                          boxShadow: "0 0 40px 10px rgba(255,215,0,0.4), 0 0 80px 20px rgba(255,140,0,0.2), inset 0 0 30px rgba(255,215,0,0.05)",
                          background: "rgba(5,5,20,0.8)",
                        }}
                      >
                        {colors.imgUrl && (
                          <div className="absolute inset-0 z-0">
                            <LazyImage
                              src={colors.imgUrl}
                              alt={name}
                              className="w-full h-full"
                              imgClassName="filter brightness-[0.45] saturate-[1.4] group-hover:scale-105 transition-transform duration-1000"
                              width={512}
                              height={512}
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent" />
                          </div>
                        )}
                        <div className="relative z-10 text-center flex flex-col items-center gap-3">
                          {/* Crown pulses */}
                          <span
                            className="block crown-pulse"
                            style={{ color: "#FFD700", filter: "drop-shadow(0 0 18px rgba(255,215,0,0.8))" }}
                          >
                            <Crown className="w-12 h-12" />
                          </span>
                          <span className="font-mono text-xs text-white/40 tracking-widest">
                            {String(i + 1).padStart(2, "0")}
                          </span>
                          <h3
                            className="font-cinzel font-black text-2xl uppercase tracking-widest"
                            style={{ color: "#FFD700", textShadow: "0 0 20px rgba(255,215,0,0.8), 0 0 40px rgba(255,140,0,0.5)" }}
                          >
                            {name}
                          </h3>
                          <p className="font-cinzel text-xs italic text-white/60 tracking-widest">
                            The Ultimate Ascension
                          </p>
                          {/* Progress bar */}
                          <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden mt-2">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: "100%",
                                background: "linear-gradient(90deg, #FFD700, #FF8C00, #FFD700)",
                                boxShadow: "0 0 10px rgba(255,215,0,0.8)",
                                animation: "shimmer-bar 2s linear infinite",
                              }}
                            />
                          </div>
                          <p className="text-[10px] text-white/40 uppercase tracking-widest mt-1">Flip for lore</p>
                        </div>
                      </div>

                      {/* Back */}
                      <div
                        className="absolute inset-0 backface-hidden rotate-y-180 rounded-2xl flex flex-col justify-center p-7"
                        style={{
                          background: "rgba(5,5,20,0.97)",
                          border: "1.5px solid rgba(255,215,0,0.5)",
                          boxShadow: "0 0 40px rgba(255,215,0,0.3), inset 0 0 20px rgba(255,215,0,0.03)",
                        }}
                      >
                        <div className="absolute inset-0 rounded-2xl pointer-events-none"
                          style={{ background: "radial-gradient(circle at center, rgba(255,215,0,0.05) 0%, transparent 65%)" }} />
                        <div className="relative z-10 flex flex-col gap-3">
                          <div className="flex items-center gap-3">
                            <Crown className="w-6 h-6 flex-shrink-0" style={{ color: "#FFD700" }} />
                            <span className="font-serif text-2xl font-bold tracking-widest" style={{ color: "#FFD700", textShadow: "0 0 14px rgba(255,215,0,0.6)" }}>{chName}</span>
                          </div>
                          <p className="text-[11px] text-white/80 italic leading-relaxed">{loreBody}</p>
                          {statsLine && (
                            <div className="rounded-lg px-3 py-2 text-[10px] font-mono border"
                              style={{ background: "rgba(255,215,0,0.06)", borderColor: "rgba(255,215,0,0.2)", color: "#FFD700" }}>
                              {statsLine}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            }

            // ── Regular realm card ─────────────────────────────────────────
            return (
              <div
                key={i}
                className="realm-card-wrapper relative h-64 w-full cursor-pointer group"
                style={{ perspective: "1000px", opacity: 0, filter: `drop-shadow(0 0 20px ${colors.glowColor})` }}
                role="button"
                tabIndex={0}
                aria-label={`View details for ${name}`}
                onClick={() => setExpandedRealm(isExpanded ? null : i)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setExpandedRealm(isExpanded ? null : i);
                  }
                }}
              >
                <div
                  className="w-full h-full transform-style-3d transition-all duration-700"
                  style={{ transform: isExpanded ? "rotateY(180deg)" : "rotateY(0deg)" }}
                >
                  {/* Front */}
                  <div
                    className="absolute inset-0 backface-hidden rounded-2xl overflow-hidden flex flex-col justify-end p-5 shadow-2xl transition-all duration-500"
                    style={{
                      border: `1px solid ${colors.border}`,
                      background: "rgba(5,5,20,0.75)",
                      backdropFilter: "blur(12px)",
                    }}
                  >
                    {colors.imgUrl && (
                      <div className="absolute inset-0 z-0">
                        <LazyImage
                          src={colors.imgUrl}
                          alt={name}
                          className="w-full h-full"
                          imgClassName="filter brightness-[0.38] saturate-[1.2] group-hover:scale-110 transition-transform duration-1000"
                          width={512}
                          height={512}
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent" />
                      </div>
                    )}

                    <div className="relative z-10 flex flex-col gap-2">
                      <div className="flex items-center justify-between">
                        <span
                          className="flex items-center justify-center p-2 rounded-full bg-black/40 border border-white/10"
                          style={{ color: colors.text, filter: `drop-shadow(0 0 8px ${colors.glowColor})` }}
                        >
                          {realmIcons[i]}
                        </span>
                        <span className="text-xl font-mono text-muted-foreground/50 font-bold tracking-widest">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                      </div>
                      <h3
                        className="font-cinzel font-bold text-xl uppercase tracking-wider mt-2"
                        style={{ color: colors.text, filter: `drop-shadow(0 0 8px ${colors.glowColor})` }}
                      >
                        {name}
                      </h3>
                      {/* Progress bar */}
                      <div className="flex gap-1 mt-2">
                        {Array.from({ length: 5 }).map((_, tier) => (
                          <div
                            key={tier}
                            className="h-1.5 flex-1 rounded-full"
                            style={{
                              background: tier === 0 ? colors.progressColor : "rgba(255,255,255,0.1)",
                              boxShadow: tier === 0 ? `0 0 5px ${colors.progressColor}` : "none",
                            }}
                          />
                        ))}
                      </div>
                      <p className="text-center mt-2 text-[9px] text-muted-foreground uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
                        Flip to Read Lore
                      </p>
                    </div>
                  </div>

                  {/* Back */}
                  <div
                    className="absolute inset-0 backface-hidden rotate-y-180 rounded-2xl flex flex-col justify-center p-5"
                    style={{
                      background: "rgba(3,3,8,0.97)",
                      border: `1px solid ${colors.border}`,
                    }}
                  >
                    <div
                      className="absolute inset-0 rounded-2xl pointer-events-none"
                      style={{ background: `radial-gradient(circle at 50% 40%, ${colors.bg} 0%, transparent 65%)` }}
                    />
                    <div className="relative z-10 flex flex-col gap-2.5">
                      {/* Chinese name + icon */}
                      <div className="flex items-center gap-2">
                        <span style={{ color: colors.text }} className="flex-shrink-0">
                          {realmIcons[i]}
                        </span>
                        <span className="font-serif text-xl font-bold" style={{ color: colors.text, textShadow: `0 0 10px ${colors.glowColor}` }}>
                          {chName}
                        </span>
                      </div>
                      {/* Lore text */}
                      <p className="text-[11px] text-white/78 italic leading-relaxed">
                        {loreBody}
                      </p>
                      {/* Stats badge */}
                      {statsLine && (
                        <div className="rounded-lg px-2.5 py-1.5 text-[9.5px] font-mono border mt-0.5"
                          style={{ background: colors.bg, borderColor: colors.border, color: colors.text }}>
                          {statsLine}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};

export default RealmTimeline;
