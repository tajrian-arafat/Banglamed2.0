import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { Loading, useToast } from "../../design-system/UI";

interface Prof { id: number; doctor_code: string; name: string; speciality: string | null; qualifications: string | null; bmdc_no: string | null; designation: string | null; district: string | null; signature_image: string | null; }

export default function DoctorProfile() {
  const [p, setP] = useState<Prof | null>(null);
  const [loading, setLoading] = useState(true);
  const { toast, toastNode } = useToast();

  useEffect(() => { api.get<Prof>("/api/doctor/profile").then(setP).finally(() => setLoading(false)); }, []);

  async function save() {
    if (!p) return;
    await api.put("/api/doctor/profile", { name: p.name, qualifications: p.qualifications, bmdc_no: p.bmdc_no, designation: p.designation, signature_image: p.signature_image });
    toast("Profile saved");
  }

  if (loading) return <div className="container"><Loading /></div>;
  if (!p) return <div className="container"><div className="glass card muted">No doctor profile linked to this account.</div></div>;

  return (
    <div className="container narrow">
      {toastNode}
      <h1>Profile & signature</h1>
      <p className="muted">These details appear on every prescription you issue.</p>
      <div className="glass card">
        <div className="grid grid-2">
          <label className="field"><span>Name</span><input className="input" value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} /></label>
          <label className="field"><span>BMDC number</span><input className="input" value={p.bmdc_no || ""} onChange={(e) => setP({ ...p, bmdc_no: e.target.value })} /></label>
          <label className="field"><span>Designation</span><input className="input" value={p.designation || ""} onChange={(e) => setP({ ...p, designation: e.target.value })} /></label>
          <label className="field"><span>Speciality</span><input className="input" value={p.speciality || ""} disabled /></label>
        </div>
        <label className="field" style={{ marginTop: 10 }}><span>Qualifications</span>
          <textarea className="input" rows={2} value={p.qualifications || ""} onChange={(e) => setP({ ...p, qualifications: e.target.value })} />
        </label>
        <label className="field" style={{ marginTop: 10 }}><span>Signature image URL (optional)</span>
          <input className="input" value={p.signature_image || ""} onChange={(e) => setP({ ...p, signature_image: e.target.value })} />
        </label>
        <button className="btn btn-primary" style={{ marginTop: 14 }} onClick={save}>Save profile</button>
      </div>
    </div>
  );
}
