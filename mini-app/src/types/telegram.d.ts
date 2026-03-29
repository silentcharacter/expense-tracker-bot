/** Minimal type declarations for Telegram Mini App WebApp API. */

interface TelegramWebAppUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
  photo_url?: string;
}

interface TelegramHapticFeedback {
  impactOccurred(style: "light" | "medium" | "heavy" | "rigid" | "soft"): void;
  notificationOccurred(type: "error" | "success" | "warning"): void;
  selectionChanged(): void;
}

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    user?: TelegramWebAppUser;
    auth_date?: number;
    hash?: string;
  };
  colorScheme: "light" | "dark";
  viewportHeight: number;
  viewportStableHeight: number;
  HapticFeedback: TelegramHapticFeedback;
  expand(): void;
  close(): void;
  ready(): void;
  enableClosingConfirmation(): void;
  setHeaderColor(color: "bg_color" | "secondary_bg_color" | `#${string}`): void;
  showConfirm(message: string, callback: (confirmed: boolean) => void): void;
  onEvent(eventType: string, callback: () => void): void;
  offEvent(eventType: string, callback: () => void): void;
}

interface Window {
  Telegram?: {
    WebApp: TelegramWebApp;
  };
}
