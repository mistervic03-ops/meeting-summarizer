import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

type ThemeMode = "dark" | "light";

const THEME_STORAGE_KEY = "meeting-summarizer-theme";

/**
 * 저장된 테마 값을 읽고, 없으면 기본값인 라이트 모드를 반환합니다.
 */
function getInitialTheme(): ThemeMode {
  if (typeof window === "undefined") {
    return "light";
  }

  return window.localStorage.getItem(THEME_STORAGE_KEY) === "dark" ? "dark" : "light";
}

/**
 * 문서 루트에 현재 테마 클래스를 적용합니다.
 */
function applyTheme(theme: ThemeMode) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

interface ThemeToggleProps {
  compact?: boolean;
}

/**
 * 조용한 라이트/다크 모드 전환 버튼을 렌더링합니다.
 */
export default function ThemeToggle({ compact = false }: ThemeToggleProps) {
  const [theme, setTheme] = useState<ThemeMode>(getInitialTheme);
  const isDark = theme === "dark";
  const label = isDark ? "라이트 모드로 전환" : "다크 모드로 전환";

  useEffect(() => {
    applyTheme(theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  return (
    <button
      aria-label={label}
      title={label}
      className={[
        "inline-flex h-7 shrink-0 items-center justify-center rounded-md border border-slate-200 bg-white text-[11px] font-medium text-slate-500 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-800 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:border-app-border dark:bg-app-surface dark:text-app-muted dark:hover:bg-app-hover dark:hover:text-app-text dark:focus-visible:border-app-accent-border dark:focus-visible:ring-app-accent-border",
        compact ? "w-7 px-0" : "gap-1.5 px-2"
      ].join(" ")}
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? <Sun className="shrink-0" size={13} /> : <Moon className="shrink-0" size={13} />}
      {compact ? null : isDark ? "Light" : "Dark"}
    </button>
  );
}
