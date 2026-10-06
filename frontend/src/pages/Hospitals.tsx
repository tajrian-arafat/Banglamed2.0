import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../core/api";
import { Loading, Empty, ErrorState } from "../design-system/UI";
import { IconHospital, IconSearch } from "../design-system/Icons";

interface H { id: number; name: string; district: string | null; address: string | null; phone: string | null; hours: string | null; }

export default function Hospitals() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<H[]>([]);
  const [total, setTotal] = useState(0);
  const [allTotal, setAllTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [reload, setReload] = useState(0);

  // Unfiltered directory size for the header.
  useEffect(() => {
    let alive = true;
    api.get<{ total: number }>("/api/directory/hospitals?limit=1")
      .then((r) => { if (alive) setAllTotal(r.total); })
      .catch(() => { if (alive) setAllTotal(null); });
    return () => { alive = false; };
  }, [reload]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr("");
    const t = setTimeout(() => {
      api.get<{ total: number; results: H[] }>(`/api/directory/hospitals?q=${encodeURIComponent(q)}&limit=48`)
        .then((r) => { if (alive) { setRows(r.results); setTotal(r.total); } })
        .catch((e) => { if (alive) { setRows([]); setTotal(0); setErr(e.message || "Could not load hospitals"); } })
        .finally(() => { if (alive) setLoading(false); });
    }, 200);
    return () => { alive = false; clearTimeout(t); };
  }, [q, reload]);

  const retry = useCallback(() => setReload((n) => n + 1), []);
  const filtering = q.trim().length > 0;

  return (
    <div className="container">
      <h1>Hospitals &amp; clinics</h1>
      <p className="muted">
        {allTotal != null ? `${allTotal.toLocaleString()} facilities in the directory.` : "Facilities in the directory."}
      </p>
      <div className="search-hero" style={{ maxWidth: 640, marginBottom: 20 }}>
        <span className="search-icon"><IconSearch size={20} /></span>
        <input className="search-input" placeholder="Search a hospital or clinic…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {loading ? <Loading /> : err ? (
        <ErrorState message={err} onRetry={retry} />
      ) : rows.length === 0 ? (
        <Empty
          icon={<IconHospital size={30} />}
          title={filtering ? "No facilities match your search" : "No facilities found"}
          hint={filtering ? "Try a different search term." : "The directory is empty."}
          action={filtering ? <button className="btn btn-sm" onClick={() => setQ("")}>Clear search</button> : undefined}
        />
      ) : (
        <>
          {filtering && <div className="muted small" style={{ marginBottom: 10 }}>{total.toLocaleString()} result{total === 1 ? "" : "s"}</div>}
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
        </>
      )}
    </div>
  );
}
