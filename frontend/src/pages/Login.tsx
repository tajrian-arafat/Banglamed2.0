import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../core/auth";
import { ApiError } from "../core/api";

const DEMO = [
  { label: "Patient", u: "patient.demo", p: "Patient@123" },
  { label: "Doctor", u: "dr.rahman", p: "Doctor@123" },
  { label: "Hospital admin", u: "hospital.dhaka", p: "Hospital@123" },
  { label: "System admin", u: "admin", p: "Admin@123" },
];

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const me = await login(username, password);
      nav(me.role === "patient" ? "/patient" : me.role === "doctor" ? "/doctor" : me.role === "hospital_admin" ? "/hospital/analytics" : "/admin");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Sign in failed");
    } finally { setBusy(false); }
  }

  return (
    <div className="container narrow">
      <div className="glass card auth-card">
        <h1 style={{ marginTop: 0 }}>Sign in</h1>
        <p className="muted small">Access your prescriptions, records and appointments.</p>
        <form onSubmit={submit} className="col" style={{ gap: 12, marginTop: 16 }}>
          <label className="field"><span>Username</span>
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
          </label>
          <label className="field"><span>Password</span>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </label>
          {err && <div className="alert alert-error">{err}</div>}
          <button className="btn btn-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <p className="muted small" style={{ marginTop: 14 }}>
          No account? <Link to="/register" className="link">Create one</Link>
        </p>
        <div className="divider" />
        <div className="tiny muted" style={{ marginBottom: 8 }}>Demo accounts (seeded)</div>
        <div className="row wrap" style={{ gap: 8 }}>
          {DEMO.map((d) => (
            <button key={d.u} className="btn btn-sm" onClick={() => { setUsername(d.u); setPassword(d.p); }}>{d.label}</button>
          ))}
        </div>
      </div>
    </div>
  );
}
