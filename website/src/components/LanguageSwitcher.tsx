import { useLanguage } from "@/hooks/useLanguage";
import { Language, languageLabels } from "@/lib/translations";

const LanguageSwitcher = () => {
  const { lang, setLang } = useLanguage();
  const langs: Language[] = ["en", "pt", "es"];

  return (
    <div className="flex gap-1">
      {langs.map((l) => (
        <button
          key={l}
          onClick={() => setLang(l)}
          className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${
            lang === l
              ? "bg-primary/20 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted"
          }`}
          aria-label={`Switch to ${languageLabels[l].label}`}
        >
          {languageLabels[l].flag}
        </button>
      ))}
    </div>
  );
};

export default LanguageSwitcher;
