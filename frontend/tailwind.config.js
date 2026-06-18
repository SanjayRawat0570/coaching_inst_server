/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./pages/**/*.{js,jsx}", "./components/**/*.{js,jsx}"],
  // Colors applied dynamically (text-${color}/bg-${color}) need safelisting so
  // the JIT generates them even though they're not literal strings in the source.
  safelist: [
    "text-neon-cyan", "text-neon-violet", "text-neon-green", "text-neon-amber", "text-neon-rose",
    "bg-neon-cyan", "bg-neon-violet", "bg-neon-green", "bg-neon-amber", "bg-neon-rose",
  ],
  theme: {
    extend: {
      colors: {
        // Dark control-room surfaces
        ink: {
          950: "#070b18",
          900: "#0b1120",
          800: "#111a2e",
          700: "#1a2540",
          600: "#26324f",
        },
        brand: {
          DEFAULT: "#7c5cff", // violet
          dark: "#6442e6",
        },
        neon: {
          cyan: "#22d3ee",
          violet: "#a78bfa",
          green: "#34d399",
          amber: "#fbbf24",
          rose: "#fb7185",
        },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(124,92,255,0.25), 0 8px 30px -8px rgba(124,92,255,0.45)",
        "glow-cyan": "0 0 0 1px rgba(34,211,238,0.25), 0 8px 30px -8px rgba(34,211,238,0.4)",
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 10px 30px -12px rgba(0,0,0,0.6)",
      },
      backgroundImage: {
        "brand-grad": "linear-gradient(135deg,#7c5cff 0%,#22d3ee 100%)",
        "brand-soft": "linear-gradient(135deg,rgba(124,92,255,0.18),rgba(34,211,238,0.12))",
        grid: "radial-gradient(circle at 1px 1px, rgba(148,163,184,0.10) 1px, transparent 0)",
      },
      keyframes: {
        floaty: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-6px)" } },
        pulseGlow: {
          "0%,100%": { opacity: 0.6 },
          "50%": { opacity: 1 },
        },
      },
      animation: {
        floaty: "floaty 6s ease-in-out infinite",
        "pulse-glow": "pulseGlow 3s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
