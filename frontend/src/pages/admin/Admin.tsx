import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { timeStr } from "../../core/format";
import { Loading, Stat, useToast } from "../../design-system/UI";
import { IconDatabase, IconUser, IconSettings, IconShield } from "../../design-system/Icons";

interface Sys { counts: Record<string, number>; data_status: { unverified: number; verified: number }; }
interface U { id: number; username: string; role: string; full_name: string; is_active: boolean; }
interface A { id: number; ts: string; actor_id: number | null; action: string; entity: string | null; entity_id: string | null; }
interface M { modules: { id: string; name: string; enabled: boolean; requires: string[] }[]; problems: string[]; }

export default function AdminPanel() {
  const [sys, setSys] = useState<Sys | null>(null);
  const [users, setUsers] = useState<U[]>([]);
  const [audit, setAudit] = useState<A[]>([]);
  const [mods, setMods] = useState<M | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("overview");
  const { toast, toastNode } = useToast();

  useEffect(() => {
    Promise.all([
      api.get<Sys>("/api/analytics/system").catch(() => null),
      api.get<{ results: U[] }>("/api/admin/users").catch(() => ({ results: [] })),
      api.get<{ results: A[] }>("/api/admin/audit?limit=40").catch(() => ({ results: [] })),
      api.get<M>("/api/admin/modules").catch(() => null),
    ]).then(([s, u, a, m]) => { setSys(s); setUsers(u.results); setAudit(a.results); setMods(m); }).finally(() => setLoading(false));
  }, []);

  async function toggle(id: number) {
    await api.post(`/api/admin/users/${id}/toggle`); toast("User updated");
    const u = await api.get<{ results: U[] }>("/api/admin/users"); setUsers(u.results);
  }

  if (loading) return <div className="container"><Loading /></div>;

  return (
    <div className="container">
      {toastNode}
      <h1>System admin</h1>
      <p className="muted">Catalog health, users, audit trail and module registry.</p>
      <div className="tabs">
        {["overview", "users", "audit", "modules"].map((t) => (
          <button key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)} style={{ textTransform: "capitalize" }}>{t}</button>
        ))}
      </div>

      {tab === "overview" && sys && (
        <>
          <div className="grid grid-4" style={{ marginTop: 18 }}>
            <Stat label="Brands" value={sys.counts.brands?.toLocaleString()} />
            <Stat label="Generics" value={sys.counts.generics?.toLocaleString()} />
            <Stat label="Companies" value={sys.counts.companies?.toLocaleString()} />
            <Stat label="Doctors" value={sys.counts.doctors?.toLocaleString()} />
            <Stat label="Hospitals" value={sys.counts.hospitals?.toLocaleString()} />
            <Stat label="Tests" value={sys.counts.tests?.toLocaleString()} />
            <Stat label="Users" value={sys.counts.users?.toLocaleString()} />
            <Stat label="Prescriptions" value={sys.counts.prescriptions?.toLocaleString()} />
          </div>
          <div className="glass card" style={{ marginTop: 18 }}>
            <h3 style={{ marginTop: 0 }}><IconDatabase size={18} /> Data verification</h3>
            <div className="row wrap" style={{ gap: 10 }}>
              <span className="badge">Unverified: {sys.data_status.unverified?.toLocaleString()}</span>
              <span className="badge badge-accent">Verified: {sys.data_status.verified?.toLocaleString()}</span>
            </div>
          </div>
        </>
      )}

      {tab === "users" && (
        <div className="glass card" style={{ marginTop: 18 }}>
          <h3 style={{ marginTop: 0 }}><IconUser size={18} /> Users</h3>
          {users.map((u) => (
            <div key={u.id} className="list-row">
              <div><div className="name">{u.full_name || u.username}</div><div className="tiny muted">@{u.username} · {u.role}</div></div>
              <div className="row" style={{ gap: 6 }}>
                <span className={`badge ${u.is_active ? "badge-accent" : "badge-warn"}`}>{u.is_active ? "active" : "disabled"}</span>
                <button className="btn btn-sm btn-ghost" onClick={() => toggle(u.id)}>{u.is_active ? "Disable" : "Enable"}</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "audit" && (
        <div className="glass card" style={{ marginTop: 18 }}>
          <h3 style={{ marginTop: 0 }}><IconShield size={18} /> Audit trail</h3>
          {audit.map((a) => (
            <div key={a.id} className="list-row">
              <div><div className="name">{a.action}</div><div className="tiny muted">{a.entity || "—"} {a.entity_id || ""} · actor #{a.actor_id ?? "—"}</div></div>
              <span className="tiny muted">{timeStr(a.ts)}</span>
            </div>
          ))}
        </div>
      )}

      {tab === "modules" && mods && (
        <div className="glass card" style={{ marginTop: 18 }}>
          <h3 style={{ marginTop: 0 }}><IconSettings size={18} /> Module registry</h3>
          {mods.problems.length > 0 && <div className="alert alert-error">{mods.problems.join("; ")}</div>}
          <div className="grid grid-3">
            {mods.modules.map((m) => (
              <div key={m.id} className="list-row">
                <div><div className="name">{m.name}</div><div className="tiny muted">{m.id}{m.requires.length ? ` · needs ${m.requires.join(", ")}` : ""}</div></div>
                <span className={`badge ${m.enabled ? "badge-accent" : "badge-warn"}`}>{m.enabled ? "on" : "off"}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
