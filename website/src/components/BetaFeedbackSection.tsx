import { useLanguage } from "@/hooks/useLanguage";
import { Bug, Lightbulb, Star } from "lucide-react";

const BetaFeedbackSection = () => {
    const { t } = useLanguage();

    const cards = [
        {
            icon: <Bug className="w-7 h-7 text-orange-400 drop-shadow-[0_0_10px_rgba(251,146,60,0.6)]" />,
            glyph: "裂", // Chinese for "rift"
            title: t.feedback.bugReport,
            desc: t.feedback.bugReportDesc,
            href: "https://t.me/Nivrael_RPG",
            color: "from-red-500/20 to-orange-500/20",
            borderHover: "hover:border-red-400/40",
            glowHover: "hover:shadow-[0_0_25px_hsl(0_84%_60%/0.15)]",
        },
        {
            icon: <Lightbulb className="w-7 h-7 text-yellow-400 drop-shadow-[0_0_10px_rgba(250,204,21,0.6)]" />,
            glyph: "慧", // Chinese for "wisdom"
            title: t.feedback.suggest,
            desc: t.feedback.suggestDesc,
            href: "https://t.me/Nivrael_RPG",
            color: "from-amber-500/20 to-yellow-500/20",
            borderHover: "hover:border-amber-400/40",
            glowHover: "hover:shadow-[0_0_25px_hsl(38_92%_50%/0.15)]",
        },
        {
            icon: <Star className="w-7 h-7 text-purple-400 drop-shadow-[0_0_10px_rgba(192,132,252,0.6)]" />,
            glyph: "道", // Chinese for "Dao/Path"
            title: t.feedback.review,
            desc: t.feedback.reviewDesc,
            href: "https://t.me/Nivrael_RPG",
            color: "from-purple-500/20 to-celestial/20",
            borderHover: "hover:border-purple-400/40",
            glowHover: "hover:shadow-[0_0_25px_hsl(270_76%_55%/0.15)]",
        },
    ];

    return (
        <section id="feedback" className="py-24 px-4 relative overflow-hidden">
            {/* Decorative top border */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-4xl h-px bg-gradient-to-r from-transparent via-celestial/20 to-transparent" />

            {/* Ambient background */}
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full bg-celestial/3 blur-3xl" />
            </div>

            <div className="container mx-auto max-w-4xl text-center relative z-10">
                <div className="text-center mb-12">
                    <h2 className="font-cinzel text-3xl sm:text-4xl inline-flex items-center gap-3 text-gold-gradient glow-gold text-reveal mb-4">
                        <span className="text-2xl animate-spin-slow" aria-hidden="true">☯</span>
                        <span>{t.feedback.title}</span>
                        <span className="text-2xl animate-spin-slow" aria-hidden="true" style={{ animationDirection: "reverse" }}>☯</span>
                    </h2>
                    <p className="text-muted-foreground max-w-2xl mx-auto text-reveal">
                        <span>{t.feedback.subtitle}</span>
                    </p>
                </div>
                <p className="text-xs text-muted-foreground/50 italic mb-12 max-w-lg mx-auto">
                    {t.feedback.lore}
                </p>

                {/* Feedback Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 max-w-3xl mx-auto">
                    {cards.map((card, i) => (
                        <a
                            key={i}
                            href={card.href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={`group relative flex flex-col items-center gap-4 p-8 rounded-2xl border border-white/5 bg-black/40 backdrop-blur-md transition-all duration-500 overflow-hidden ${card.borderHover} ${card.glowHover} hover:-translate-y-2`}
                        >
                            {/* Subtle glass reflection */}
                            <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
                            {/* Background glyph */}
                            <span className="absolute top-3 right-4 text-4xl font-bold text-foreground/[0.03] font-serif select-none pointer-events-none" aria-hidden="true" lang="zh">
                                {card.glyph}
                            </span>

                            {/* Icon with gradient bg */}
                            <div className={`w-14 h-14 rounded-xl bg-gradient-to-br ${card.color} flex items-center justify-center text-2xl group-hover:scale-110 transition-transform duration-300`}>
                                {card.icon}
                            </div>

                            <h3 className="font-cinzel font-bold text-sm text-foreground">{card.title}</h3>
                            <p className="text-xs text-muted-foreground/70 leading-relaxed">{card.desc}</p>
                        </a>
                    ))}
                </div>
            </div>
        </section>
    );
};

export default BetaFeedbackSection;
