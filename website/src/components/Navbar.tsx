import { useState, useEffect, useRef } from "react";
import { useLanguage } from "@/hooks/useLanguage";
import LanguageSwitcher from "./LanguageSwitcher";

const Navbar = () => {
  const { t } = useLanguage();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [ctaPulse, setCtaPulse] = useState(false);
  const pulseTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    setMobileOpen(false);
  };

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    pulseTimer.current = setInterval(() => {
      setCtaPulse(true);
      setTimeout(() => setCtaPulse(false), 900);
    }, 4000);
    return () => { if (pulseTimer.current) clearInterval(pulseTimer.current); };
  }, []);

  const navItems = [
    { id: "features", label: t.nav.features },
    { id: "realms", label: t.nav.realms },
    { id: "community", label: t.nav.community },
    { id: "feedback", label: t.nav.feedback },
  ];

  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-500"
      style={{
        background: scrolled ? "rgba(8,8,26,0.88)" : "transparent",
        backdropFilter: scrolled ? "blur(20px)" : "none",
        borderBottom: scrolled ? "1px solid rgba(255,215,0,0.08)" : "1px solid transparent",
        boxShadow: scrolled ? "0 4px 30px rgba(0,0,0,0.4)" : "none",
      }}
    >
      <div className="container mx-auto px-4 h-16 flex items-center justify-between">
        <button
          onClick={() => scrollTo("hero")}
          className="font-cinzel text-lg font-black tracking-widest relative group"
          style={{ color: "#FFD700", textShadow: "0 0 20px rgba(255,215,0,0.45)" }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.textShadow = "0 0 30px rgba(255,215,0,0.9),0 0 60px rgba(255,140,0,0.5)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.textShadow = "0 0 20px rgba(255,215,0,0.45)"; }}
        >
          NIVRAEL
          <span className="absolute -bottom-0.5 left-0 w-0 h-px bg-gradient-to-r from-primary to-transparent group-hover:w-full transition-all duration-500" />
        </button>

        <div className="hidden md:flex items-center gap-7">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => scrollTo(item.id)}
              className="text-sm font-medium relative group"
              style={{ color: "rgba(255,255,255,0.62)", transition: "color 0.2s" }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = "#ffffff"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.62)"; }}
            >
              {item.label}
              <span className="absolute -bottom-0.5 left-0 w-0 h-px bg-primary group-hover:w-full transition-all duration-300" />
            </button>
          ))}
          {/* WEB-A — a vitrine é conteúdo do próprio site, alcançável de
              qualquer ponto do scroll (não é uma saída para outra app). */}
          <a
            href="/play"
            className="text-sm font-medium relative group"
            style={{ color: "rgba(255,215,0,0.72)", transition: "color 0.2s" }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = "#FFD700"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = "rgba(255,215,0,0.72)"; }}
          >
            <span aria-hidden="true">🗺️</span> {t.hero.worldCta}
            <span className="absolute -bottom-0.5 left-0 w-0 h-px bg-primary group-hover:w-full transition-all duration-300" />
          </a>
        </div>

        <div className="flex items-center gap-3">
          <LanguageSwitcher />

          {/* WEB-C §3.3 — o botao permanente da barra passa a ser a PORTA
              (`/login`), nao o Telegram. Mesmo separador de proposito: e uma
              pagina nossa, nao uma saida para outra app. O bot desce a link de
              texto ao lado — Lei §1: deixar de ser botao nao e desaparecer. */}
          <a
            href="/login"
            className="hidden md:inline-flex items-center gap-2 px-5 py-2 rounded-full font-cinzel font-bold text-xs tracking-wider"
            style={{
              background: "linear-gradient(135deg,#FFD700,#FF8C00)",
              color: "#030308",
              boxShadow: ctaPulse
                ? "0 0 30px rgba(255,215,0,0.7),0 0 60px rgba(255,140,0,0.4)"
                : "0 0 14px rgba(255,215,0,0.25)",
              transform: ctaPulse ? "scale(1.06)" : "scale(1)",
              transition: "box-shadow 0.3s ease,transform 0.3s ease",
            }}
          >
            <span aria-hidden="true">⚔️</span> {t.hero.playCta}
          </a>
          <a
            href="https://t.me/Nivrael_bot"
            target="_blank"
            rel="noopener noreferrer"
            className="hidden md:inline-flex items-center gap-1.5 text-xs font-medium"
            style={{ color: "rgba(255,255,255,0.5)", transition: "color 0.2s" }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.85)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.5)"; }}
          >
            <span aria-hidden="true">💬</span> {t.hero.cta}
          </a>

          <button
            className="md:hidden flex flex-col gap-1.5 p-2"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Toggle menu"
          >
            <span className={`w-5 h-0.5 bg-white/70 transition-all duration-300 ${mobileOpen ? 'rotate-45 translate-y-2' : ''}`} />
            <span className={`w-5 h-0.5 bg-white/70 transition-all duration-300 ${mobileOpen ? 'opacity-0 scale-x-0' : ''}`} />
            <span className={`w-5 h-0.5 bg-white/70 transition-all duration-300 ${mobileOpen ? '-rotate-45 -translate-y-2' : ''}`} />
          </button>
        </div>
      </div>

      <div
        className="md:hidden overflow-hidden transition-all duration-300"
        style={{
          maxHeight: mobileOpen ? "460px" : "0",  // WEB-C: +1 link (a porta) — 380px cortava o último
          opacity: mobileOpen ? 1 : 0,
          background: "rgba(8,8,26,0.97)",
          backdropFilter: "blur(20px)",
          borderBottom: "1px solid rgba(255,215,0,0.08)",
        }}
      >
        <div className="container mx-auto px-4 py-4 flex flex-col gap-1">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => scrollTo(item.id)}
              className="text-left text-sm text-white/60 hover:text-white py-2.5 border-b border-white/5 last:border-0 transition-colors"
            >
              {item.label}
            </button>
          ))}
          <a
            href="/login"
            className="mt-3 text-center py-3 rounded-xl font-cinzel font-bold text-sm"
            style={{ background: "linear-gradient(135deg,#FFD700,#FF8C00)", color: "#030308", boxShadow: "0 0 20px rgba(255,215,0,0.3)" }}
          >
            <span aria-hidden="true">⚔️</span> {t.hero.playCta}
          </a>
          <a
            href="/play"
            className="mt-2 text-center py-3 rounded-xl font-cinzel font-bold text-sm border"
            style={{ borderColor: "rgba(255,215,0,0.45)", color: "#FFD700" }}
          >
            <span aria-hidden="true">🗺️</span> {t.hero.worldCta}
          </a>
          <a
            href="https://t.me/Nivrael_bot"
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 text-center py-2.5 text-sm"
            style={{ color: "rgba(255,255,255,0.55)" }}
          >
            <span aria-hidden="true">💬</span> {t.hero.cta}
          </a>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
