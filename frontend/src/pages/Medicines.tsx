import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { MedicineSearch } from "../components/MedicineSearch";
import { Loading, Empty, ErrorState } from "../design-system/UI";
import { IconPill } from "../design-system/Icons";

interface Hit { brand_id: number; brand: string; generic: string; company: string; strength: string; form: string; unit_price?: number | null; strip_price?: number | null; pack_size?: string | null; }

export default function Medicines() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const [rows, setRows] = useState<Hit[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!q) { setRows([]); return; }
    setLoading(true); setErr("");
    api.get<{ results: Hit[] }>(`/api/medicines/search?q=${encodeURIComponent(q)}&limit=40`)
      .then((r) => setRows(r.results))
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [q]);

  return (
    <div className="container">
      <h1>Medicines</h1>
      <p className="muted">Search the full Bangladesh brand catalog by brand, generic or company.</p>
      <div style={{ maxWidth: 720, marginBottom: 20 }}>
        <MedicineSearch autoFocus onPick={(id) => setParams({ q })} />
      </div>
      {loading && <Loading />}
      {err && <ErrorState message={err} />}
      {!loading && !err && q && rows.length === 0 && (
        <Empty icon={<IconPill size={30} />} title="No matches" hint={`Nothing found for “${q}”. Try a different spelling or the generic name.`} />
      )}
      {!loading && rows.length > 0 && (
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
