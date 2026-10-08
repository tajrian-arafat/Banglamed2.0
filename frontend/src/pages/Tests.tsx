import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { Loading, Empty, ErrorState } from "../design-system/UI";
import { IconFlask, IconSearch } from "../design-system/Icons";

interface T { id: number; name: string; slug: string; price_min: number | null; price_max: number | null; }

// The catalogue holds 108 tests; a fixed 40-row fetch left 68 of them
// unreachable in the UI.
const TARGET = 48;

export default function Tests() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(TARGET);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [err, setErr] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    setErr("");
    if (rows.length === 0) setLoading(true);
    const t = setTimeout(() => {
      api.get<{ total: number; results: T[] }>(`/api/tests/search?q=${encodeURIComponent(q)}&limit=${limit}`)
        .then((r) => { if (alive) { setRows(r.results); setTotal(r.total); } })
        .catch((e) => { if (alive) { setRows([]); setTotal(0); setErr(e.message || "Could not load tests"); } })
        .finally(() => { if (alive) { setLoading(false); setMore(false); } });
    }, 200);
    return () => { alive = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, limit, reload]);

  const retry = useCallback(() => setReload((n) => n + 1), []);
  const filtering = q.trim().length > 0;

  return (
    <div className="container">
      <h1>Tests &amp; prices</h1>
      <p className="muted">Compare diagnostic test prices across hospitals.</p>
      <div className="search-hero" style={{ maxWidth: 640, marginBottom: 20 }}>
        <span className="search-icon"><IconSearch size={20} /></span>
        <input className="search-input" placeholder="Search a test (e.g. blood, glucose)…" value={q} onChange={(e) => { setQ(e.target.value); setLimit(TARGET); }} />
      </div>

      {loading ? <Loading /> : err ? (
        <ErrorState message={err} onRetry={retry} />
      ) : rows.length === 0 ? (
        <Empty
          icon={<IconFlask size={30} />}
          title={filtering ? "No tests match your search" : "No tests found"}
          hint={filtering ? "Try a different search term." : "The test catalogue is empty."}
          action={filtering ? <button className="btn btn-sm" onClick={() => { setQ(""); setLimit(TARGET); }}>Clear search</button> : undefined}
        />
      ) : (
        <>
          <div className="muted small" style={{ marginBottom: 10 }}>
            Showing {rows.length.toLocaleString()} of {total.toLocaleString()} test{total === 1 ? "" : "s"}
          </div>
          <div className="grid grid-3">
            {rows.map((t) => (
              <Link key={t.id} to={`/tests/${t.id}`} className="glass card med-card">
                <h3 style={{ margin: 0 }}>{t.name}</h3>
                <div className="muted small" style={{ marginTop: 8 }}>
                  {t.price_min != null ? `${bdt(t.price_min)}${t.price_max && t.price_max !== t.price_min ? ` – ${bdt(t.price_max)}` : ""}` : "Price on request"}
                </div>
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
