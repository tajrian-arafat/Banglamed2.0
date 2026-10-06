import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../core/auth";
import { ApiError } from "../core/api";

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ full_name: "", username: "", password: "", account_type: "personal" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  function set(k: string, v: string) { setForm((f) => ({ ...f, [k]: v })); }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      await register(form);
      nav("/patient");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Registration failed");
    } finally { setBusy(false); }
  }

  return (
    <div className="container narrow">
      <div className="glass card auth-card">
        <h1 style={{ marginTop: 0 }}>Create your account</h1>
        <p className="muted small">Keep your prescriptions, records and reminders in one place.</p>
        <form onSubmit={submit} className="col" style={{ gap: 12, marginTop: 16 }}>
          <label className="field"><span>Full name</span>
            <input className="input" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} required />
          </label>
          <label className="field"><span>Username</span>
            <input className="input" value={form.username} onChange={(e) => set("username", e.target.value)} required minLength={3} />
          </label>
          <label className="field"><span>Password</span>
            <input className="input" type="password" value={form.password} onChange={(e) => set("password", e.target.value)} required minLength={6} />
          </label>
          <label className="field"><span>Account type</span>
            <select className="input" value={form.account_type} onChange={(e) => set("account_type", e.target.value)}>
              <option value="personal">Personal</option>
              <option value="family">Family (manage relatives)</option>
            </select>
          </label>
          {err && <div className="alert alert-error">{err}</div>}
          <button className="btn btn-primary" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
        </form>
        <p className="muted small" style={{ marginTop: 14 }}>
          Already registered? <Link to="/login" className="link">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
