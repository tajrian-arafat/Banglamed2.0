import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { MedicineSearch } from "../components/MedicineSearch";
import { Loading, Empty, ErrorState } from "../design-system/UI";
import { IconPill } from "../design-system/Icons";

interface Hit { brand_id: number; brand: string; generic: string; company: string; strength: string; form: string; unit_price?: number | null; strip_price?: number | null; pack_size?: string | null; }

export default function Medicines() {
  const { q: qParam } = useParams();
  const [params, setParams] = useSearchParams();
  // The live query is local state (typing must never touch the router); the
  // URL is only used to seed a deep link such as /medicines/q/napa.
  const [q, setQ] = useState((params.get("q") || qParam || "").trim());
  const [rows, setRows] = useState<Hit[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [reload, setReload] = useState(0);

  // Results grid: driven by the current query (typing in the box mirrors it here).
  useEffect(() => {
    if (!q) { setRows([]); setErr(""); setLoading(false); return; }
    let alive = true;
    setLoading(true); setErr("");
    api.get<{ results: Hit[] }>(`/api/medicines/search?q=${encodeURIComponent(q)}&limit=40`)
      .then((r) => { if (alive) setRows(r.results); })
      .catch((e) => { if (alive) { setRows([]); setErr(e.message || "Search failed"); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [q, reload]);

  const retry = useCallback(() => setReload((n) => n + 1), []);

  return (
    <div className="container">
      <h1>Medicines</h1>
      <p className="muted">Search the full Bangladesh brand catalog by brand, generic or company.</p>
      <div style={{ maxWidth: 720, marginBottom: 20 }}>
        {/* One box: live matching suggestions; picking one opens its detail page.
            No onPick here, so MedicineSearch performs its default navigation to
            /medicines/<brand id>; onQuery only mirrors the text into the grid. */}
        <MedicineSearch autoFocus initial={q} onQuery={setQ} />
      </div>

      {loading && <Loading />}
      {err && !loading && <ErrorState message={err} onRetry={retry} />}
      {!loading && !err && q && rows.length === 0 && (
        <Empty icon={<IconPill size={30} />} title="No matches" hint={`Nothing found for “${q}”. Try a different spelling or the generic name.`} />
      )}
      {!loading && !err && rows.length > 0 && (
        <>
          <div className="muted small" style={{ marginBottom: 10 }}>{rows.length} results for “{q}”</div>
          <div className="grid grid-3">
            {rows.map((r) => (
              <Link key={r.brand_id} to={`/medicines/${r.brand_id}`} className="glass card med-card">
                <div className="row-between">
                  <h3 style={{ margin: 0 }}>{r.brand}</h3>
                  {r.unit_price != null && <span className="badge badge-accent">{bdt(r.unit_price)}</span>}
                </div>
                <div className="muted small" style={{ marginTop: 6 }}>{r.strength || "—"} · {r.form || "—"}</div>
                <div className="tiny muted" style={{ marginTop: 4 }}>{r.generic || "—"}</div>
                <div className="tiny muted">{r.company || "—"}</div>
              </Link>
            ))}
          </div>
        </>
      )}
      {!q && (
        <div className="glass card" style={{ textAlign: "center" }}>
          <p className="muted">Start typing to search 25,000+ medicines.</p>
        </div>
      )}
    </div>
  );
}
