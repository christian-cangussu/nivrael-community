import { useEffect, useRef, useState } from "react";
import { useLanguage } from "@/hooks/useLanguage";
import { Swords, Scroll, Landmark } from "lucide-react";

const CommunitySection = () => {
  const { t } = useLanguage();
  const [count, setCount] = useState(0);
  const counterRef = useRef<HTMLDivElement>(null);
  const hasAnimated = useRef(false);
  const sectionRef = useRef<HTMLElement>(null); // Ref for the section to observe

  // Animated counter and reveal animations
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            // Counter animation
            if (!hasAnimated.current) {
              hasAnimated.current = true;
              // ⚠️ NÚMERO REAL, medido na DB a 2026-08-20: 240 no mundo legado
              // + 21 no servidor de entrada. Dizia 1.000 e o subtítulo dizia
              // "milhares" — a página de entrada de um jogo em beta aberto não
              // pode abrir com um número inventado. Atualizar quando crescer.
              const target = 261;
              const duration = 2000;
              const start = performance.now();

              const animate = (now: number) => {
                const elapsed = now - start;
                const progress = Math.min(elapsed / duration, 1);
                const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
                setCount(Math.floor(eased * target));
                if (progress < 1) requestAnimationFrame(animate);
              };
              requestAnimationFrame(animate);
            }

            // Cards stagger
            const cards = entry.target.querySelectorAll(".community-card");
            cards.forEach((card, i) => {
              setTimeout(() => {
                card.classList.add("visible");
              }, i * 150);
            });

            // Text reveal
            const reveals = entry.target.querySelectorAll(".text-reveal span"); // Target spans inside text-reveal
            reveals.forEach((el, i) => {
              setTimeout(() => el.classList.add("visible"), i * 200);
            });
          }
        });
      },
      { threshold: 0.3 }
    );

    if (sectionRef.current) observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);

  const cards = [
    {
      href: "https://t.me/Nivrael_BOT",
      icon: <Swords className="w-12 h-12 text-primary drop-shadow-[0_0_15px_rgba(255,215,0,0.6)]" />,
      title: t.community.bot,
      desc: t.community.botDesc,
      hoverBorder: "hover:border-primary/50",
      hoverGlow: "hover:shadow-[0_0_25px_hsl(51_100%_50%/0.15)]",
    },
    {
      href: "https://t.me/Nivrael_RPG",
      icon: <Scroll className="w-12 h-12 text-accent drop-shadow-[0_0_15px_rgba(34,211,238,0.6)]" />,
      title: t.community.channel,
      desc: t.community.channelDesc,
      hoverBorder: "hover:border-accent/50",
      hoverGlow: "hover:shadow-[0_0_25px_hsl(187_94%_43%/0.15)]",
    },
    {
      href: "https://t.me/Nivrael_RPG",
      icon: <Landmark className="w-12 h-12 text-celestial-glow drop-shadow-[0_0_15px_rgba(168,85,247,0.8)]" />,
      title: t.community.group,
      desc: t.community.groupDesc,
      hoverBorder: "hover:border-celestial/50",
      hoverGlow: "hover:shadow-[0_0_25px_hsl(270_76%_40%/0.15)]",
    },
  ];

  return (
    <section id="community" ref={sectionRef} className="py-24 px-4 relative overflow-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-4xl h-px bg-gradient-to-r from-transparent via-primary/20 to-transparent" />
        <div className="absolute bottom-1/3 right-0 w-72 h-72 rounded-full bg-celestial/5 blur-3xl" />
        <div className="absolute top-1/3 left-0 w-72 h-72 rounded-full bg-primary/5 blur-3xl" />
      </div>

      <div className="container mx-auto max-w-5xl relative z-10">
        <h2 className="font-cinzel text-3xl sm:text-4xl md:text-5xl text-center mb-6 text-gold-gradient glow-gold text-reveal">
          <span>{t.community.title}</span>
        </h2>
        <div className="text-center text-muted-foreground max-w-3xl mx-auto space-y-4 mb-16">
          <p className="text-reveal"><span>{t.community.subtitle}</span></p>
        </div>

        {/* Animated Counter */}
        <div ref={counterRef} className="inline-flex items-center gap-3 mb-12 px-8 py-4 rounded-full border border-primary/20 bg-primary/5 backdrop-blur-sm">
          <span className="font-cinzel text-3xl sm:text-4xl font-black text-primary" style={{ minWidth: '4ch' }}>
            {count.toLocaleString()}+
          </span>
          <span className="text-muted-foreground text-sm text-left">{t.community.counter}</span>
        </div>

        {/* CTA Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 max-w-3xl mx-auto">
          {cards.map((card, i) => (
            <a
              key={i}
              href={card.href}
              target="_blank"
              rel="noopener noreferrer"
              className={`flex flex-col items-center gap-4 p-8 rounded-2xl border border-white/5 bg-black/40 backdrop-blur-md transition-all duration-500 hover:-translate-y-2 relative overflow-hidden group ${card.hoverBorder} ${card.hoverGlow}`}
            >
              {/* Subtle glass reflection */}
              <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
              <div className="relative z-10 mb-4 group-hover:scale-110 group-hover:-rotate-3 transition-transform duration-500">{card.icon}</div>
              <span className="relative z-10 font-cinzel font-bold text-base text-white">{card.title}</span>
              <span className="relative z-10 text-sm text-white/50 leading-relaxed text-center">{card.desc}</span>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
};

export default CommunitySection;
