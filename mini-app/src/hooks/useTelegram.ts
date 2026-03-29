import { useEffect } from "react";

export function useTelegram() {
  const tg = window.Telegram?.WebApp;

  useEffect(() => {
    if (!tg) return;

    tg.expand();
    tg.enableClosingConfirmation();
    tg.setHeaderColor("secondary_bg_color");
    tg.ready();
  }, [tg]);

  return {
    tg,
    user: tg?.initDataUnsafe?.user,
    colorScheme: tg?.colorScheme,
    viewportHeight: tg?.viewportStableHeight,
    hapticFeedback: tg?.HapticFeedback,
    close: () => tg?.close(),
    showConfirm: (message: string) =>
      new Promise<boolean>((resolve) => tg?.showConfirm(message, resolve)),
  };
}
