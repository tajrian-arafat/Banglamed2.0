import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, clearTokens, getToken, setTokens } from "./api";

export type Role = "patient" | "doctor" | "hospital_admin" | "system_admin";
export interface Me { id: number; username: string; role: Role; account_type: string; full_name: string; email?: string | null; }

interface AuthCtx {
  me: Me | null;
  loading: boolean;
  login: (u: string, p: string) => Promise<Me>;
  register: (payload: { username: string; password: string; full_name: string; account_type: string }) => Promise<Me>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    if (!getToken()) { setMe(null); setLoading(false); return; }
    try {
      const m = await api.get<Me>("/api/auth/me");
      setMe(m);
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function login(username: string, password: string) {
    const r = await api.post<{ access_token: string; refresh_token: string; role: Role; user_id: number; full_name: string }>(
      "/api/auth/login", { username, password });
    setTokens(r.access_token, r.refresh_token);
    const m = await api.get<Me>("/api/auth/me");
    setMe(m);
    return m;
  }

  async function register(payload: { username: string; password: string; full_name: string; account_type: string }) {
    const r = await api.post<{ access_token: string; refresh_token: string }>("/api/auth/register", payload);
    setTokens(r.access_token, r.refresh_token);
    const m = await api.get<Me>("/api/auth/me");
    setMe(m);
    return m;
  }

  function logout() {
    api.post("/api/auth/logout").catch(() => {});
    clearTokens();
    setMe(null);
  }

  return <Ctx.Provider value={{ me, loading, login, register, logout, refresh }}>{children}</Ctx.Provider>;
}

export function useAuth() { return useContext(Ctx); }
