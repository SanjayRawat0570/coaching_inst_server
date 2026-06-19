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
          DEFAULT: "#4f46e5", // indigo-600
          dark: "#4338ca",    // indigo-700
          light: "#6366f1",   // indigo-500
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
        sans: ['"Inter var"', "Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
      },
      boxShadow: {
        // Soft, layered elevation — the premium default for surfaces.
        soft: "0 1px 2px rgba(16,24,40,0.04), 0 2px 6px rgba(16,24,40,0.04)",
        "soft-md": "0 2px 4px rgba(16,24,40,0.04), 0 8px 20px -6px rgba(16,24,40,0.10)",
        "soft-lg": "0 4px 10px -2px rgba(16,24,40,0.06), 0 18px 40px -12px rgba(16,24,40,0.16)",
        // "glow" kept as a token name for compatibility, but now a neutral soft
        // elevation — no colored halo (cleaner, more professional).
        glow: "0 1px 2px rgba(16,24,40,0.05), 0 6px 16px -6px rgba(16,24,40,0.12)",
        "glow-cyan": "0 1px 2px rgba(16,24,40,0.05), 0 6px 16px -6px rgba(16,24,40,0.12)",
        card: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 12px 36px -16px rgba(0,0,0,0.55)",
      },
      backgroundImage: {
        // Solid brand fill (kept under the "grad" name for compatibility).
        "brand-grad": "linear-gradient(#4f46e5,#4f46e5)",
        "brand-soft": "linear-gradient(rgba(79,70,229,0.08),rgba(79,70,229,0.08))",
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
