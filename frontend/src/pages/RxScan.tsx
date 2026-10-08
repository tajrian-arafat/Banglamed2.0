import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../core/api";
import { Loading, ErrorState, Badge } from "../design-system/UI";
import { IconShield, IconCheck, IconAlert } from "../design-system/Icons";

// Landing page a patient reaches by SCANNING the QR printed on a prescription.
// It shows the prescribed medicines and tests WITH PRICES, plus a free-text
// search so the scanned sheet can also be used to price anything else.
interface PriceMed {
  brand_id: number | null; name: string | null; found: boolean; strength?: string | null;
  form?: string | null; unit_price: number | null; strip_price: number | null;
  pack_size?: string | null; pieces_per_strip?: number | null;
}
interface PriceTest {
  test_id: number | null; name: string | null; found: boolean; price_min: number | null;
  price_max: number | null; sample_type?: string | null; fasting_required?: boolean;
  offers?: { hospital_name: string | null; location: string | null; price: number | null }[];
}
interface Lookup {
  rx_code: string; issued_at: string | null; prescriber: string | null; patient_initials: string | null;
  diagnosis: string | null; medicines: PriceMed[]; tests: PriceTest[];
  estimated_medicine_cost: number | null; medicine_count: number; test_count: number; disclaimer: string;
}

function money(v: number | null | undefined) {
  return v == null ? "—" : `৳ ${v.toFixed(2)}`;
}

export default function RxScan() {
  const { token } = useParams();
  const [d, setD] = useState<Lookup | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ medicines: any[]; tests: PriceTest[] } | null>(null);

  useEffect(() => {
    api.get<Lookup>(`/api/prices/lookup/${token}`).then(setD).catch((e) => setErr(e.message));
  }, [token]);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setRes(null); return; }
    const t = setTimeout(() => {
      api.get<{ medicines: any[]; tests: PriceTest[] }>(`/api/prices/search?q=${encodeURIComponent(term)}`)
        .then(setRes).catch(() => setRes(null));
    }, 120);
    return () => clearTimeout(t);
  }, [q]);

  if (err) return <div className="container"><ErrorState message={err} /></div>;
  if (!d) return <div className="container"><Loading /></div>;

  return (
    <div className="container narrow">
      <div className="glass card">
        <div className="row-between wrap">
          <div>
            <div className="tiny muted">Scanned prescription</div>
            <h1 style={{ margin: "4px 0" }}>{d.rx_code}</h1>
            <div className="tiny muted">
              Issued {(d.issued_at || "").slice(0, 10)} · {d.prescriber || "—"}
              {d.patient_initials ? ` · patient ${d.patient_initials}` : ""}
            </div>
          </div>
          <div className="col" style={{ alignItems: "flex-end", gap: 6 }}>
            <Badge tone="ok"><IconCheck size={13} /> Verified sheet</Badge>
            {d.estimated_medicine_cost != null && (
              <Badge tone="accent">est. {money(d.estimated_medicine_cost)}</Badge>
            )}
          </div>
        </div>
        <div className="divider" />
        <div className="grid grid-3">
          <div><div className="tiny muted">Medicines</div><div className="name">{d.medicine_count}</div></div>
          <div><div className="tiny muted">Tests</div><div className="name">{d.test_count}</div></div>
          <div><div className="tiny muted">Diagnosis</div><div className="name" style={{ fontSize: 14 }}>{d.diagnosis || "—"}</div></div>
        </div>
      </div>

      <div className="glass card" style={{ marginTop: 14 }}>
        <h3 style={{ marginTop: 0 }}>Medicines &amp; prices</h3>
        {d.medicines.length === 0 && <div className="muted small">No medicines on this prescription.</div>}
        {d.medicines.map((m, i) => (
          <div key={i} className="list-row">
            <div>
              <div className="name">{m.name || "—"} {m.strength ? <span className="tiny muted">{m.strength}</span> : null}</div>
              <div className="tiny muted">
                {m.found ? `${m.form || ""}${m.pack_size ? ` · pack ${m.pack_size}` : ""}` : "Not found in the catalog — ask your pharmacist"}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div className="name">{money(m.strip_price ?? m.unit_price)}</div>
              <div className="tiny muted">{m.strip_price != null ? "per strip" : (m.unit_price != null ? "per unit" : "")}</div>
            </div>
          </div>
        ))}
      </div>

      {d.tests.length > 0 && (
        <div className="glass card" style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>Tests &amp; prices</h3>
          {d.tests.map((t, i) => (
            <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
              <div className="row-between">
                <div>
                  <div className="name">{t.name || "—"}</div>
                  <div className="tiny muted">
                    {[t.sample_type, t.fasting_required ? "fasting required" : null].filter(Boolean).join(" · ") || "—"}
                  </div>
                </div>
                <div className="name" style={{ textAlign: "right" }}>
                  {t.price_min != null ? `${money(t.price_min)}${t.price_max && t.price_max !== t.price_min ? ` – ${money(t.price_max)}` : ""}` : "—"}
                </div>
              </div>
              {(t.offers || []).slice(0, 3).map((o, j) => (
                <div key={j} className="row-between tiny muted" style={{ paddingTop: 2 }}>
                  <span>{o.hospital_name || "—"}{o.location ? ` · ${o.location}` : ""}</span>
                  <span>{money(o.price)}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      <div className="glass card" style={{ marginTop: 14 }}>
        <h3 style={{ marginTop: 0 }}>Price any medicine or test</h3>
        <input className="input" placeholder="e.g. Napa, CBC, Amoxicillin…" value={q} onChange={(e) => setQ(e.target.value)} />
        {q.trim().length >= 2 && res && (
          <div style={{ marginTop: 10 }}>
            {res.medicines.length === 0 && res.tests.length === 0 && <div className="muted small">No matches for “{q.trim()}”.</div>}
            {res.medicines.map((m: any, i: number) => (
              <div key={`m${i}`} className="list-row">
                <div><div className="name">{m.brand}</div><div className="tiny muted">{m.generic} · {m.company}</div></div>
                <div className="name" style={{ textAlign: "right" }}>{money(m.strip_price ?? m.unit_price)}</div>
              </div>
            ))}
            {res.tests.map((t, i) => (
              <div key={`t${i}`} className="list-row">
                <div><div className="name">{t.name}</div><div className="tiny muted">{t.sample_type || "test"}</div></div>
                <div className="name" style={{ textAlign: "right" }}>{money(t.price_min)}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="glass card alert-note" style={{ marginTop: 14 }}>
        <div className="row" style={{ gap: 8 }}><IconShield size={16} /><strong className="small">About these prices</strong></div>
        <p className="tiny muted" style={{ marginBottom: 0 }}>{d.disclaimer}</p>
      </div>
      <div className="row" style={{ gap: 6, marginTop: 10 }}>
        <IconAlert size={13} /><span className="tiny muted">Informational only — not medical advice.</span>
      </div>
    </div>
  );
}
