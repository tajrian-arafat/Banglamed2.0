import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../core/api";
import { Loading, Empty, ErrorState } from "../design-system/UI";
import { IconStethoscope, IconSearch, IconMapPin } from "../design-system/Icons";

interface Doc { id: number; doctor_code: string; name: string; speciality: string | null; qualifications: string | null; designation: string | null; district: string | null; city: string | null; }

// Page size. The previous fixed limit of 48 meant the other 2,036 of 2,084
// doctors existed in the DB but could not be reached from the UI at all.
const TARGET = 48;

export default function Doctors() {
  const [q, setQ] = useState("");
  const [spec, setSpec] = useState("");
  const [specs, setSpecs] = useState<{ id: number; name: string }[]>([]);
  const [rows, setRows] = useState<Doc[]>([]);
  const [total, setTotal] = useState(0);
  const [allTotal, setAllTotal] = useState<number | null>(null);
  const [limit, setLimit] = useState(TARGET);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [err, setErr] = useState("");
  const [reload, setReload] = useState(0);

  // All specialities (non-fatal: the dropdown simply stays empty if this fails).
  useEffect(() => {
    let alive = true;
    api.get<{ results: { id: number; name: string }[] }>("/api/directory/specialities")
      .then((r) => { if (alive) setSpecs(r.results); })
      .catch(() => { if (alive) setSpecs([]); });
    // Unfiltered directory size, so the header can show a true total.
    api.get<{ total: number }>("/api/directory/doctors?limit=1")
      .then((r) => { if (alive) setAllTotal(r.total); })
      .catch(() => { if (alive) setAllTotal(null); });
    return () => { alive = false; };
  }, [reload]);

  useEffect(() => {
    let alive = true;
    setErr("");
    if (rows.length === 0) setLoading(true);
    const t = setTimeout(() => {
      api.get<{ total: number; results: Doc[] }>(
        `/api/directory/doctors?q=${encodeURIComponent(q)}&speciality=${encodeURIComponent(spec)}&limit=${limit}`,
      )
        .then((r) => { if (alive) { setRows(r.results); setTotal(r.total); } })
        .catch((e) => { if (alive) { setRows([]); setTotal(0); setErr(e.message || "Could not load doctors"); } })
        .finally(() => { if (alive) { setLoading(false); setMore(false); } });
    }, 200);
    return () => { alive = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, spec, limit, reload]);

  const retry = useCallback(() => setReload((n) => n + 1), []);
  const filtering = q.trim().length > 0 || spec.length > 0;
  const clear = () => { setQ(""); setSpec(""); setLimit(TARGET); };

  return (
    <div className="container">
      <h1>Find a doctor</h1>
      <p className="muted">
        {allTotal != null ? `Browse ${allTotal.toLocaleString()} doctors by name and speciality.` : "Browse doctors by name and speciality."}
      </p>
      <div className="row wrap" style={{ gap: 10, marginBottom: 20 }}>
        <div className="search-hero" style={{ flex: 1, minWidth: 260 }}>
          <span className="search-icon"><IconSearch size={20} /></span>
          <input className="search-input" placeholder="Search by doctor name…" value={q} onChange={(e) => { setQ(e.target.value); setLimit(TARGET); }} />
        </div>
        <select className="input" style={{ maxWidth: 260 }} value={spec} onChange={(e) => { setSpec(e.target.value); setLimit(TARGET); }}>
          <option value="">All specialities</option>
          {specs.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
        </select>
      </div>

      {loading ? <Loading /> : err ? (
        <ErrorState message={err} onRetry={retry} />
      ) : rows.length === 0 ? (
        <Empty
          icon={<IconStethoscope size={30} />}
          title={filtering ? "No doctors match your search" : "No doctors found"}
          hint={filtering ? "Try a different name or clear the speciality filter." : "The directory is empty."}
          action={filtering ? <button className="btn btn-sm" onClick={clear}>Clear filters</button> : undefined}
        />
      ) : (
        <>
          <div className="muted small" style={{ marginBottom: 10 }}>
            Showing {rows.length.toLocaleString()} of {total.toLocaleString()} doctor{total === 1 ? "" : "s"}
          </div>
          <div className="grid grid-3">
            {rows.map((d) => (
              <Link key={d.id} to={`/doctors/${d.id}`} className="glass card med-card">
                <h3 style={{ margin: 0 }}>{d.name}</h3>
                <div className="muted small" style={{ marginTop: 6 }}>{d.speciality || "—"}</div>
                <div className="tiny muted" style={{ marginTop: 4 }}>{d.qualifications || ""}</div>
                {(d.district || d.city) && (
                  <div className="tiny muted row" style={{ gap: 4, alignItems: "center", marginTop: 4 }}>
                    <IconMapPin size={12} /><span>{d.district || d.city}</span>
                  </div>
                )}
              </Link>
            ))}
          </div>
          {rows.length < total && (
            <div style={{ textAlign: "center", marginTop: 22 }}>
              <button className="btn btn-primary" disabled={more} onClick={() => { setMore(true); setLimit((l) => l + TARGET); }}>
                {more ? "Loading…" : `Load more (${(total - rows.length).toLocaleString()} remaining)`}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
