import { lazy, Suspense } from "react";
import Navbar from "@/components/Navbar";
import HeroSection from "@/components/HeroSection";
import Footer from "@/components/Footer";
import StickyMobileCTA from "@/components/StickyMobileCTA";

// Lazy-load below-the-fold sections for code splitting
const FeaturesSection = lazy(() => import("@/components/FeaturesSection"));
const GamePreview = lazy(() => import("@/components/GamePreview"));
const RealmTimeline = lazy(() => import("@/components/RealmTimeline"));
const CommunitySection = lazy(() => import("@/components/CommunitySection"));
const BetaFeedbackSection = lazy(() => import("@/components/BetaFeedbackSection"));

// Minimal fallback to avoid layout shift
const SectionFallback = () => <div className="min-h-screen" />;

// ─── Index ────────────────────────────────────────────────────────────────────
//
// WEB-C §3.3 — o que saiu daqui, e porquê. Cada um destes custava o primeiro
// pixel e não devolvia nada ao jogador:
//
//  • `LoadingScreen` — segurava a página INTEIRA atrás de uma animação de
//    entrada. Era o pior dos cinco: um ecrã de carregamento por cima de um
//    site estático adia o LCP por decisão nossa, não por peso real.
//  • `Lenis` (smooth scroll) — reescrevia o scroll do browser em JS. Uma roda
//    de rato que não obedece é a definição de "site que parece um demo".
//  • `CustomCursor` — substituía o cursor do sistema. Um cursor que arrasta
//    atrás do ponteiro lê-se como lag, e desaparece para quem navega a teclado.
//  • `ScrollProgress` — um anel 道 na margem, `aria-hidden`, a re-renderizar
//    a cada evento de scroll para dizer algo que a barra do browser já diz.
//  • `MagneticButton` (em HeroSection) — botões que fogem do rato. O acto
//    primário da página não deve ser um alvo móvel.
//
// O que ficou: uma página, as secções, e o botão que leva a jogar.
const Index = () => {
  return (
    <div className="min-h-screen bg-background overflow-x-hidden selection:bg-primary/30 selection:text-primary">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:bg-[#FFD700] focus:text-black focus:rounded focus:font-bold focus:text-sm"
      >
        Skip to content
      </a>
      <header>
        <Navbar />
      </header>
      <main id="main-content">
        <HeroSection />
        <Suspense fallback={<SectionFallback />}>
          <FeaturesSection />
        </Suspense>
        <Suspense fallback={<SectionFallback />}>
          <GamePreview />
        </Suspense>
        <Suspense fallback={<SectionFallback />}>
          <RealmTimeline />
        </Suspense>
        <Suspense fallback={<SectionFallback />}>
          <CommunitySection />
        </Suspense>
        <Suspense fallback={<SectionFallback />}>
          <BetaFeedbackSection />
        </Suspense>
      </main>
      <StickyMobileCTA />
      <Footer />
    </div>
  );
};

export default Index;
