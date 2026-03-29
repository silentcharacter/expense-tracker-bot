import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

type ColorScheme = "light" | "dark";

interface ThemeContextValue {
  colorScheme: ColorScheme;
}

const ThemeContext = createContext<ThemeContextValue>({ colorScheme: "light" });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const tg = window.Telegram?.WebApp;
  const [colorScheme, setColorScheme] = useState<ColorScheme>(
    tg?.colorScheme ?? "light"
  );

  useEffect(() => {
    if (!tg) return;

    const handleThemeChange = () => {
      setColorScheme(tg.colorScheme ?? "light");
    };

    tg.onEvent("themeChanged", handleThemeChange);
    return () => {
      tg.offEvent("themeChanged", handleThemeChange);
    };
  }, [tg]);

  return (
    <ThemeContext.Provider value={{ colorScheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
