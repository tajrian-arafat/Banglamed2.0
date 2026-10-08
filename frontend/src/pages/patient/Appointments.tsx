import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { bdt, dateStr } from "../../core/format";
import { Loading, Empty, useToast } from "../../design-system/UI";
import { IconCalendar } from "../../design-system/Icons";

interface P { id: number; full_name: string; }
interface Apt { id: number; apt_code: string; serial_no: number; status: string; date: string | null; doctor_name: string | null; session_start: string | null; fee: number | null; }
interface Sched { id: number; doctor_id: number; doctor_name: string | null; date: string; total_serials: number; booked: number; available: number; session_start: string | null; fee: number | null; }

export default function PatientAppointments() {
  const [patients, setPatients] = useState<P[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [mine, setMine] = useState<Apt[]>([]);
  const [scheds, setScheds] = useState<Sched[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast, toastNode } = useToast();

  function load() {
    setLoading(true);
    Promise.all([
      api.get<{ results: Apt[] }>("/api/appointments/mine"),
      api.get<{ results: Sched[] }>("/api/appointments/schedules"),
    ]).then(([a, s]) => { setMine(a.results); setScheds(s.results); }).finally(() => setLoading(false));
  }

  useEffect(() => {
    api.get<{ results: P[] }>("/api/patients").then((r) => { setPatients(r.results); if (r.results[0]) setPid(r.results[0].id); });
    load();
  }, []);

  async function book(s: Sched) {
    if (!pid) return;
    try {
      const r = await api.post<{ serial_no: number }>("/api/appointments/book", { schedule_id: s.id, patient_id: pid });
      toast(`Booked — serial #${r.serial_no}`); load();
    } catch (e: any) { toast(e.message); }
  }

  async function cancel(id: number) {
    await api.post(`/api/appointments/${id}/cancel`); toast("Cancelled"); load();
  }

  return (
    <div className="container">
      {toastNode}
      <h1>Appointments</h1>
      <p className="muted">Book a serial and track your visits.</p>
      {patients.length > 1 && (
        <select className="input" style={{ maxWidth: 320, marginBottom: 16 }} value={pid ?? ""} onChange={(e) => setPid(Number(e.target.value))}>
          {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
        </select>
      )}
      {loading ? <Loading /> : (
        <>
          <div className="glass card" style={{ marginBottom: 18 }}>
            <h3 style={{ marginTop: 0 }}>My appointments</h3>
            {mine.length === 0 ? <div className="muted small">No appointments booked.</div> : mine.map((a) => (
              <div key={a.id} className="list-row">
                <div>
                  <div className="name">{a.doctor_name || "Doctor"} <span className="tiny muted">#{a.serial_no}</span></div>
                  <div className="tiny muted">{a.date ? dateStr(a.date) : ""} {a.session_start || ""} · {a.apt_code}</div>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  <span className="badge badge-accent">{a.status}</span>
                  {a.status !== "cancelled" && <button className="btn btn-sm btn-ghost" onClick={() => cancel(a.id)}>Cancel</button>}
                </div>
              </div>
            ))}
          </div>
          <div className="glass card">
            <h3 style={{ marginTop: 0 }}><IconCalendar size={18} /> Available schedules</h3>
            {scheds.length === 0 ? <Empty title="No schedules open" hint="Check back later for new doctor schedules." /> : scheds.map((s) => (
              <div key={s.id} className="list-row">
                <div>
                  <div className="name">{s.doctor_name || "Doctor"}</div>
                  <div className="tiny muted">{dateStr(s.date)} {s.session_start || ""} · {s.available}/{s.total_serials} free</div>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  {s.fee != null && <span className="badge">{bdt(s.fee)}</span>}
                  <button className="btn btn-sm btn-primary" disabled={s.available <= 0} onClick={() => book(s)}>Book</button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
