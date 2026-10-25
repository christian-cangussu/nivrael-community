export type Language = "en" | "pt" | "es";

export interface Translations {
  nav: {
    features: string;
    realms: string;
    community: string;
    feedback: string;
  };
  hero: {
    subtitle: string;
    tagline: string;
    narrativeIntro: string;
    cta: string;
    playCta: string;
    worldCta: string;
    secondaryCta: string;
    badge: string;
  };
  features: {
    title: string;
    subtitle: string;
    items: {
      title: string;
      description: string;
    }[];
  };
  preview: {
    title: string;
    subtitle: string;
  };
  gamePreview: {
    actions: string[];
    estados: string[];
    realm: string;
    spiritRoot: string;
    spiritRootLow: string;
    cbPerHour: string;
    power: string;
    soul: string;
    perception: string;
    luck: string;
    spiritualJade: string;
    stones: string;
    status: string;
    companion: string;
    nextAdvance: string;
    premium: string;
    ranking: string;
    celestialAnomalies: string;
    help: string;
    cbTracking: string;
    idleProgress: string;
  };
  realms: {
    title: string;
    subtitle: string;
    names: string[];
    descriptions: string[];
  };
  community: {
    title: string;
    subtitle: string;
    counter: string;
    bot: string;
    botDesc: string;
    channel: string;
    channelDesc: string;
    group: string;
    groupDesc: string;
  };
  feedback: {
    title: string;
    subtitle: string;
    lore: string;
    bugReport: string;
    bugReportDesc: string;
    suggest: string;
    suggestDesc: string;
    review: string;
    reviewDesc: string;
  };
  footer: {
    copyright: string;
    privacy: string;
    terms: string;
    contact: string;
    builtWith: string;
    betaVersion: string;
  };
}


const en: Translations = {
  nav: {
    features: "Features",
    realms: "Realms",
    community: "Community",
    feedback: "Feedback",
  },
  hero: {
    subtitle: "Path of Immortals",
    narrativeIntro: "In the world of Qiankun, where Qi flows between the heavens and earth, a mortal discovers the Dao and begins the journey to Immortality...",
    tagline: "A Xianxia idle cultivation RPG with a world that moves on its own: nine houses with old grudges, five cities that want something today, and a sky with a temper. Play inside Telegram — or just look at the world first.",
    cta: "ENTER THE WORLD",
    playCta: "PLAY NOW",
    worldCta: "SEE THE WORLD",
    secondaryCta: "Discover the Realms",
    badge: "⚡ THE GATES OF CULTIVATION ARE OPEN",
  },
  features: {
    title: "Master the Arts of Cultivation",
    subtitle: "From Mortal to True Immortal, in a world that keeps moving while you are away. Look at it live before you install anything.",
    items: [
      { title: "Idle Cultivation", description: "Cultivate Qi around the clock, online or off. Eleven realms, nine sub-layers each — and a Foundation whose purity you carry for the rest of your life." },
      { title: "A World That Moves", description: "Nine NPC houses raid, recluse and seek inheritances on their own schedule. Read the Chronicle to find out what the world did while you were gone." },
      { title: "Five Cities, Five Lands", description: "Línghé, Qiānhé, Yǎnshān, Fēnghuǒ and forbidden Mòyǔ. Each has a named city that WANTS something right now, and a land that prospers, tenses, falls under siege — or under a foreign flag." },
      { title: "天时 The Timing of Heaven", description: "The sky has moods. An Enraged Sky makes every tribulation 12% crueler; a Veil of Clouds makes it 12% kinder. It turns every 12 hours — and it tells you what's coming next. The only written future in the game." },
      { title: "Heavenly Tribulations", description: "Nine rounds of lightning from a sky that wants you dead. Resist, Dodge, or Absorb — each round, your call. One failure ends everything." },
      { title: "Deep Alchemy", description: "41 pill recipes across 7 cauldron grades. Your alchemy rank buys the flame itself: higher ranks hold more energy and refill it faster, so mastery — not your wallet — shortens the wait." },
      { title: "The Jiānghú", description: "NPC cultivators aren't statues. They march on continents, collect the contracts nobody claimed, settle blood debts with each other — and ambush YOU, where you can fight, bribe, or run." },
      { title: "Sect Libraries & Sealed Shelves", description: "129 techniques, and the good ones are locked. Earn the Outer, Inner and Core shelves of your house; prove yourself for the sealed chambers; and one house keeps a Forbidden Vault whose arts cost you years of your life." },
      { title: "Body, Meridians & Bloodline", description: "Cultivation isn't only Qi. Temper the mortal body, open twelve meridians one ritual at a time, grow a spirit garden, hunt for essence — and let your Spirit Root decide which elements the Dao lets you touch." },
      { title: "Spirit Beasts & 23 Dungeons", description: "Capture and bond 15 beast species from Common to Divine — companions, mounts, or expeditions that run while you sleep. And every dungeon portal is anchored to a real place on the map." },
      { title: "A Trade of Your Own", description: "Pick a profession that actually bites the engines — alchemy, forging, healing — and read the Imperial Market Report to learn what the world is short of this week." },
      { title: "Living Economy & the Caravan", description: "A player-driven market, plus the old caravan master: every material is born somewhere, and what your mountain doesn't grow, he'll send for. Always at a bad rate — and he tells you so to your face." },
    ],
  },
  preview: {
    title: "Your Cultivation Awaits",
    subtitle: "Play 100% inside Telegram — no download. Or open the live world in your browser first: no account, nothing to install.",
  },
  realms: {
    title: "The Path to Immortality",
    subtitle: "11 Realms of Ascension. Each realm has 9 sub-layers of progression. Master Foundation Purity, survive Heavenly Tribulations, and transcend mortality.",
    names: [
      "Mortal", "Qi Condensation", "Foundation Establishment", "Core Formation",
      "Nascent Soul", "Soul Transformation", "Void Refinement", "Body Integration",
      "Mahayana", "Tribulation Transcendence", "True Immortal",
    ],
    descriptions: [
      "凡人 · Born of flesh and fate. You perceive the world through mortal eyes — unaware of the Qi that weaves through every breath. The path of Immortality begins with a single step.\n\n⚡ Breakthrough: 1K CB · Multiplier: 1.0×",
      "聚气期 · The first great awakening. Your meridians crack open like floodgates and Qi rushes in. Nine sub-layers of condensation await before your Foundation can be laid.\n\n⚡ Breakthrough: 10K CB · Multiplier: 2.5×",
      "筑基期 · The most critical stage of all. Your Foundation Purity (0–100%) determines your entire future. Reach 100% for a permanent 5× cultivation bonus — a Perfect Foundation that gods envy.\n\n⚡ Breakthrough: 100K CB · Multiplier: 6× · 🔑 Foundation Purity system unlocks",
      "结丹期 · Deep within your dantian, raw Qi crystallizes into a Golden Core (金丹) — a treasure coveted by demons and immortals alike. The divide between cultivators and mortals is crossed forever.\n\n⚡ Breakthrough: 1M CB · Multiplier: 15×",
      "元婴期 · Your soul awakens as a separate, immortal entity within your Golden Core. The Heavens take notice. From this realm, you must survive Heavenly Tribulations to advance — there is no other way.\n\n⚡ Breakthrough: 10M CB · Multiplier: 40× · ⚡ Tribulations begin",
      "化神期 · You have transcended the boundaries of flesh. Reality warps to your will. Master Heaven's Wrath — strike the skies before they strike you — and bend the laws of nature to your Dao.\n\n⚡ Breakthrough: 100M CB · Multiplier: 100× · 🌩️ Heaven's Wrath technique",
      "炼虚期 · Space itself becomes your weapon. Tear rifts through the fabric of existence with Void Slash. The boundary between worlds grows paper-thin beneath your gaze.\n\n⚡ Breakthrough: 1B CB · Multiplier: 250× · 🌀 Void Slash unlocks",
      "合体期 · Heaven and Earth dissolve into your body. Every meridian carries the weight of mountains. You become a living force of nature — no longer a being that inhabits the world, but one that IS the world.\n\n⚡ Breakthrough: 10B CB · Multiplier: 600×",
      "大乘期 · The Great Vehicle. Seek 108 fragments of the eternal Dao — Speed, Destruction, Life, Time, Creation. Assemble the complete set to unlock the Eternal Dao and stand at the threshold of godhood.\n\n⚡ Breakthrough: 100B CB · Multiplier: 1,500× · ☯️ Eternal Dao (108 fragments)",
      "渡劫期 · Nine rounds of celestial lightning descend from a sky that wants you dead. Choose your fate each round: Resist (raw power), Dodge (speed and wit), or Absorb (convert lightning into strength). One failure ends everything.\n\n⚡ Breakthrough: 1T CB · Multiplier: 4,000× · ⚡ 9 Tribulation rounds",
      "真仙 · You have shed mortality forever. The veil between Heaven and the mortal world dissolves at your feet. The Prestige System unlocks — shatter your power and begin anew, carrying permanent bonuses into an eternal loop of ascension.\n\n✨ Multiplier: 10,000× · 🔄 Prestige System · ∞ Eternal Ascension",
    ],
  },
  community: {
    title: "Join the Sect",
    subtitle: "The world of Qiankun is in open beta. The gates are open, and the Elders read every single report.",
    counter: "cultivators have walked the path",
    bot: "Enter the World",
    botDesc: "Begin your cultivation journey now",
    channel: "Celestial Decrees",
    channelDesc: "Official announcements from the Elders",
    group: "Sect Hall",
    groupDesc: "Chat with fellow cultivators",
  },
  feedback: {
    title: "Your Voice Shapes the Heavens",
    subtitle: "As a beta tester, your wisdom helps forge the destiny of Nivrael. The Celestial Elders heed your counsel.",
    lore: "Every bug you find seals a rift in reality. Every suggestion plants a seed of cosmic power.",
    bugReport: "Report a Rift",
    bugReportDesc: "Found a bug? Help us seal the cracks in reality.",
    suggest: "Offer Wisdom",
    suggestDesc: "Suggest features that will shape the future of Nivrael.",
    review: "Share Your Path",
    reviewDesc: "Tell us about your cultivation experience so far.",
  },
  gamePreview: {
    actions: ["🌿 Cultivation & Base", "⚔️ Adventure & Combat", "👥 Community & Trade", "🔨 Central Workshop"],
    estados: ["⚡ Cultivating... +1.2K CB/hour", "🧘 In deep meditation...", "⚡ Cultivating... +1.2K CB/hour", "🏃 On expedition..."],
    realm: "Realm",
    spiritRoot: "Spirit Root",
    spiritRootLow: "Low",
    cbPerHour: "CB/hour",
    power: "Power",
    soul: "Soul",
    perception: "Perception",
    luck: "Luck",
    spiritualJade: "Spiritual Jade",
    stones: "Stones",
    status: "Status",
    companion: "Companion",
    nextAdvance: "Next advance",
    premium: "💎 Premium Domain / VIP",
    ranking: "🏆 Ranking",
    celestialAnomalies: "🌩️ Celestial Anomalies",
    help: "❓ Help",
    cbTracking: "Real-time CB tracking",
    idleProgress: "Idle progress",
  },
  footer: {
    copyright: "Nivrael: Path of Immortals © 2026",
    privacy: "Privacy Policy",
    terms: "Terms of Service",
    contact: "Contact",
    builtWith: "Built with Dao and Python 🐍",
    betaVersion: "Open Beta v0.1",
  },
};

const pt: Translations = {
  nav: {
    features: "Recursos",
    realms: "Reinos",
    community: "Comunidade",
    feedback: "Feedback",
  },
  hero: {
    subtitle: "Caminho dos Imortais",
    narrativeIntro: "No mundo de Qiankun, onde o Qi flui entre os céus e a terra, um mortal descobre o Dao e começa a jornada rumo à Imortalidade...",
    tagline: "Um RPG idle de cultivo Xianxia com um mundo que anda sozinho: nove casas com rixas antigas, cinco cidades que querem alguma coisa hoje, e um céu com humor. Jogue dentro do Telegram — ou só olhe o mundo primeiro.",
    cta: "ENTRAR NO MUNDO",
    playCta: "JOGAR AGORA",
    worldCta: "VER O MUNDO",
    secondaryCta: "Descobrir os Reinos",
    badge: "⚡ OS PORTÕES DO CULTIVO ESTÃO ABERTOS",
  },
  features: {
    title: "Domine as Artes do Cultivo",
    subtitle: "De Mortal a Imortal Verdadeiro, num mundo que continua andando enquanto você está fora. Olhe para ele ao vivo antes de instalar qualquer coisa.",
    items: [
      { title: "Cultivo Ocioso", description: "Cultive Qi o tempo todo, online ou não. Onze reinos, nove sub-camadas cada — e uma Fundação cuja pureza você carrega pelo resto da vida." },
      { title: "Um Mundo Que Anda", description: "Nove casas NPC saqueiam, se recolhem e caçam heranças no ritmo delas. Leia a Crônica para descobrir o que o mundo fez enquanto você estava fora." },
      { title: "Cinco Cidades, Cinco Terras", description: "Línghé, Qiānhé, Yǎnshān, Fēnghuǒ e a proibida Mòyǔ. Cada uma tem uma cidade com nome que QUER alguma coisa agora, e uma terra que prospera, tensiona, cai sob cerco — ou sob bandeira estrangeira." },
      { title: "天时 O Tempo do Céu", description: "O céu tem humor. Um Céu Irado deixa toda tribulação 12% mais cruel; um Véu de Nuvens deixa 12% mais branda. Vira de 12 em 12 horas — e diz qual vem a seguir. O único futuro escrito do jogo." },
      { title: "Tribulações Celestiais", description: "Nove rodadas de raio vindas de um céu que quer você morto. Resistir, Esquivar ou Absorver — cada rodada, escolha sua. Uma falha encerra tudo." },
      { title: "Alquimia Profunda", description: "41 receitas de pílula em 7 graus de caldeirão. Seu posto de alquimia compra a própria chama: postos altos guardam mais energia e a recarregam mais rápido — quem encurta a espera é a maestria, não a carteira." },
      { title: "O Jiānghú", description: "Os cultivadores NPC não são estátuas. Marcham sobre continentes, cobram os contratos que ninguém reclamou, acertam dívidas de sangue entre si — e emboscam VOCÊ, onde dá para enfrentar, subornar ou recuar." },
      { title: "Bibliotecas e Estantes Seladas", description: "129 técnicas, e as boas estão trancadas. Conquiste as estantes Externa, Interna e do Núcleo da sua casa; prove-se para as câmaras seladas; e uma casa guarda um Cofre Proibido cujas artes custam anos da sua vida." },
      { title: "Corpo, Meridianos e Raiz", description: "Cultivo não é só Qi. Tempere o corpo mortal, abra doze meridianos um ritual de cada vez, cultive uma horta espiritual, cace essência — e deixe sua Raiz Espiritual decidir em quais elementos o Dao permite você tocar." },
      { title: "Bestas e 23 Masmorras", description: "Capture e vincule 15 espécies do Comum ao Divino — companheiras, montarias ou expedições que correm enquanto você dorme. E todo portal de masmorra está ancorado num lugar real do mapa." },
      { title: "Um Ofício Seu", description: "Escolha uma profissão que morde os motores de verdade — alquimia, forja, cura — e leia o Relatório do Mercado Imperial para saber do que o mundo está com falta nesta semana." },
      { title: "Economia Viva e a Caravana", description: "Um mercado movido por jogadores, mais o velho mestre da caravana: todo material nasce em algum lugar, e o que a sua montanha não dá, ele manda vir. Sempre a uma razão ruim — e ele diz isso na sua cara." },
    ],
  },
  preview: {
    title: "Seu Cultivo Aguarda",
    subtitle: "Jogue 100% dentro do Telegram — sem download. Ou abra o mundo ao vivo no navegador antes: sem conta, sem instalar nada.",
  },
  realms: {
    title: "O Caminho da Imortalidade",
    subtitle: "11 Reinos de Ascensão. Cada reino tem 9 sub-camadas de progressão. Domine a Pureza da Fundação, sobreviva às Tribulações Celestiais e transcenda a mortalidade.",
    names: [
      "Mortal", "Condensação de Qi", "Estabelecimento da Fundação", "Formação do Núcleo",
      "Alma Nascente", "Transformação da Alma", "Refinamento do Vazio", "Integração Corporal",
      "Mahayana", "Transcendência da Tribulação", "Verdadeiro Imortal",
    ],
    descriptions: [
      "凡人 · Nascido de carne e destino. Você percebe o mundo com olhos mortais — alheio ao Qi que permeia cada respiração. O caminho da Imortalidade começa com um único passo.\n\n⚡ Avanço: 1K CB · Multiplicador: 1.0×",
      "聚气期 · O primeiro grande despertar. Seus meridianos se abrem como comportas e o Qi irrompe. Nove sub-camadas de condensação aguardam antes que sua Fundação possa ser estabelecida.\n\n⚡ Avanço: 10K CB · Multiplicador: 2.5×",
      "筑基期 · A etapa mais crítica de todas. Sua Pureza da Fundação (0–100%) determina todo o seu futuro. Alcance 100% para um bônus permanente de 5× — uma Fundação Perfeita que até os deuses invejariam.\n\n⚡ Avanço: 100K CB · Multiplicador: 6× · 🔑 Sistema de Pureza da Fundação",
      "结丹期 · No fundo do seu dantian, o Qi bruto cristaliza em um Núcleo Dourado (金丹) — um tesouro cobiçado por demônios e imortais. A divisão entre cultivadores e mortais é cruzada para sempre.\n\n⚡ Avanço: 1M CB · Multiplicador: 15×",
      "元婴期 · Sua alma desperta como entidade separada e imortal dentro do seu Núcleo Dourado. Os Céus percebem. Daqui, você deve sobreviver às Tribulações Celestiais para avançar — não há outro caminho.\n\n⚡ Avanço: 10M CB · Multiplicador: 40× · ⚡ Tribulações começam",
      "化神期 · Você transcendeu os limites da carne. A realidade se dobra à sua vontade. Domine o Heaven's Wrath — golpeie os céus antes que eles te golpeiem — e curve as leis da natureza ao seu Dao.\n\n⚡ Avanço: 100M CB · Multiplicador: 100× · 🌩️ Técnica Heaven's Wrath",
      "炼虚期 · O próprio espaço torna-se sua arma. Rasgue fendas pelo tecido da existência com Void Slash. A fronteira entre os mundos fica fina como papel sob seu olhar.\n\n⚡ Avanço: 1B CB · Multiplicador: 250× · 🌀 Void Slash desbloqueado",
      "合体期 · Céu e Terra se dissolvem no seu corpo. Cada meridiano carrega o peso de montanhas. Você se torna uma força viva da natureza — não mais um ser que habita o mundo, mas um que É o mundo.\n\n⚡ Avanço: 10B CB · Multiplicador: 600×",
      "大乘期 · O Grande Veículo. Busque 108 fragmentos do Dao eterno — Velocidade, Destruição, Vida, Tempo, Criação. Monte o conjunto completo para desbloquear o Dao Eterno e estar no limiar da divindade.\n\n⚡ Avanço: 100B CB · Multiplicador: 1.500× · ☯️ Dao Eterno (108 fragmentos)",
      "渡劫期 · Nove rounds de relâmpagos celestiais descem de um céu que quer você morto. Escolha seu destino a cada round: Resistir (poder bruto), Esquivar (velocidade e astúcia) ou Absorver (converter raio em força). Uma falha encerra tudo.\n\n⚡ Avanço: 1T CB · Multiplicador: 4.000× · ⚡ 9 rounds de Tribulação",
      "真仙 · Você abandonou a mortalidade para sempre. O véu entre os Céus e o mundo mortal se dissolve a seus pés. O Sistema de Prestígio desbloqueia — destrua seu poder e comece de novo, carregando bônus permanentes num loop eterno de ascensão.\n\n✨ Multiplicador: 10.000× · 🔄 Sistema de Prestígio · ∞ Ascensão Eterna",
    ],
  },
  community: {
    title: "Junte-se à Seita",
    subtitle: "O mundo de Qiankun está em beta aberto. Os portões estão abertos, e os Anciãos leem cada report.",
    counter: "cultivadores já trilharam o caminho",
    bot: "Entrar no Mundo",
    botDesc: "Comece sua jornada de cultivo agora",
    channel: "Decretos Celestiais",
    channelDesc: "Anúncios oficiais dos Anciãos",
    group: "Salão da Seita",
    groupDesc: "Converse com outros cultivadores",
  },
  feedback: {
    title: "Sua Voz Molda os Céus",
    subtitle: "Como beta tester, sua sabedoria ajuda a forjar o destino de Nivrael. Os Anciãos Celestiais ouvem seu conselho.",
    lore: "Cada bug que você encontra sela uma fenda na realidade. Cada sugestão planta uma semente de poder cósmico.",
    bugReport: "Reportar uma Fenda",
    bugReportDesc: "Encontrou um bug? Ajude a selar as rachaduras na realidade.",
    suggest: "Oferecer Sabedoria",
    suggestDesc: "Sugira recursos que moldarão o futuro de Nivrael.",
    review: "Compartilhe Seu Caminho",
    reviewDesc: "Conte-nos sobre sua experiência de cultivo até agora.",
  },
  gamePreview: {
    actions: ["🌿 Cultivo e Base", "⚔️ Aventura e Combate", "👥 Comunidade e Comércio", "🔨 Oficina Central"],
    estados: ["⚡ Cultivando... +1.2K CB/hora", "🧘 Em meditação profunda...", "⚡ Cultivando... +1.2K CB/hora", "🏃 Em expedição..."],
    realm: "Reino",
    spiritRoot: "Raiz Espiritual",
    spiritRootLow: "Baixa",
    cbPerHour: "CB/hora",
    power: "Poder",
    soul: "Alma",
    perception: "Percepção",
    luck: "Sorte",
    spiritualJade: "Jade Espiritual",
    stones: "Pedras",
    status: "Estado",
    companion: "Companheiro",
    nextAdvance: "Próximo avanço",
    premium: "💎 Domínio Premium / VIP",
    ranking: "🏆 Ranking",
    celestialAnomalies: "🌩️ Anomalias Celestiais",
    help: "❓ Ajuda",
    cbTracking: "CB em tempo real",
    idleProgress: "Progresso idle",
  },
  footer: {
    copyright: "Nivrael: Path of Immortals © 2026",
    privacy: "Política de Privacidade",
    terms: "Termos de Serviço",
    contact: "Contato",
    builtWith: "Construído com Dao e Python 🐍",
    betaVersion: "Beta Aberto v0.1",
  },
};

const es: Translations = {
  nav: {
    features: "Características",
    realms: "Reinos",
    community: "Comunidad",
    feedback: "Feedback",
  },
  hero: {
    subtitle: "Camino de los Inmortales",
    narrativeIntro: "En el mundo de Qiankun, donde el Qi fluye entre los cielos y la tierra, un mortal descubre el Dao y comienza el viaje hacia la Inmortalidad...",
    tagline: "Un RPG idle de cultivo Xianxia con un mundo que anda solo: nueve casas con rencillas viejas, cinco ciudades que quieren algo hoy, y un cielo con humor. Juega dentro de Telegram — o solo mira el mundo primero.",
    cta: "ENTRAR AL MUNDO",
    playCta: "JUGAR AHORA",
    worldCta: "VER EL MUNDO",
    secondaryCta: "Descubrir los Reinos",
    badge: "⚡ LAS PUERTAS DEL CULTIVO ESTÁN ABIERTAS",
  },
  features: {
    title: "Domina las Artes del Cultivo",
    subtitle: "De Mortal a Inmortal Verdadero, en un mundo que sigue andando mientras no estás. Míralo en vivo antes de instalar nada.",
    items: [
      { title: "Cultivo Ocioso", description: "Cultiva Qi todo el tiempo, conectado o no. Once reinos, nueve subcapas cada uno — y una Fundación cuya pureza cargas el resto de tu vida." },
      { title: "Un Mundo Que Anda", description: "Nueve casas NPC saquean, se recluyen y cazan herencias a su propio ritmo. Lee la Crónica para descubrir qué hizo el mundo mientras no estabas." },
      { title: "Cinco Ciudades, Cinco Tierras", description: "Línghé, Qiānhé, Yǎnshān, Fēnghuǒ y la prohibida Mòyǔ. Cada una tiene una ciudad con nombre que QUIERE algo ahora, y una tierra que prospera, se tensa, cae bajo asedio — o bajo bandera extranjera." },
      { title: "天时 El Tiempo del Cielo", description: "El cielo tiene humor. Un Cielo Airado vuelve toda tribulación 12% más cruel; un Velo de Nubes la vuelve 12% más benigna. Gira cada 12 horas — y dice cuál viene después. El único futuro escrito del juego." },
      { title: "Tribulaciones Celestiales", description: "Nueve rondas de rayo desde un cielo que te quiere muerto. Resistir, Esquivar o Absorber — cada ronda, decisión tuya. Un fallo lo termina todo." },
      { title: "Alquimia Profunda", description: "41 recetas de píldora en 7 grados de caldero. Tu rango de alquimia compra la llama misma: los rangos altos guardan más energía y la recargan más rápido — quien acorta la espera es la maestría, no la billetera." },
      { title: "El Jiānghú", description: "Los cultivadores NPC no son estatuas. Marchan sobre continentes, cobran los contratos que nadie reclamó, saldan deudas de sangre entre ellos — y te emboscan a TI, donde puedes pelear, sobornar o huir." },
      { title: "Bibliotecas y Estantes Sellados", description: "129 técnicas, y las buenas están bajo llave. Gana los estantes Externo, Interno y del Núcleo de tu casa; pruébate para las cámaras selladas; y una casa guarda una Bóveda Prohibida cuyas artes te cuestan años de vida." },
      { title: "Cuerpo, Meridianos y Raíz", description: "Cultivar no es solo Qi. Templa el cuerpo mortal, abre doce meridianos un ritual a la vez, cultiva un huerto espiritual, caza esencia — y deja que tu Raíz Espiritual decida qué elementos te permite tocar el Dao." },
      { title: "Bestias y 23 Mazmorras", description: "Captura y vincula 15 especies del Común al Divino — compañeras, monturas o expediciones que corren mientras duermes. Y cada portal de mazmorra está anclado a un lugar real del mapa." },
      { title: "Un Oficio Propio", description: "Elige una profesión que muerde los motores de verdad — alquimia, forja, sanación — y lee el Informe del Mercado Imperial para saber de qué anda escaso el mundo esta semana." },
      { title: "Economía Viva y la Caravana", description: "Un mercado movido por jugadores, más el viejo maestro de la caravana: todo material nace en algún lugar, y lo que tu montaña no da, él lo manda traer. Siempre a una razón mala — y te lo dice en la cara." },
    ],
  },
  preview: {
    title: "Tu Cultivo te Espera",
    subtitle: "Juega 100% dentro de Telegram — sin descargas. O abre el mundo en vivo en tu navegador antes: sin cuenta, sin instalar nada.",
  },
  realms: {
    title: "El Camino de la Inmortalidad",
    subtitle: "11 Reinos de Ascensión. Cada reino tiene 9 sub-capas de progresión. Domina la Pureza de Base, sobrevive a las Tribulaciones Celestiales y trasciende la mortalidad.",
    names: [
      "Mortal", "Condensación de Qi", "Establecimiento de Base", "Formación del Núcleo",
      "Alma Naciente", "Transformación del Alma", "Refinamiento del Vacío", "Integración Corporal",
      "Mahayana", "Trascendencia de la Tribulación", "Verdadero Inmortal",
    ],
    descriptions: [
      "凡人 · Nacido de carne y destino. Percibes el mundo con ojos mortales — ajeno al Qi que impregna cada aliento. El camino a la Inmortalidad comienza con un solo paso.\n\n⚡ Avance: 1K CB · Multiplicador: 1.0×",
      "聚气期 · El primer gran despertar. Tus meridianos se abren como compuertas y el Qi irrumpe. Nueve sub-capas de condensación aguardan antes de que tu Base pueda ser establecida.\n\n⚡ Avance: 10K CB · Multiplicador: 2.5×",
      "筑基期 · La etapa más crítica de todas. Tu Pureza de Base (0–100%) determina todo tu futuro. Alcanza el 100% para un bono permanente de 5× — una Base Perfecta que los propios dioses envidiarían.\n\n⚡ Avance: 100K CB · Multiplicador: 6× · 🔑 Sistema de Pureza de Base",
      "结丹期 · En lo profundo de tu dantian, el Qi bruto cristaliza en un Núcleo Dorado (金丹) — un tesoro codiciado por demonios e inmortales. La división entre cultivadores y mortales se cruza para siempre.\n\n⚡ Avance: 1M CB · Multiplicador: 15×",
      "元婴期 · Tu alma despierta como entidad separada e inmortal dentro de tu Núcleo Dorado. Los Cielos toman nota. Desde aquí, debes sobrevivir Tribulaciones Celestiales para avanzar — no hay otro camino.\n\n⚡ Avance: 10M CB · Multiplicador: 40× · ⚡ Comienzan las Tribulaciones",
      "化神期 · Has trascendido los límites de la carne. La realidad se doblega a tu voluntad. Domina Heaven's Wrath — golpea los cielos antes de que te golpeen — y doblega las leyes de la naturaleza a tu Dao.\n\n⚡ Avance: 100M CB · Multiplicador: 100× · 🌩️ Técnica Heaven's Wrath",
      "炼虚期 · El propio espacio se convierte en tu arma. Rasga grietas en el tejido de la existencia con Void Slash. La frontera entre mundos se vuelve fina como papel bajo tu mirada.\n\n⚡ Avance: 1B CB · Multiplicador: 250× · 🌀 Void Slash desbloqueado",
      "合体期 · Cielo y Tierra se disuelven en tu cuerpo. Cada meridiano carga el peso de montañas. Te conviertes en una fuerza viva de la naturaleza — ya no un ser que habita el mundo, sino uno que ES el mundo.\n\n⚡ Avance: 10B CB · Multiplicador: 600×",
      "大乘期 · El Gran Vehículo. Busca 108 fragmentos del Dao eterno — Velocidad, Destrucción, Vida, Tiempo, Creación. Completa el conjunto para desbloquear el Dao Eterno y situarte en el umbral de la divinidad.\n\n⚡ Avance: 100B CB · Multiplicador: 1.500× · ☯️ Dao Eterno (108 fragmentos)",
      "渡劫期 · Nueve rondas de relámpagos celestiales descienden de un cielo que quiere verte muerto. Elige tu destino cada ronda: Resistir (poder bruto), Esquivar (velocidad e ingenio) o Absorber (convertir el rayo en fuerza). Un fallo lo termina todo.\n\n⚡ Avance: 1T CB · Multiplicador: 4.000× · ⚡ 9 rondas de Tribulación",
      "真仙 · Has abandonado la mortalidad para siempre. El velo entre los Cielos y el mundo mortal se disuelve a tus pies. El Sistema de Prestigio se desbloquea — destruye tu poder y comienza de nuevo, llevando bonos permanentes en un bucle eterno de ascensión.\n\n✨ Multiplicador: 10.000× · 🔄 Sistema de Prestigio · ∞ Ascensión Eterna",
    ],
  },
  community: {
    title: "Únete a la Secta",
    subtitle: "El mundo de Qiankun está en beta abierta. Las puertas están abiertas, y los Ancianos leen cada reporte.",
    counter: "cultivadores ya recorrieron el camino",
    bot: "Entrar al Mundo",
    botDesc: "Comienza tu viaje de cultivo ahora",
    channel: "Decretos Celestiales",
    channelDesc: "Anuncios oficiales de los Ancianos",
    group: "Salón de la Secta",
    groupDesc: "Chatea con otros cultivadores",
  },
  feedback: {
    title: "Tu Voz Moldea los Cielos",
    subtitle: "Como beta tester, tu sabiduría ayuda a forjar el destino de Nivrael. Los Ancianos Celestiales escuchan tu consejo.",
    lore: "Cada bug que encuentras sella una fisura en la realidad. Cada sugerencia planta una semilla de poder cósmico.",
    bugReport: "Reportar una Fisura",
    bugReportDesc: "¿Encontraste un bug? Ayúdanos a sellar las grietas en la realidad.",
    suggest: "Ofrecer Sabiduría",
    suggestDesc: "Sugiere funciones que moldearán el futuro de Nivrael.",
    review: "Comparte Tu Camino",
    reviewDesc: "Cuéntanos tu experiencia de cultivo hasta ahora.",
  },
  gamePreview: {
    actions: ["🌿 Cultivo y Base", "⚔️ Aventura y Combate", "👥 Comunidad y Comercio", "🔨 Taller Central"],
    estados: ["⚡ Cultivando... +1.2K CB/hora", "🧘 En meditación profunda...", "⚡ Cultivando... +1.2K CB/hora", "🏃 En expedición..."],
    realm: "Reino",
    spiritRoot: "Raíz Espiritual",
    spiritRootLow: "Baja",
    cbPerHour: "CB/hora",
    power: "Poder",
    soul: "Alma",
    perception: "Percepción",
    luck: "Suerte",
    spiritualJade: "Jade Espiritual",
    stones: "Piedras",
    status: "Estado",
    companion: "Compañero",
    nextAdvance: "Próximo avance",
    premium: "💎 Dominio Premium / VIP",
    ranking: "🏆 Ranking",
    celestialAnomalies: "🌩️ Anomalías Celestiales",
    help: "❓ Ayuda",
    cbTracking: "CB en tiempo real",
    idleProgress: "Progreso idle",
  },
  footer: {
    copyright: "Nivrael: Path of Immortals © 2026",
    privacy: "Política de Privacidad",
    terms: "Términos de Servicio",
    contact: "Contacto",
    builtWith: "Construido con Dao y Python 🐍",
    betaVersion: "Beta Abierta v0.1",
  },
};

export const translations: Record<Language, Translations> = { en, pt, es };

export const languageLabels: Record<Language, { flag: string; label: string }> = {
  en: { flag: "🇬🇧", label: "English" },
  pt: { flag: "🇧🇷", label: "Português" },
  es: { flag: "🇪🇸", label: "Español" },
};
