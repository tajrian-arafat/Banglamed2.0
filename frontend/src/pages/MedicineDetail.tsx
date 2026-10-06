import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { Loading, ErrorState, Badge } from "../design-system/UI";
import { IconShield, IconAlert } from "../design-system/Icons";

interface Card { id: number; name: string; form: string; strength: string; generic: string; company: string; unit_price: number | null; strip_price: number | null; pack_size: string | null; pieces_per_strip: number | null; }
interface Detail {
  brand: Card & { med_code: string | null; data_status: string; completeness: number };
  generic: { id: number | null; name: string | null; therapeutic_class: string | null; pregnancy_category: string | null };
  company: { id: number | null; name: string | null; headquarter: string | null };
  sections: Record<string, string | null>;
  other_strengths: Card[];
  alternatives: Card[];
  disclaimer: string;
}

const SECTION_LABELS: Record<string, string> = {
  indications: "Indications", dosage_administration: "Dosage & administration", side_effects: "Side effects",
  precautions_warnings: "Precautions & warnings", pregnancy_lactation: "Pregnancy & lactation",
  overdose_effects: "Overdose", storage_conditions: "Storage", pharmacology: "Pharmacology",
  contraindications: "Contraindications", interaction: "Interactions",
};

export default function MedicineDetail() {
  const { id } = useParams();
  const [d, setD] = useState<Detail | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    setD(null); setErr("");
    api.get<Detail>(`/api/medicines/${id}`).then(setD).catch((e) => setErr(e.message));
  }, [id]);

  if (err) return <div className="container"><ErrorState message={err} /></div>;
  if (!d) return <div className="container"><Loading /></div>;

  const sections = Object.entries(d.sections).filter(([, v]) => v && v.trim());

  return (
    <div className="container">
      <Link to="/medicines" className="link small">← Back to search</Link>
      <div className="glass card" style={{ marginTop: 12 }}>
        <div className="row-between wrap" style={{ gap: 12 }}>
          <div>
            <h1 style={{ margin: 0 }}>{d.brand.name} <span className="muted" style={{ fontSize: "0.6em" }}>{d.brand.strength}</span></h1>
            <div className="muted" style={{ marginTop: 6 }}>
              {d.brand.form || "—"} · {d.generic.name || "—"}
            </div>
            <div className="tiny muted" style={{ marginTop: 4 }}>
              {d.company.name || "—"}{d.brand.med_code ? ` · ${d.brand.med_code}` : ""}
            </div>
          </div>
          <div className="col" style={{ alignItems: "flex-end", gap: 6 }}>
            {d.brand.unit_price != null && <div className="price-big">{bdt(d.brand.unit_price)} <span className="tiny muted">/ unit</span></div>}
            {d.brand.strip_price != null && <div className="tiny muted">Strip: {bdt(d.brand.strip_price)}</div>}
            {d.brand.pack_size && <div className="tiny muted">Pack: {d.brand.pack_size}</div>}
            <Badge tone={d.brand.data_status === "verified" ? "ok" : ""}>{d.brand.data_status}</Badge>
          </div>
        </div>
        <div className="row wrap" style={{ gap: 8, marginTop: 14 }}>
          {d.generic.therapeutic_class && <span className="badge">{d.generic.therapeutic_class}</span>}
          {d.generic.pregnancy_category && <span className="badge badge-warn">Pregnancy cat. {d.generic.pregnancy_category}</span>}
          <span className="badge">Completeness {Math.round((d.brand.completeness || 0) * 100)}%</span>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: 18, alignItems: "start" }}>
        <div className="col" style={{ gap: 14 }}>
          {sections.length === 0 && <div className="glass card muted">No detailed information recorded for this brand.</div>}
          {sections.map(([k, v]) => (
            <div key={k} className="glass card">
              <h3 style={{ marginTop: 0 }}>{SECTION_LABELS[k] || k}</h3>
              <p className="prose">{v}</p>
            </div>
          ))}
        </div>
        <div className="col" style={{ gap: 14 }}>
          <div className="glass card">
            <h3 style={{ marginTop: 0 }}><IconShield size={18} /> Alternatives</h3>
            <p className="tiny muted">Same active ingredient, strength and form — cheapest first.</p>
            {d.alternatives.length === 0 && <div className="muted small">No alternatives found.</div>}
            {d.alternatives.slice(0, 12).map((a) => (
              <Link key={a.id} to={`/medicines/${a.id}`} className="list-row">
                <div>
                  <div className="name">{a.name}</div>
                  <div className="tiny muted">{a.company || "—"}</div>
                </div>
                <span className="badge badge-accent">{bdt(a.unit_price)}</span>
              </Link>
            ))}
          </div>
          {d.other_strengths.length > 0 && (
            <div className="glass card">
              <h3 style={{ marginTop: 0 }}>Other strengths & forms</h3>
              {d.other_strengths.slice(0, 12).map((a) => (
                <Link key={a.id} to={`/medicines/${a.id}`} className="list-row">
                  <div>
                    <div className="name">{a.name} <span className="tiny muted">{a.strength}</span></div>
                    <div className="tiny muted">{a.form || "—"} · {a.company || "—"}</div>
                  </div>
                </Link>
              ))}
            </div>
          )}
          <div className="glass card alert-note">
            <div className="row" style={{ gap: 8 }}><IconAlert size={16} /><strong className="small">Important</strong></div>
            <p className="tiny muted" style={{ marginBottom: 0 }}>{d.disclaimer}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
