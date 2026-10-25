import { useState, useEffect } from 'react';
import { useLanguage } from '@/hooks/useLanguage';

const StickyMobileCTA = () => {
    const [isVisible, setIsVisible] = useState(false);
    const { t } = useLanguage();

    useEffect(() => {
        const handleScroll = () => {
            // Show after scrolling past hero (roughly 100vh)
            setIsVisible(window.scrollY > window.innerHeight * 0.8);
        };

        window.addEventListener('scroll', handleScroll, { passive: true });
        return () => window.removeEventListener('scroll', handleScroll);
    }, []);

    // Only show on mobile/tablet
    return (
        <div
            className={`fixed bottom-0 left-0 right-0 z-50 md:hidden transition-transform duration-300 ${isVisible ? 'translate-y-0' : 'translate-y-full'
                }`}
            role="complementary"
            aria-label="Quick action"
        >
            <div className="bg-[#0a0a0f]/95 backdrop-blur-md border-t border-[#FFD700]/20 px-4 py-3 flex gap-3">
                {/* A WEB-C mudou o botao primario do Hero e da Navbar para
                    `/login` (a porta propria, com Google/Apple/e-mail) e deixou
                    ESTA barra para tras — e ela e' `md:hidden`, ou seja, e' o
                    unico CTA primario que o visitante de TELEMOVEL ve depois de
                    passar o hero. Resultado: no telemovel o botao maior e mais
                    brilhante do site continuava a despejar a pessoa no Telegram,
                    saltando a porta que a WEB-B construiu. Report do owner
                    2026-09-01: "play now link enviando direto ao telegram". */}
                <a
                    href="/login"
                    className="flex-1 bg-gradient-to-r from-[#FFD700] to-[#FFA500] text-black font-bold text-center py-3 rounded-lg text-sm hover:opacity-90 transition-opacity min-h-[44px] flex items-center justify-center"
                >
                    <span aria-hidden="true">⚔️</span> {t.hero?.playCta || 'Play now'}
                </a>
                <a
                    href="/play"
                    className="bg-transparent border border-[#FFD700]/45 text-[#FFD700] font-semibold text-center py-3 px-4 rounded-lg text-sm hover:bg-[#FFD700]/10 transition-colors min-h-[44px] flex items-center justify-center"
                >
                    <span aria-hidden="true">🗺️</span> {t.hero?.worldCta || 'See the world'}
                </a>
            </div>
        </div>
    );
};

export default StickyMobileCTA;
