import { useLanguage } from "@/hooks/useLanguage";

// Pre-computed footer particle positions (12 particles, no RAF loop)
const footerParticles = Array.from({ length: 12 }, (_, i) => ({
  left: `${(i * 8.3 + 4) % 100}%`,
  delay: `${(i * 0.7) % 8}s`,
  duration: `${7 + (i * 0.9) % 6}s`,
  hue: [51, 187, 270][i % 3],
}));

const Footer = () => {
  const { t } = useLanguage();

  return (
    <footer className="relative overflow-hidden" style={{ borderTop: "1px solid rgba(255,215,0,0.08)" }}>
      {/* Mountain background darkened */}
      <div className="absolute inset-0 z-0 overflow-hidden">
        <picture>
          <source srcSet="/hero-bg.webp" type="image/webp" />
          <img
            src="/hero-bg.png"
            alt=""
            loading="lazy"
            decoding="async"
            className="w-full h-full object-cover object-center"
            style={{ filter: "brightness(0.1) saturate(1.2)" }}
          />
        </picture>
      </div>
      <div className="absolute inset-0 z-[1] pointer-events-none"
        style={{ background: "linear-gradient(to bottom, rgba(3,3,8,0.65) 0%, rgba(3,3,8,0.9) 100%)" }}
      />

      {/* CSS particles — replaces canvas RAF loop */}
      <div className="absolute inset-0 z-[2] pointer-events-none overflow-hidden" aria-hidden="true">
        {footerParticles.map((p, i) => (
          <div
            key={i}
            className="footer-particle"
            style={{
              left: p.left,
              animationDelay: p.delay,
              animationDuration: p.duration,
              background: `radial-gradient(circle, hsla(${p.hue},85%,65%,0.7), transparent)`,
              width: "3px",
              height: "3px",
            }}
          />
        ))}
      </div>

      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-3xl h-px z-[3]"
        style={{ background: "linear-gradient(90deg, transparent, rgba(255,215,0,0.3), transparent)" }}
      />

      <div className="container mx-auto max-w-4xl px-4 py-12 relative z-10">
        <div className="text-center mb-8">
          <h3 className="font-cinzel text-2xl font-black tracking-widest mb-2"
            style={{ color: "#FFD700", textShadow: "0 0 20px rgba(255,215,0,0.4)" }}>
            NIVRAEL
          </h3>
          <p className="text-xs tracking-widest uppercase font-cinzel" style={{ color: "rgba(255,255,255,0.5)" }}>
            Path of Immortals
          </p>
        </div>

        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="text-center md:text-left">
            <div className="flex items-center gap-3 justify-center md:justify-start mb-1">
              <p className="font-cinzel text-sm font-bold" style={{ color: "rgba(255,255,255,0.7)" }}>
                {t.footer.copyright}
              </p>
              <span className="px-2 py-0.5 rounded-md text-[10px] font-bold tracking-wider border"
                style={{ borderColor: "rgba(0,212,170,0.3)", background: "rgba(0,212,170,0.08)", color: "#00d4aa" }}>
                {t.footer.betaVersion}
              </span>
            </div>
            <p className="text-xs mt-1" style={{ color: "rgba(255,255,255,0.5)" }}>{t.footer.builtWith}</p>
          </div>
          <div className="flex gap-6">
            {[t.footer.privacy, t.footer.terms, t.footer.contact].map((label) => (
              <span key={label} className="text-white/30 cursor-default text-sm">
                {label}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-8 pt-6 flex items-center justify-center gap-4"
          style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
          <div className="h-px flex-1" style={{ background: "linear-gradient(90deg, transparent, rgba(255,215,0,0.15))" }} />
          <span style={{ color: "rgba(255,215,0,0.3)", fontSize: "1.2rem" }}>☯</span>
          <div className="h-px flex-1" style={{ background: "linear-gradient(90deg, rgba(255,215,0,0.15), transparent)" }} />
        </div>
      </div>
    </footer>
  );
};

export default Footer;
