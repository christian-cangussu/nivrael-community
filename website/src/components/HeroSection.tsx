import { useEffect, useRef, useState } from "react";
import { useLanguage } from "@/hooks/useLanguage";
import { motion, useScroll, useTransform } from "framer-motion";
import gsap from "gsap";
import HeroScene from "@/components/HeroScene";

const HeroSection = () => {
  const { t } = useLanguage();
  const [displayedText, setDisplayedText] = useState("");
  const [typingDone, setTypingDone] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  const { scrollY } = useScroll();
  const contentY = useTransform(scrollY, [0, 800], ["0%", "55%"]);
  const contentOpacity = useTransform(scrollY, [0, 500], [1, 0]);
  const sceneOpacity = useTransform(scrollY, [0, 600], [1, 0]);

  // Typing effect for narrative intro (delayed so GSAP intro plays first)
  useEffect(() => {
    setDisplayedText("");
    setTypingDone(false);
    const text = t.hero.narrativeIntro;
    let i = 0;
    const startDelay = setTimeout(() => {
      const interval = setInterval(() => {
        if (i < text.length) {
          setDisplayedText(text.slice(0, i + 1));
          i++;
        } else {
          setTypingDone(true);
          clearInterval(interval);
        }
      }, 35);
      return () => clearInterval(interval);
    }, 1600);
    return () => clearTimeout(startDelay);
  }, [t.hero.narrativeIntro]);

  // GSAP staggered entrance
  useEffect(() => {
    if (!contentRef.current) return;
    const els = contentRef.current.querySelectorAll(".gsap-intro");
    gsap.fromTo(
      els,
      { y: 44, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.92, stagger: 0.18, ease: "power3.out", delay: 0.4 }
    );
  }, []);

  return (
    <section id="hero" className="relative min-h-screen flex items-center justify-center overflow-hidden w-full bg-void-deep">

      {/* CSS/SVG hero background — lightweight, no JS animation loops */}
      <motion.div className="absolute inset-0 z-0" style={{ opacity: sceneOpacity }}>
        <HeroScene />
      </motion.div>

      {/* Radial vignette */}
      <div
        className="absolute inset-0 z-[2] pointer-events-none"
        style={{ background: "radial-gradient(ellipse at center, transparent 25%, rgba(3,3,8,0.72) 70%, rgba(3,3,8,0.96) 100%)" }}
      />

      {/* Atmospheric colour blobs */}
      <div className="absolute inset-0 z-[2] pointer-events-none overflow-hidden">
        <div className="absolute top-1/4 -left-32 w-96 h-96 rounded-full bg-celestial/6 blur-[110px] animate-pulse" style={{ animationDuration: "9s" }} />
        <div className="absolute top-1/2 -right-32 w-[500px] h-[500px] rounded-full bg-primary/5 blur-[130px] animate-pulse" style={{ animationDuration: "13s" }} />
        <div className="absolute bottom-1/4 left-1/3 w-80 h-80 rounded-full bg-celestial/4 blur-[100px] animate-pulse" style={{ animationDuration: "7s" }} />
      </div>

      {/* Vertical calligraphy watermarks */}
      <div className="absolute inset-0 z-[2] pointer-events-none flex justify-between px-4 sm:px-16 items-center opacity-[0.035] text-white font-serif font-black select-none mix-blend-overlay overflow-hidden" aria-hidden="true">
        <div className="text-[12rem] md:text-[18rem] leading-none tracking-[0.2em]" style={{ writingMode: "vertical-rl" }} lang="zh">乾坤</div>
        <div className="text-[12rem] md:text-[18rem] leading-none tracking-[0.2em]" style={{ writingMode: "vertical-rl" }} lang="zh">天道</div>
      </div>

      {/* Main text content */}
      <motion.div
        ref={contentRef}
        className="relative z-10 text-center px-4 max-w-5xl mx-auto w-full flex flex-col items-center justify-center"
        style={{ y: contentY, opacity: contentOpacity }}
      >
        {/* Badge */}
        <div className="gsap-intro inline-block mb-8" style={{ opacity: 0 }}>
          <span className="px-6 py-2.5 rounded-full text-xs font-bold tracking-widest border border-primary/30 bg-black/40 backdrop-blur-md text-primary glow-badge">
            {t.hero.badge}
          </span>
        </div>

        {/* Chinese subtitle */}
        <p className="gsap-intro text-white/50 text-sm sm:text-base tracking-[0.5em] font-mono mb-4" style={{ opacity: 0 }} aria-hidden="true" lang="zh">
          道途：永生之路
        </p>

        {/* Epic title */}
        <h1
          className="gsap-intro font-cinzel text-6xl sm:text-8xl md:text-[9rem] font-black tracking-widest text-transparent bg-clip-text bg-gradient-to-b from-white via-yellow-100 to-gold-dim hero-title-pulsate mb-4 leading-none select-none"
          style={{ opacity: 0, filter: "drop-shadow(0 0 40px rgba(255,215,0,0.35))" }}
        >
          NIVRAEL
        </h1>

        {/* Path of Immortals */}
        <p className="gsap-intro font-cinzel text-xl sm:text-3xl md:text-4xl text-white/90 tracking-[0.25em] mb-8 font-light" style={{ opacity: 0 }}>
          {t.hero.subtitle}
        </p>

        {/* Narrative glass panel */}
        <div className="gsap-intro w-full max-w-3xl mx-auto mb-10 p-6 rounded-2xl border border-white/5 bg-black/25 backdrop-blur-sm shadow-2xl" style={{ opacity: 0 }}>
          <div className="min-h-[3.5rem] sm:min-h-[3rem] flex items-center justify-center">
            <p
              className={`text-qi-cyan text-base sm:text-lg italic leading-relaxed ${!typingDone ? "typing-cursor" : ""}`}
              style={{ textShadow: "0 0 12px rgba(0,212,170,0.4)" }}
            >
              {displayedText}
            </p>
          </div>
          <p className="text-white/55 text-sm sm:text-base mt-4 max-w-2xl mx-auto leading-relaxed">
            {t.hero.tagline}
          </p>
        </div>

        {/* CTAs — WEB-C (2026-08-27): o acto primário passa a ser JOGAR.
            Até aqui o botão de ouro levava a `/play` (a vitrine, que é LEITURA)
            e o de jogar levava ao Telegram. Desde a WEB-B F2 há uma porta
            própria — `/login`, com Google/Apple/e-mail — e o site era o único
            sítio do projecto que ainda não a apontava (dívida escrita em
            `Mecanicas/identidade.md` §7: "a porta ainda não está anunciada em
            lado nenhum"). Quem chega frio tem de poder JOGAR num clique, sem
            instalar nada.

            Nenhuma porta fechou (Lei §1): a vitrine desce a secundário — quem
            quer ver antes de entrar continua a um clique — e o bot continua no
            navbar e na barra fixa do telemóvel.

            Os `MagneticButton` saíram: o botão principal de uma página não
            deve fugir do ponteiro de quem o quer carregar. */}
        <div className="gsap-intro flex flex-col sm:flex-row items-center justify-center gap-6 mt-4" style={{ opacity: 0 }}>
          <a
            href="/login"
            className="inline-flex items-center justify-center gap-3 px-10 py-5 rounded-xl font-cinzel font-bold text-lg tracking-widest bg-gradient-to-r from-primary via-gold-dim to-primary text-primary-foreground hover:scale-[1.03] active:scale-95 transition-all duration-300 border border-primary/50 relative overflow-hidden group min-w-[280px]"
            style={{ boxShadow: "0 0 40px rgba(255,215,0,0.3)" }}
          >
            <div className="absolute inset-0 -translate-x-full group-hover:animate-shimmer-fast bg-gradient-to-r from-transparent via-white/40 to-transparent skew-x-12" />
            <span className="relative z-10">{t.hero.playCta}</span>
            <span className="text-2xl relative z-10 group-hover:rotate-12 transition-transform" aria-hidden="true">⚔️</span>
          </a>
          <a
            href="/play"
            className="inline-flex items-center justify-center gap-3 px-10 py-5 rounded-xl font-cinzel font-bold text-lg tracking-widest border border-qi-cyan/40 text-qi-cyan hover:bg-qi-cyan/10 hover:border-qi-cyan transition-all duration-300 active:scale-95 bg-black/40 backdrop-blur-md min-w-[280px] group"
            style={{ boxShadow: "0 0 30px rgba(0,212,170,0.12)" }}
          >
            <span className="text-xl group-hover:-translate-y-1 transition-transform" aria-hidden="true">🗺️</span>
            <span>{t.hero.worldCta}</span>
          </a>
        </div>

        {/* O antigo secundário desce a link de texto — deixar de ser botão não é
            deixar de existir (Lei §1: nenhum caminho desaparece). */}
        <div className="gsap-intro mt-6" style={{ opacity: 0 }}>
          <button
            onClick={() => document.getElementById("realms")?.scrollIntoView({ behavior: "smooth" })}
            className="inline-flex items-center gap-2 text-sm text-white/50 hover:text-white/80 transition-colors"
          >
            <span aria-hidden="true">📖</span>
            <span className="underline underline-offset-4 decoration-white/20">{t.hero.secondaryCta}</span>
          </button>
        </div>
      </motion.div>

      {/* Bottom depth fade */}
      <div className="absolute bottom-0 left-0 right-0 z-20 pointer-events-none">
        <div className="h-48 bg-gradient-to-t from-void-deep via-void-deep/70 to-transparent" />
      </div>

      {/* Scroll hint */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-20 flex flex-col items-center gap-2 animate-bounce" style={{ opacity: 0.4 }}>
        <div className="w-px h-8 bg-gradient-to-b from-transparent to-primary" />
        <div className="w-1.5 h-1.5 rounded-full bg-primary" />
      </div>
    </section>
  );
};

export default HeroSection;
