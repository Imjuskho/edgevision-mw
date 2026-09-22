import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import type { AuthState } from "../types";
import { studioApi } from "../services/api";

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const saved = localStorage.getItem("studio_token");
    if (!saved) {
      return { token: null, user: null, isAuthenticated: false };
    }
    const tokenParts = saved.split(".");
    if (tokenParts.length === 3) {
      try {
        const payload = JSON.parse(atob(tokenParts[1]));
        const now = Math.floor(Date.now() / 1000);
        if (payload.exp && payload.exp < now) {
          localStorage.removeItem("studio_token");
          return { token: null, user: null, isAuthenticated: false };
        }
      } catch {
        localStorage.removeItem("studio_token");
        return { token: null, user: null, isAuthenticated: false };
      }
    }
    return { token: saved, user: null, isAuthenticated: true };
  });

  useEffect(() => {
    const saved = localStorage.getItem("studio_token");
    if (!saved || !state.isAuthenticated) return;

    let cancelled = false;

    (async () => {
      try {
        const resp = await studioApi.getCurrentUser();
        if (cancelled) return;
        setState({ token: saved, user: resp.data, isAuthenticated: true });
      } catch {
        if (cancelled) return;
        localStorage.removeItem("studio_token");
        setState({ token: null, user: null, isAuthenticated: false });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [state.isAuthenticated]);

  const login = useCallback(async (email: string, password: string) => {
    const resp = await studioApi.login(email, password);
    const token = resp.data.access_token;
    localStorage.setItem("studio_token", token);
    const profileResp = await studioApi.getCurrentUser();
    setState({ token, user: profileResp.data, isAuthenticated: true });
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      await studioApi.register(email, password, fullName);
      await login(email, password);
    },
    [login]
  );

  const logout = useCallback(() => {
    localStorage.removeItem("studio_token");
    setState({ token: null, user: null, isAuthenticated: false });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
