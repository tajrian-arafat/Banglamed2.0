import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../core/api";
import { useAuth } from "../../core/auth";
import { Loading, Stat } from "../../design-system/UI";
import { IconFile, IconUser, IconCalendar, IconShield } from "../../design-system/Icons";

interface Prof { id: number; name: string; speciality: string | null; bmdc_no: string | null; doctor_code: string; }
interface P { id: number; full_name: string; seen_by_me: boolean; }

export default function DoctorDashboard() {
  const { me } = useAuth();
  const [prof, setProf] = useState<Prof | null>(null);
  const [patients, setPatients] = useState<P[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<Prof>("/api/doctor/profile").catch(() => null),
      api.get<{ results: P[] }>("/api/doctor/patients?limit=100").catch(() => ({ results: [] })),
    ]).then(([p, pts]) => { setProf(p); setPatients(pts.results); }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="container"><Loading /></div>;
  const seen = patients.filter((p) => p.seen_by_me).length;

  return (
    <div className="container">
      <h1>{(() => { const n = prof?.name || me?.full_name || ""; return /^dr\.?\s/i.test(n) ? n : `Dr. ${n}`; })()}</h1>
      <p className="muted">{prof?.speciality || "—"}{prof?.bmdc_no ? ` · BMDC ${prof.bmdc_no}` : ""}</p>
      <div className="grid grid-4" style={{ marginTop: 18 }}>
        <Stat label="Patients seen" value={seen} sub="by you" />
        <Stat label="Directory" value={patients.length} sub="searchable" />
        <Stat label="Doctor code" value={prof?.doctor_code || "—"} />
        <Stat label="Status" value="Active" sub="verified" />
      </div>
      <div className="grid grid-4" style={{ marginTop: 18 }}>
        <Link to="/doctor/prescribe" className="glass card quick"><IconFile size={22} /><span>Write prescription</span></Link>
        <Link to="/doctor/patients" className="glass card quick"><IconUser size={22} /><span>My patients</span></Link>
        <Link to="/doctor/schedule" className="glass card quick"><IconCalendar size={22} /><span>Schedules</span></Link>
        <Link to="/doctor/profile" className="glass card quick"><IconShield size={22} /><span>Profile & signature</span></Link>
      </div>
      <div className="glass card" style={{ marginTop: 18 }}>
        <h3 style={{ marginTop: 0 }}>Recently seen</h3>
        {patients.filter((p) => p.seen_by_me).slice(0, 8).map((p) => (
          <div key={p.id} className="list-row"><div className="name">{p.full_name}</div><span className="badge">seen</span></div>
        ))}
        {seen === 0 && <div className="muted small">No patients seen yet.</div>}
      </div>
    </div>
  );
}
