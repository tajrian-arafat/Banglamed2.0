import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { Loading, Empty } from "../design-system/UI";
import { IconFlask, IconSearch } from "../design-system/Icons";

interface T { id: number; name: string; slug: string; price_min: number | null; price_max: number | null; }

export default function Tests() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      api.get<{ results: T[] }>(`/api/tests/search?q=${encodeURIComponent(q)}&limit=40`)
        .then((r) => setRows(r.results)).finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="container">
      <h1>Tests & prices</h1>
      <p className="muted">Compare diagnostic test prices across hospitals.</p>
      <div className="search-hero" style={{ maxWidth: 640, marginBottom: 20 }}>
        <span className="search-icon"><IconSearch size={20} /></span>
        <input className="search-input" placeholder="Search a test (e.g. blood, glucose)…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {loading ? <Loading /> : rows.length === 0 ? (
        <Empty icon={<IconFlask size={30} />} title="No tests found" hint="Try a different search term." />
      ) : (
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
      )}
    </div>
  );
}
