import { createContext, useCallback, useContext, useRef, useState } from "react";

/**
 * Small toasts, no library: const toast = useToast(); toast("Saved") or
 * toast("Couldn't save", "error"). Announced to screen readers (aria-live).
 */
type Tone = "success" | "error" | "info";
type Item = { id: number; text: string; tone: Tone };

const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => {});

export function ToastProvider({ children }) {
  const [items, setItems] = useState<Item[]>([]);
  const next = useRef(1);

  const show = useCallback((text: string, tone: Tone = "success") => {
    const id = next.current++;
    setItems((xs) => [...xs.slice(-2), { id, text, tone }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), tone === "error" ? 6000 : 3500);
  }, []);

  const toneClass = {
    success: "border-emerald-500/40 bg-emerald-50 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200",
    error: "border-rose-500/40 bg-rose-50 text-rose-800 dark:bg-rose-500/15 dark:text-rose-200",
    info: "border-slate-300 bg-white text-slate-800 dark:border-white/15 dark:bg-ink-800 dark:text-slate-100",
  };

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div aria-live="polite" role="status"
           className="fixed bottom-4 inset-x-4 sm:inset-x-auto sm:right-4 z-50 flex flex-col gap-2 sm:w-80">
        {items.map((t) => (
          <div key={t.id} className={`rounded-xl border px-4 py-3 text-sm shadow-lg ${toneClass[t.tone]}`}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
