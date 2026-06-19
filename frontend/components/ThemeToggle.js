import { useTheme } from "../lib/useTheme";
import Icon from "./Icon";

export default function ThemeToggle({ className = "" }) {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-label="Toggle theme"
      className={
        "grid place-items-center h-9 w-9 rounded-xl border border-slate-200 bg-white/60 text-slate-600 hover:bg-slate-100 hover:text-slate-900 " +
        "dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-300 dark:hover:bg-white/[0.07] dark:hover:text-white transition " +
        className
      }
    >
      <Icon name={theme === "dark" ? "sun" : "moon"} size={17} />
    </button>
  );
}
