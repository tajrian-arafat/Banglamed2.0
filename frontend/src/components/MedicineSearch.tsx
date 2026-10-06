import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { IconSearch } from "../design-system/Icons";

interface Hit { brand_id: number; brand: string; generic: string; company: string; strength: string; form: string; unit_price?: number | null; }

export function MedicineSearch({ placeholder, autoFocus, onPick }: { placeholder?: string; autoFocus?: boolean; onPick?: (id: number) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const nav = useNavigate();

  useEffect(() => {
    if (q.trim().length < 2) { setHits([]); return; }
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const r = await api.get<{ results: Hit[] }>(`/api/medicines/search?q=${encodeURIComponent(q)}&limit=8`);
        setHits(r.results);
        setOpen(true);
      } catch { setHits([]); }
      finally { setLoading(false); }
    }, 220);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    function onDoc(e: MouseEvent) { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function pick(h: Hit) {
    setOpen(false);
    if (onPick) onPick(h.brand_id);
    else nav(`/medicines/${h.brand_id}`);
  }

  return (
    <div className="search-hero" ref={box}>
      <span className="search-icon"><IconSearch size={20} /></span>
      <input
        className="search-input"
        placeholder={placeholder || "Search a medicine, generic or company…"}
        value={q}
        autoFocus={autoFocus}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => hits.length && setOpen(true)}
      />
      {open && (hits.length > 0 || loading) && (
        <div className="glass search-results">
          {loading && <div className="search-item muted small">Searching…</div>}
          {hits.map((h) => (
            <div key={h.brand_id} className="search-item" onClick={() => pick(h)}>
              <div className="row-between">
                <div>
                  <div className="name">{h.brand} {h.strength ? <span className="muted small">{h.strength}</span> : null}</div>
                  <div className="meta">{h.generic || "—"} · {h.company || "—"} {h.form ? `· ${h.form}` : ""}</div>
                </div>
                {h.unit_price != null && <span className="badge badge-accent">{bdt(h.unit_price)}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
