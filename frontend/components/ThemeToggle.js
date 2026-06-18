import { useTheme } from "../lib/useTheme";

export default function ThemeToggle({ className = "" }) {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-label="Toggle theme"
      className={
        "grid place-items-center h-9 w-9 rounded-xl border border-slate-300 text-slate-600 hover:bg-slate-100 " +
        "dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5 transition " +
        className
      }
    >
      {theme === "dark" ? "☀️" : "🌙"}
    </button>
  );
}
