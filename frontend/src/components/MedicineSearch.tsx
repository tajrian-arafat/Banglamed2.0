import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { IconSearch } from "../design-system/Icons";

interface Hit { brand_id: number; brand: string; generic: string; company: string; strength: string; form: string; unit_price?: number | null; }

// Typeahead timings. The brief used to be 220 ms AND a 2-character minimum, so
// the first keystroke produced nothing at all and each subsequent key waited on
// a debounce — which reads as "suggestions only appear after a pause".
//
// Now: suggestions fire from the FIRST character, and the debounce is short
// enough to still coalesce a burst of typing into one request. The server side
// is a prefix-only, index-only query (see /api/medicines/suggest), so a request
// per keystroke is cheap.
const MIN_CHARS = 1;
const DEBOUNCE_MS = 90;

export function MedicineSearch({
  placeholder, autoFocus, onPick, onQuery, initial = "",
}: {
  placeholder?: string;
  autoFocus?: boolean;
  onPick?: (id: number) => void;
  onQuery?: (q: string) => void;
  initial?: string;
}) {
  const [q, setQ] = useState(initial);
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const box = useRef<HTMLDivElement>(null);
  // Monotonic request id: a response is only applied when it belongs to the
  // newest query, so a slow early response can never overwrite a later one.
  const reqId = useRef(0);
  const nav = useNavigate();

  useEffect(() => {
    const query = q.trim();
    if (query.length < MIN_CHARS) {
      setHits([]); setErr(""); setLoading(false); onQuery?.("");
      reqId.current++; // invalidate anything in flight
      return;
    }
    setLoading(true);
    setErr("");
    const myReq = ++reqId.current;
    const t = setTimeout(async () => {
      if (myReq !== reqId.current) return;
      onQuery?.(query);
      try {
        const r = await api.get<{ results: Hit[] }>(`/api/medicines/suggest?q=${encodeURIComponent(query)}&limit=8`);
        if (myReq !== reqId.current) return;
        setHits(r.results);
        setOpen(true);
      } catch (e) {
        if (myReq !== reqId.current) return;
        setHits([]);
        setErr(e instanceof Error ? e.message : "Search failed");
        setOpen(true);
      } finally {
        if (myReq === reqId.current) setLoading(false);
      }
    }, DEBOUNCE_MS);
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

  const ready = q.trim().length >= MIN_CHARS;
  const showPanel = open && ready && (loading || err !== "" || hits.length > 0);
  const nothingFound = !loading && err === "" && hits.length === 0 && ready;

  return (
    <div className="search-hero" ref={box}>
      <span className="search-icon"><IconSearch size={20} /></span>
      <input
        className="search-input"
        placeholder={placeholder || "Search a medicine, generic or company…"}
        value={q}
        autoFocus={autoFocus}
        aria-label="Search medicines"
        aria-expanded={showPanel}
        role="combobox"
        aria-autocomplete="list"
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => (hits.length || err) && setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
          if (e.key === "Enter" && ready) { setOpen(false); nav(`/medicines/q/${encodeURIComponent(q.trim())}`); }
        }}
      />
      {showPanel && (
        <div className="glass search-results" role="listbox">
          {loading && <div className="search-item muted small">Searching…</div>}
          {!loading && err !== "" && <div className="search-item muted small">Search unavailable — {err}</div>}
          {!loading && err === "" && nothingFound && <div className="search-item muted small">No medicine matches “{q.trim()}”.</div>}
          {hits.map((h) => (
            <div key={h.brand_id} className="search-item" role="option" tabIndex={0}
                 aria-selected={false}
                 onClick={() => pick(h)}
                 onKeyDown={(e) => { if (e.key === "Enter") pick(h); }}>
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
