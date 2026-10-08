import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { bdt, dateStr } from "../../core/format";
import { Loading, useToast } from "../../design-system/UI";
import { IconPlus } from "../../design-system/Icons";

interface Prof { id: number; name: string; }
interface S { id: number; doctor_id: number; doctor_name: string | null; date: string; total_serials: number; booked: number; available: number; session_start: string | null; session_end: string | null; fee: number | null; }

export default function DoctorSchedule() {
  const [prof, setProf] = useState<Prof | null>(null);
  const [rows, setRows] = useState<S[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ date: "", total_serials: 30, session_start: "17:00", session_end: "21:00", fee: 800 });
  const { toast, toastNode } = useToast();

  function load() {
    if (!prof) return;
    setLoading(true);
    api.get<{ results: S[] }>(`/api/appointments/schedules?doctor_id=${prof.id}`).then((r) => setRows(r.results)).finally(() => setLoading(false));
  }

  useEffect(() => { api.get<Prof>("/api/doctor/profile").then(setProf).catch(() => {}); }, []);
  useEffect(load, [prof]);

  async function create() {
    if (!prof || !form.date) return;
    await api.post("/api/appointments/schedules", { doctor_id: prof.id, ...form });
    toast("Schedule created"); setForm({ ...form, date: "" }); load();
  }

  return (
    <div className="container">
      {toastNode}
      <h1>My schedules</h1>
      <p className="muted">Publish serial-based sessions for patients to book.</p>
      <div className="glass card" style={{ marginBottom: 18 }}>
        <h3 style={{ marginTop: 0 }}><IconPlus size={18} /> New schedule</h3>
        <div className="grid grid-4">
          <label className="field"><span>Date</span><input className="input" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
          <label className="field"><span>Total serials</span><input className="input" type="number" value={form.total_serials} onChange={(e) => setForm({ ...form, total_serials: Number(e.target.value) })} /></label>
          <label className="field"><span>Start</span><input className="input" value={form.session_start} onChange={(e) => setForm({ ...form, session_start: e.target.value })} /></label>
          <label className="field"><span>End</span><input className="input" value={form.session_end} onChange={(e) => setForm({ ...form, session_end: e.target.value })} /></label>
          <label className="field"><span>Fee (BDT)</span><input className="input" type="number" value={form.fee} onChange={(e) => setForm({ ...form, fee: Number(e.target.value) })} /></label>
        </div>
        <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={create} disabled={!form.date}>Create schedule</button>
      </div>
      {loading ? <Loading /> : (
        <div className="glass card">
          <h3 style={{ marginTop: 0 }}>Published schedules</h3>
          {rows.length === 0 && <div className="muted small">No schedules yet.</div>}
          {rows.map((s) => (
            <div key={s.id} className="list-row">
              <div><div className="name">{dateStr(s.date)}</div><div className="tiny muted">{s.session_start || ""}{s.session_end ? `–${s.session_end}` : ""} · {s.booked}/{s.total_serials} booked</div></div>
              <div className="row" style={{ gap: 6 }}>
                {s.fee != null && <span className="badge">{bdt(s.fee)}</span>}
                <span className="badge badge-accent">{s.available} free</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
