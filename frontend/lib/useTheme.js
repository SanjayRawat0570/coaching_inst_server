import { useEffect, useState } from "react";

/**
 * Light/dark theme hook. The initial class is set in _document.js before paint;
 * here we read it, expose a toggle, and persist the choice to localStorage.
 */
export function useTheme() {
  const [theme, setTheme] = useState("dark");

  useEffect(() => {
    const isDark = document.documentElement.classList.contains("dark");
    setTheme(isDark ? "dark" : "light");
  }, []);

  const toggle = () => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      document.documentElement.classList.toggle("dark", next === "dark");
      try {
        localStorage.setItem("theme", next);
      } catch (e) {
        /* ignore */
      }
      return next;
    });
  };

  return { theme, toggle };
}
