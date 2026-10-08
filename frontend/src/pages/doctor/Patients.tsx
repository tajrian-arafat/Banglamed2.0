import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../core/api";
import { dateStr } from "../../core/format";
import { Loading, Empty, Modal } from "../../design-system/UI";
import { IconUser, IconSearch } from "../../design-system/Icons";

interface P { id: number; patient_code: string; full_name: string; sex: string | null; dob: string | null; seen_by_me: boolean; }
interface Hist { patient: { full_name: string; patient_code: string }; prescriptions: { id: number; rx_code: string; date: string; diagnosis: string | null; status: string; by_me: boolean }[]; }

export default function DoctorPatients() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<P[]>([]);
  const [loading, setLoading] = useState(true);
  const [hist, setHist] = useState<Hist | null>(null);

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      api.get<{ results: P[] }>(`/api/doctor/patients?q=${encodeURIComponent(q)}&limit=60`)
        .then((r) => setRows(r.results)).finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  async function open(p: P) {
    const h = await api.get<Hist>(`/api/doctor/patients/${p.id}/history`);
    setHist(h);
  }

  return (
    <div className="container">
      <h1>My patients</h1>
      <p className="muted">Search the patient directory and review prescription history.</p>
      <div className="search-hero" style={{ maxWidth: 640, marginBottom: 20 }}>
        <span className="search-icon"><IconSearch size={20} /></span>
        <input className="search-input" placeholder="Search by patient name…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {loading ? <Loading /> : rows.length === 0 ? (
        <Empty icon={<IconUser size={30} />} title="No patients found" hint="Try a different name." />
      ) : (
        <div className="grid grid-3">
          {rows.map((p) => (
            <div key={p.id} className="glass card med-card" onClick={() => open(p)} style={{ cursor: "pointer" }}>
              <div className="row-between">
                <h3 style={{ margin: 0 }}>{p.full_name}</h3>
                {p.seen_by_me && <span className="badge badge-accent">seen</span>}
              </div>
              <div className="tiny muted" style={{ marginTop: 6 }}>{p.patient_code} · {p.sex || "—"}</div>
            </div>
          ))}
        </div>
      )}
      {hist && (
        <Modal title={`${hist.patient.full_name} — history`} onClose={() => setHist(null)}>
          {hist.prescriptions.length === 0 && <div className="muted small">No prescriptions recorded.</div>}
          {hist.prescriptions.map((rx) => (
            <div key={rx.id} className="list-row">
              <div><div className="name">{rx.rx_code}</div><div className="tiny muted">{dateStr(rx.date)} · {rx.diagnosis || "—"}</div></div>
              <div className="row" style={{ gap: 6 }}>
                <span className="badge">{rx.status}</span>
                {rx.by_me && <span className="badge badge-accent">by you</span>}
                <Link to={`/doctor/prescribe?patient=${hist.patient && rx.id}`} className="btn btn-sm btn-ghost">Copy</Link>
              </div>
            </div>
          ))}
        </Modal>
      )}
    </div>
  );
}
