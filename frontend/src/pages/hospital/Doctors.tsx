import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../core/api";
import { Loading, Empty } from "../../design-system/UI";
import { IconStethoscope, IconSearch } from "../../design-system/Icons";

interface Doc { id: number; name: string; speciality: string | null; district: string | null; }

export default function HospitalDoctors() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      api.get<{ results: Doc[] }>(`/api/directory/doctors?q=${encodeURIComponent(q)}&limit=60`).then((r) => setRows(r.results)).finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div className="container">
      <h1>Doctors</h1>
      <p className="muted">Directory of doctors available to your facility.</p>
      <div className="search-hero" style={{ maxWidth: 640, marginBottom: 20 }}>
        <span className="search-icon"><IconSearch size={20} /></span>
        <input className="search-input" placeholder="Search doctors…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {loading ? <Loading /> : rows.length === 0 ? <Empty icon={<IconStethoscope size={30} />} title="No doctors found" /> : (
        <div className="grid grid-3">
          {rows.map((d) => (
            <Link key={d.id} to={`/doctors/${d.id}`} className="glass card med-card">
              <h3 style={{ margin: 0 }}>{d.name}</h3>
              <div className="muted small" style={{ marginTop: 6 }}>{d.speciality || "—"}</div>
              <div className="tiny muted">{d.district || ""}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
