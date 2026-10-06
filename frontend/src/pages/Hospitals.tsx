import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../core/api";
import { Loading, Empty } from "../design-system/UI";
import { IconHospital, IconSearch } from "../design-system/Icons";

interface H { id: number; name: string; district: string | null; address: string | null; phone: string | null; hours: string | null; }

export default function Hospitals() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<H[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      api.get<{ total: number; results: H[] }>(`/api/directory/hospitals?q=${encodeURIComponent(q)}&limit=48`)
        .then((r) => { setRows(r.results); setTotal(r.total); }).finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="container">
      <h1>Hospitals & clinics</h1>
      <p className="muted">{total.toLocaleString()} facilities in the directory.</p>
      <div className="search-hero" style={{ maxWidth: 640, marginBottom: 20 }}>
        <span className="search-icon"><IconSearch size={20} /></span>
        <input className="search-input" placeholder="Search a hospital or clinic…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {loading ? <Loading /> : rows.length === 0 ? (
        <Empty icon={<IconHospital size={30} />} title="No facilities found" hint="Try a different search term." />
      ) : (
        <div className="grid grid-3">
          {rows.map((h) => (
            <Link key={h.id} to={`/hospitals/${h.id}`} className="glass card med-card">
              <h3 style={{ margin: 0 }}>{h.name}</h3>
              <div className="muted small" style={{ marginTop: 6 }}>{h.district || "—"}</div>
              <div className="tiny muted" style={{ marginTop: 4 }}>{h.address || ""}</div>
              {h.phone && <div className="tiny muted">{h.phone}</div>}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
