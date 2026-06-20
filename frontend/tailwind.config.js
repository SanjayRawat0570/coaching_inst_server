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
        // Dark control-room surfaces — plum-tinted to sit under the violet brand
        ink: {
          950: "#0a0712",
          900: "#0e0b16",
          800: "#181426",
          700: "#241d3a",
          600: "#322a4a",
        },
        brand: {
          DEFAULT: "#7c3aed", // violet-600
          dark: "#6d28d9",    // violet-700
          light: "#8b5cf6",   // violet-500
        },
        // Premium highlight — used in gradient accents (headline, CTA sheen)
        accent: "#e879f9",   // fuchsia-400
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
        // Brand-tinted elevation for the primary CTA — premium violet glow.
        brand: "0 1px 2px rgba(124,58,237,0.20), 0 8px 22px -6px rgba(124,58,237,0.45)",
        "brand-lg": "0 2px 4px rgba(124,58,237,0.18), 0 14px 34px -8px rgba(124,58,237,0.50)",
      },
      backgroundImage: {
        // Premium brand gradients — depth on fills, sheen on the headline accent.
        "brand-grad": "linear-gradient(135deg,#8b5cf6 0%,#7c3aed 55%,#6d28d9 100%)",
        "brand-soft": "linear-gradient(rgba(124,58,237,0.08),rgba(124,58,237,0.08))",
        "text-grad": "linear-gradient(100deg,#8b5cf6 0%,#7c3aed 42%,#e879f9 100%)",
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
