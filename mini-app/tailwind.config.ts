import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "'Segoe UI'", "Roboto", "sans-serif"],
      },
      colors: {
        tg: {
          bg: "var(--tg-theme-bg-color)",
          text: "var(--tg-theme-text-color)",
          hint: "var(--tg-theme-hint-color)",
          link: "var(--tg-theme-link-color)",
          button: "var(--tg-theme-button-color)",
          "button-text": "var(--tg-theme-button-text-color)",
          "secondary-bg": "var(--tg-theme-secondary-bg-color)",
          "header-bg": "var(--tg-theme-header-bg-color)",
          accent: "var(--tg-theme-accent-text-color)",
          "section-bg": "var(--tg-theme-section-bg-color)",
          "section-header": "var(--tg-theme-section-header-text-color)",
          subtitle: "var(--tg-theme-subtitle-text-color)",
          destructive: "var(--tg-theme-destructive-text-color)",
        },
      },
      borderRadius: {
        card: "12px",
      },
      spacing: {
        "tab-bar": "56px",
        header: "48px",
      },
    },
  },
  plugins: [],
};

export default config;
