import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./pages/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      fontFamily: {
        cinzel: ["Cinzel", "serif"],
        inter: ["Inter", "sans-serif"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        gold: {
          DEFAULT: "hsl(var(--gold))",
          dim: "hsl(var(--gold-dim))",
        },
        celestial: {
          DEFAULT: "hsl(var(--celestial))",
          glow: "hsl(var(--celestial-glow))",
        },
        qi: {
          cyan: "hsl(var(--qi-cyan))",
        },
        void: {
          DEFAULT: "hsl(var(--void-dark))",
          deep: "hsl(var(--void-deeper))",
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar-background))",
          foreground: "hsl(var(--sidebar-foreground))",
          primary: "hsl(var(--sidebar-primary))",
          "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          border: "hsl(var(--sidebar-border))",
          ring: "hsl(var(--sidebar-ring))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "badge-glow": {
          "0%,100%": { boxShadow: "0 0 10px rgba(255,215,0,0.4),0 0 20px rgba(255,215,0,0.2)" },
          "50%":      { boxShadow: "0 0 20px rgba(255,215,0,0.7),0 0 40px rgba(255,215,0,0.4),0 0 60px rgba(255,215,0,0.2)" },
        },
        "hero-title-glow": {
          "0%,100%": { textShadow: "0 0 20px rgba(255,215,0,0.5),0 0 40px rgba(255,215,0,0.3)" },
          "50%":     { textShadow: "0 0 30px rgba(255,215,0,0.9),0 0 60px rgba(255,215,0,0.6),0 0 90px rgba(255,215,0,0.3)" },
        },
        "shimmer-fast": {
          "0%":   { transform: "translateX(-150%) skewX(12deg)" },
          "100%": { transform: "translateX(250%) skewX(12deg)" },
        },
        "float-orbit": {
          "0%,100%": { transform: "translateY(0px) rotate(0deg)" },
          "33%":     { transform: "translateY(-14px) rotate(3deg)" },
          "66%":     { transform: "translateY(-6px) rotate(-2deg)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "badge-glow": "badge-glow 2s ease-in-out infinite",
        "hero-title-glow": "hero-title-glow 3s ease-in-out infinite",
        "shimmer-fast": "shimmer-fast 1.5s infinite linear",
        "float-orbit": "float-orbit 5s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
