import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { Loading, Empty, useToast } from "../../design-system/UI";
import { IconBell, IconPlus, IconTrash } from "../../design-system/Icons";

interface P { id: number; full_name: string; }
interface Item { id: number; medicine_name: string; times: string[]; start_date: string | null; end_date: string | null; }
interface R { id: number; title: string; source: string; is_active: boolean; items: Item[]; }

export default function PatientReminders() {
  const [patients, setPatients] = useState<P[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [rows, setRows] = useState<R[]>([]);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [med, setMed] = useState("");
  const [times, setTimes] = useState("08:00, 20:00");
  const { toast, toastNode } = useToast();

  useEffect(() => { api.get<{ results: P[] }>("/api/patients").then((r) => { setPatients(r.results); if (r.results[0]) setPid(r.results[0].id); }); }, []);

  function load() {
    if (!pid) return;
    setLoading(true);
    api.get<{ results: R[] }>(`/api/reminders?patient_id=${pid}`).then((r) => setRows(r.results)).finally(() => setLoading(false));
  }
  useEffect(load, [pid]);

  async function create() {
    if (!pid || !med.trim()) return;
    await api.post("/api/reminders", {
      patient_id: pid, title: title || "Medicine reminder",
      items: [{ medicine_name: med, times: times.split(",").map((s) => s.trim()).filter(Boolean) }],
    });
    setTitle(""); setMed(""); toast("Reminder created"); load();
  }

  async function remove(id: number) {
    await api.del(`/api/reminders/${id}`);
    toast("Reminder removed"); load();
  }

  return (
    <div className="container">
      {toastNode}
      <h1>Reminders</h1>
      <p className="muted">Turn your medicines into a daily schedule.</p>
      {patients.length > 1 && (
        <select className="input" style={{ maxWidth: 320, marginBottom: 16 }} value={pid ?? ""} onChange={(e) => setPid(Number(e.target.value))}>
          {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
        </select>
      )}
      <div className="glass card" style={{ marginBottom: 18 }}>
        <h3 style={{ marginTop: 0 }}><IconPlus size={18} /> New reminder</h3>
        <div className="grid grid-3">
          <label className="field"><span>Title</span><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Morning medicines" /></label>
          <label className="field"><span>Medicine</span><input className="input" value={med} onChange={(e) => setMed(e.target.value)} placeholder="e.g. Celofen" /></label>
          <label className="field"><span>Times (comma separated)</span><input className="input" value={times} onChange={(e) => setTimes(e.target.value)} /></label>
        </div>
        <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={create} disabled={!med.trim()}>Add reminder</button>
      </div>
      {loading ? <Loading /> : rows.length === 0 ? (
        <Empty icon={<IconBell size={30} />} title="No reminders yet" hint="Add one above to get started." />
      ) : (
        <div className="grid grid-2">
          {rows.map((r) => (
            <div key={r.id} className="glass card">
              <div className="row-between">
                <h3 style={{ margin: 0 }}>{r.title}</h3>
                <button className="btn btn-sm btn-ghost" onClick={() => remove(r.id)}><IconTrash size={15} /></button>
              </div>
              {r.items.map((it) => (
                <div key={it.id} className="list-row">
                  <div className="name">{it.medicine_name}</div>
                  <div className="row" style={{ gap: 6 }}>{it.times.map((t) => <span key={t} className="badge">{t}</span>)}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
