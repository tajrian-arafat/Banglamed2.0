import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../core/api";
import { Loading, Empty } from "../design-system/UI";
import { IconStethoscope, IconSearch } from "../design-system/Icons";

interface Doc { id: number; doctor_code: string; name: string; speciality: string | null; qualifications: string | null; district: string | null; city: string | null; }

export default function Doctors() {
  const [q, setQ] = useState("");
  const [spec, setSpec] = useState("");
  const [specs, setSpecs] = useState<{ id: number; name: string }[]>([]);
  const [rows, setRows] = useState<Doc[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.get<{ results: { id: number; name: string }[] }>("/api/directory/specialities").then((r) => setSpecs(r.results)).catch(() => {}); }, []);

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      api.get<{ total: number; results: Doc[] }>(`/api/directory/doctors?q=${encodeURIComponent(q)}&speciality=${encodeURIComponent(spec)}&limit=48`)
        .then((r) => { setRows(r.results); setTotal(r.total); }).finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(t);
  }, [q, spec]);

  return (
    <div className="container">
      <h1>Find a doctor</h1>
      <p className="muted">Browse {total.toLocaleString()} doctors by name and speciality.</p>
      <div className="row wrap" style={{ gap: 10, marginBottom: 20 }}>
        <div className="search-hero" style={{ flex: 1, minWidth: 260 }}>
          <span className="search-icon"><IconSearch size={20} /></span>
          <input className="search-input" placeholder="Search by doctor name…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className="input" style={{ maxWidth: 260 }} value={spec} onChange={(e) => setSpec(e.target.value)}>
          <option value="">All specialities</option>
          {specs.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
        </select>
      </div>
      {loading ? <Loading /> : rows.length === 0 ? (
        <Empty icon={<IconStethoscope size={30} />} title="No doctors found" hint="Try a different name or speciality." />
      ) : (
        <div className="grid grid-3">
          {rows.map((d) => (
            <Link key={d.id} to={`/doctors/${d.id}`} className="glass card med-card">
              <h3 style={{ margin: 0 }}>{d.name}</h3>
              <div className="muted small" style={{ marginTop: 6 }}>{d.speciality || "—"}</div>
              <div className="tiny muted" style={{ marginTop: 4 }}>{d.qualifications || ""}</div>
              <div className="tiny muted">{d.district || d.city || ""}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
