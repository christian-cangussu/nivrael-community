// ─── HeroScene ───────────────────────────────────────────────────────────────
// Lightweight CSS/SVG hero background — replaces Three.js WebGL scene.
// Layers: background image, SVG mountains, mist, Dao circle, CSS particles,
// star twinkle. Zero JS animation loops; all motion via CSS @keyframes.
// ─────────────────────────────────────────────────────────────────────────────

const PARTICLE_COUNT = 20;
const STAR_COUNT = 24;

// Pre-compute random positions so they're stable across renders
const particles = Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
  left: `${(i * 4.7 + 13) % 100}%`,
  delay: `${(i * 0.42) % 8}s`,
  duration: `${6 + (i * 0.67) % 8}s`,
}));

const stars = Array.from({ length: STAR_COUNT }, (_, i) => ({
  left: `${(i * 4.13 + 7) % 100}%`,
  top: `${(i * 3.91 + 5) % 70}%`,
  delay: `${(i * 0.33) % 5}s`,
  duration: `${2 + (i * 0.5) % 3}s`,
}));

const HeroScene = () => {
  return (
    <div className="absolute inset-0 overflow-hidden" aria-hidden="true">
      {/* Layer 1: Background image + gradient overlay */}
      <div className="absolute inset-0">
        <picture>
          <source srcSet="/hero-bg.webp" type="image/webp" />
          <img
            src="/hero-bg.png"
            alt=""
            className="w-full h-full object-cover"
            loading="eager"
            fetchPriority="high"
          />
        </picture>
        <div className="absolute inset-0 bg-gradient-to-b from-[#0a0a0f]/60 via-[#0a0a0f]/30 to-[#0a0a0f]" />
      </div>

      {/* Layer 2: SVG Mountains (3 layers with different opacities) */}
      <svg
        className="absolute bottom-0 w-full"
        viewBox="0 0 1440 400"
        preserveAspectRatio="none"
        style={{ willChange: "auto" }}
      >
        {/* Far mountains — darkest, most subtle */}
        <path
          d="M0,400 L0,260 Q120,140 240,210 Q360,100 480,180 Q600,60 720,160 Q840,80 960,150 Q1080,40 1200,170 Q1320,110 1440,200 L1440,400 Z"
          fill="rgba(10,10,25,0.5)"
        />
        {/* Mid mountains */}
        <path
          d="M0,400 L0,300 Q180,160 360,240 Q540,120 720,210 Q900,100 1080,200 Q1260,140 1440,260 L1440,400 Z"
          fill="rgba(10,10,20,0.65)"
        />
        {/* Front mountains — most opaque */}
        <path
          d="M0,400 L0,340 Q240,220 480,300 Q720,180 960,280 Q1200,200 1440,320 L1440,400 Z"
          fill="rgba(10,10,20,0.85)"
        />
      </svg>

      {/* Layer 3: Mist / cloud drift layers */}
      <div className="hero-mist-1 absolute bottom-20 left-0 w-[200%] h-32 opacity-20 will-change-transform" />
      <div className="hero-mist-2 absolute bottom-40 left-0 w-[200%] h-24 opacity-[0.15] will-change-transform" />

      {/* Layer 4: Dao circle (道 in rotating golden ring) */}
      <div className="hero-dao-circle absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2">
        <div className="w-32 h-32 md:w-48 md:h-48 rounded-full border border-[#FFD700]/30 hero-dao-spin flex items-center justify-center will-change-transform">
          <span className="text-4xl md:text-6xl text-[#FFD700]/40 hero-dao-glow select-none">
            道
          </span>
        </div>
      </div>

      {/* Layer 5: CSS Particles (max 20 floating dots) */}
      <div className="hero-particles absolute inset-0 pointer-events-none">
        {particles.map((p, i) => (
          <div
            key={i}
            className="hero-particle will-change-transform"
            style={{
              left: p.left,
              animationDelay: p.delay,
              animationDuration: p.duration,
            }}
          />
        ))}
      </div>

      {/* Layer 6: Star twinkle (tiny dots that fade in/out) */}
      <div className="hero-stars absolute inset-0 pointer-events-none">
        {stars.map((s, i) => (
          <div
            key={i}
            className="hero-star"
            style={{
              left: s.left,
              top: s.top,
              animationDelay: s.delay,
              animationDuration: s.duration,
            }}
          />
        ))}
      </div>
    </div>
  );
};

export default HeroScene;
