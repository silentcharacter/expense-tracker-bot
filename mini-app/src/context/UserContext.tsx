import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchSettings } from "../api/settings";
import type { UserSettings } from "../api/types";

interface UserContextValue {
  user: UserSettings | null;
  isLoading: boolean;
  error: string | null;
  refreshUser: () => Promise<void>;
}

const UserContext = createContext<UserContextValue>({
  user: null,
  isLoading: true,
  error: null,
  refreshUser: async () => {},
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

  return (
    <UserContext.Provider value={{ user, isLoading, error, refreshUser }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser(): UserContextValue {
  return useContext(UserContext);
}
