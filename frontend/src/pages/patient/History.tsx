import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { dateStr } from "../../core/format";
import { Loading, Empty } from "../../design-system/UI";
import { IconFile } from "../../design-system/Icons";

interface P { id: number; full_name: string; patient_code: string; }
interface Ev { type: string; id: number; date: string; title: string; status?: string; diagnosis?: string | null; serial_no?: number; date_of_visit?: string | null; }

export default function PatientHistory() {
  const [patients, setPatients] = useState<P[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<{ results: P[] }>("/api/patients").then((r) => {
      setPatients(r.results);
      if (r.results[0]) setPid(r.results[0].id);
    });
  }, []);

  useEffect(() => {
    if (!pid) return;
    setLoading(true);
    api.get<{ events: Ev[] }>(`/api/records/${pid}/timeline`).then((r) => setEvents(r.events)).finally(() => setLoading(false));
  }, [pid]);

  return (
    <div className="container">
      <h1>My records</h1>
      <p className="muted">A timeline of prescriptions, appointments and tests.</p>
      {patients.length > 1 && (
        <select className="input" style={{ maxWidth: 320, marginBottom: 16 }} value={pid ?? ""} onChange={(e) => setPid(Number(e.target.value))}>
          {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.patient_code})</option>)}
        </select>
      )}
      {loading ? <Loading /> : events.length === 0 ? (
        <Empty icon={<IconFile size={30} />} title="No records yet" hint="Prescriptions issued to you will appear here." />
      ) : (
        <div className="timeline">
          {events.map((e, i) => (
            <div key={i} className="glass card timeline-item">
              <div className="row-between">
                <div>
                  <div className="name">{e.title}</div>
                  <div className="tiny muted">{dateStr(e.date)}{e.date_of_visit ? ` · visit ${e.date_of_visit}` : ""}</div>
                  {e.diagnosis && <div className="tiny muted">Dx: {e.diagnosis}</div>}
                </div>
                <div className="col" style={{ alignItems: "flex-end", gap: 4 }}>
                  <span className="badge">{e.type}</span>
                  {e.status && <span className="badge badge-accent">{e.status}</span>}
                  {e.serial_no != null && <span className="tiny muted">serial #{e.serial_no}</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
