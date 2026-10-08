import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { Loading, useToast } from "../../design-system/UI";
import { IconPlus, IconTrash } from "../../design-system/Icons";

interface P { id: number; patient_code: string; full_name: string; relation: string | null; sex: string | null; dob: string | null; blood_group: string | null; is_pregnant: boolean; is_lactating: boolean; }
interface Detail extends P { allergies: { id: number; substance: string; note: string | null }[]; }

export default function PatientProfile() {
  const [patients, setPatients] = useState<P[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ full_name: "", relation: "child", sex: "male", dob: "", blood_group: "" });
  const [allergy, setAllergy] = useState("");
  const { toast, toastNode } = useToast();

  function loadList() {
    api.get<{ results: P[] }>("/api/patients").then((r) => { setPatients(r.results); if (r.results[0] && !pid) setPid(r.results[0].id); });
  }
  useEffect(loadList, []);

  useEffect(() => {
    if (!pid) return;
    setLoading(true);
    api.get<Detail>(`/api/patients/${pid}`).then(setDetail).finally(() => setLoading(false));
  }, [pid]);

  async function addProfile() {
    if (!form.full_name.trim()) return;
    await api.post("/api/patients", form);
    setForm({ full_name: "", relation: "child", sex: "male", dob: "", blood_group: "" });
    toast("Profile added"); loadList();
  }

  async function addAllergy() {
    if (!pid || !allergy.trim()) return;
    await api.post(`/api/patients/${pid}/allergies`, { substance: allergy });
    setAllergy(""); toast("Allergy added");
    api.get<Detail>(`/api/patients/${pid}`).then(setDetail);
  }

  async function delAllergy(aid: number) {
    if (!pid) return;
    await api.del(`/api/patients/${pid}/allergies/${aid}`);
    api.get<Detail>(`/api/patients/${pid}`).then(setDetail);
  }

  return (
    <div className="container">
      {toastNode}
      <h1>Profiles & allergies</h1>
      <p className="muted">Manage family members and record allergies for safer prescribing.</p>
      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <div className="col" style={{ gap: 14 }}>
          <div className="glass card">
            <h3 style={{ marginTop: 0 }}>Family profiles</h3>
            {patients.map((p) => (
              <div key={p.id} className={`list-row ${pid === p.id ? "active" : ""}`} onClick={() => setPid(p.id)} style={{ cursor: "pointer" }}>
                <div><div className="name">{p.full_name}</div><div className="tiny muted">{p.patient_code} · {p.relation || "self"}</div></div>
                {pid === p.id && <span className="badge badge-accent">selected</span>}
              </div>
            ))}
          </div>
          <div className="glass card">
            <h3 style={{ marginTop: 0 }}><IconPlus size={18} /> Add a profile</h3>
            <div className="grid grid-2">
              <label className="field"><span>Full name</span><input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
              <label className="field"><span>Relation</span>
                <select className="input" value={form.relation} onChange={(e) => setForm({ ...form, relation: e.target.value })}>
                  <option value="self">Self</option><option value="spouse">Spouse</option><option value="child">Child</option>
                  <option value="parent">Parent</option><option value="other">Other</option>
                </select>
              </label>
              <label className="field"><span>Sex</span>
                <select className="input" value={form.sex} onChange={(e) => setForm({ ...form, sex: e.target.value })}>
                  <option value="male">Male</option><option value="female">Female</option><option value="other">Other</option>
                </select>
              </label>
              <label className="field"><span>Date of birth</span><input className="input" type="date" value={form.dob} onChange={(e) => setForm({ ...form, dob: e.target.value })} /></label>
              <label className="field"><span>Blood group</span><input className="input" value={form.blood_group} onChange={(e) => setForm({ ...form, blood_group: e.target.value })} placeholder="e.g. B+" /></label>
            </div>
            <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={addProfile}>Add profile</button>
          </div>
        </div>
        <div className="glass card">
          <h3 style={{ marginTop: 0 }}>Allergies</h3>
          {loading ? <Loading /> : detail ? (
            <>
              <div className="tiny muted" style={{ marginBottom: 10 }}>{detail.full_name} · {detail.patient_code}</div>
              {detail.allergies.length === 0 && <div className="muted small">No allergies recorded.</div>}
              {detail.allergies.map((a) => (
                <div key={a.id} className="list-row">
                  <div className="name">{a.substance}</div>
                  <button className="btn btn-sm btn-ghost" onClick={() => delAllergy(a.id)}><IconTrash size={15} /></button>
                </div>
              ))}
              <div className="row" style={{ gap: 8, marginTop: 12 }}>
                <input className="input" placeholder="e.g. Penicillin" value={allergy} onChange={(e) => setAllergy(e.target.value)} />
                <button className="btn btn-primary" onClick={addAllergy}>Add</button>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
