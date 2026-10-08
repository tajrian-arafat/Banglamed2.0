import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../core/api";
import { useAuth } from "../../core/auth";
import { dateStr } from "../../core/format";
import { Loading, Stat, Empty } from "../../design-system/UI";
import { IconFile, IconBell, IconCalendar, IconUpload, IconUser } from "../../design-system/Icons";

interface P { id: number; patient_code: string; full_name: string; relation: string | null; sex: string | null; dob: string | null; blood_group: string | null; }
interface Ev { type: string; id: number; date: string; title: string; status?: string; }

export default function PatientDashboard() {
  const { me } = useAuth();
  const [patients, setPatients] = useState<P[]>([]);
  const [events, setEvents] = useState<Ev[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<{ results: P[] }>("/api/patients").then(async (r) => {
      setPatients(r.results);
      if (r.results[0]) {
        const tl = await api.get<{ events: Ev[] }>(`/api/records/${r.results[0].id}/timeline`).catch(() => ({ events: [] }));
        setEvents(tl.events.slice(0, 6));
      }
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="container"><Loading /></div>;

  return (
    <div className="container">
      <h1>Welcome, {me?.full_name}</h1>
      <p className="muted">Your health records, prescriptions and reminders.</p>

      <div className="grid grid-4" style={{ marginTop: 18 }}>
        <Stat label="Profiles" value={patients.length} sub="family members" />
        <Stat label="Recent events" value={events.length} sub="last activity" />
        <Stat label="Account" value={me?.account_type || "—"} sub="type" />
        <Stat label="Role" value="Patient" sub="access level" />
      </div>

      <div className="grid grid-4" style={{ marginTop: 18 }}>
        <Link to="/patient/history" className="glass card quick"><IconFile size={22} /><span>My records</span></Link>
        <Link to="/patient/upload" className="glass card quick"><IconUpload size={22} /><span>Upload prescription</span></Link>
        <Link to="/patient/reminders" className="glass card quick"><IconBell size={22} /><span>Reminders</span></Link>
        <Link to="/patient/appointments" className="glass card quick"><IconCalendar size={22} /><span>Appointments</span></Link>
      </div>

      <div className="grid grid-2" style={{ marginTop: 18, alignItems: "start" }}>
        <div className="glass card">
          <h3 style={{ marginTop: 0 }}><IconUser size={18} /> Profiles</h3>
          {patients.map((p) => (
            <div key={p.id} className="list-row">
              <div><div className="name">{p.full_name}</div><div className="tiny muted">{p.patient_code} · {p.relation || "self"}</div></div>
              <Link to="/patient/profile" className="btn btn-sm btn-ghost">Manage</Link>
            </div>
          ))}
        </div>
        <div className="glass card">
          <h3 style={{ marginTop: 0 }}>Recent activity</h3>
          {events.length === 0 ? <Empty title="No activity yet" hint="Your prescriptions and appointments will appear here." /> : events.map((e, i) => (
            <div key={i} className="list-row">
              <div><div className="name">{e.title}</div><div className="tiny muted">{dateStr(e.date)}</div></div>
              {e.status && <span className="badge">{e.status}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
