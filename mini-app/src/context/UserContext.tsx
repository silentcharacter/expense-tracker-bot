import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { fetchSettings } from "../api/settings";
import type { UserSettings } from "../api/types";
import { deviceTimeZone, isValidTimeZone, todayInTz } from "../utils/dates";

interface UserContextValue {
  user: UserSettings | null;
  isLoading: boolean;
  error: string | null;
  refreshUser: () => Promise<void>;
  /** Effective IANA timezone (device zone only if settings failed to load). */
  timezone: string;
  /** "Today" as YYYY-MM-DD in `timezone`. */
  today: string;
  /** True when the user has no personal timezone (server default is used). */
  timezoneIsDefault: boolean;
  /** Today's YYYY-MM-DD in `timezone`, computed from the current clock. */
  todayInTz: () => string;
}

const initialTz = deviceTimeZone();

const UserContext = createContext<UserContextValue>({
  user: null,
  isLoading: true,
  error: null,
  refreshUser: async () => {},
  timezone: initialTz,
  today: todayInTz(initialTz),
  timezoneIsDefault: true,
  todayInTz: () => todayInTz(initialTz),
});

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshUser = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const settings = await fetchSettings();
      setUser(settings);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load user");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const value = useMemo<UserContextValue>(() => {
    // The device zone is only a fallback for a failed settings load (or a
    // response that omits/garbles the zone), never the normal path.
    const tz =
      user?.timezone && isValidTimeZone(user.timezone) ? user.timezone : deviceTimeZone();
    const serverToday =
      user?.timezone && user.today && /^\d{4}-\d{2}-\d{2}$/.test(user.today)
        ? user.today
        : null;
    return {
      user,
      isLoading,
      error,
      refreshUser,
      timezone: tz,
      today: serverToday ?? todayInTz(tz),
      timezoneIsDefault: user ? (user.timezone_is_default ?? !user.timezone) : true,
      todayInTz: () => todayInTz(tz),
    };
  }, [user, isLoading, error, refreshUser]);

  return (
    <UserContext.Provider value={value}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser(): UserContextValue {
  return useContext(UserContext);
}
