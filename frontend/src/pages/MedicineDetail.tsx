import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { Loading, ErrorState, Badge } from "../design-system/UI";
import { IconShield, IconAlert } from "../design-system/Icons";

interface Card { id: number; name: string; form: string | null; strength: string | null; generic: string | null; company: string | null; unit_price: number | null; strip_price: number | null; pack_size: string | null; pieces_per_strip: number | null; }
interface Detail {
  brand: Card & { med_code: string | null; data_status: string; completeness: number };
  generic: { id: number | null; name: string | null; therapeutic_class: string | null; pregnancy_category: string | null };
  company: { id: number | null; name: string | null; headquarter: string | null };
  sections: Record<string, string | null>;
  // relationship groups — each list is capped; the *_count is the true total
  alternatives: Card[];
  alternatives_count: number;
  other_forms: Card[];
  other_forms_count: number;
  other_strengths: Card[];
  other_strengths_count: number;
  brand_family: Card[];
  brand_family_count: number;
  same_generic_total: number;
  disclaimer: string;
}

const SECTION_LABELS: Record<string, string> = {
  indications: "Indications", dosage_administration: "Dosage & administration", side_effects: "Side effects",
  precautions_warnings: "Precautions & warnings", pregnancy_lactation: "Pregnancy & lactation",
  overdose_effects: "Overdose", storage_conditions: "Storage", pharmacology: "Pharmacology",
  contraindications: "Contraindications", interaction: "Interactions",
};

const RENDER_CAP = 12;

/** One related-product row. Always links to that product's own detail page. */
function RelatedRow({ a, show }: { a: Card; show?: "form" | "strength" }) {
  return (
    <Link key={a.id} to={`/medicines/${a.id}`} className="list-row">
      <div>
        <div className="name">
          {a.name}
          {a.strength ? <span className="tiny muted"> {a.strength}</span> : null}
        </div>
        <div className="tiny muted">
          {show === "form" && a.form ? `${a.form} · ` : ""}
          {show === "strength" && a.form ? `${a.form} · ` : ""}
          {a.company || a.pack_size || a.form || "—"}
        </div>
      </div>
      {a.unit_price != null && <span className="badge badge-accent">{bdt(a.unit_price)}</span>}
    </Link>
  );
}

/** Shared card for a relationship group: truthful count in the header, an
 *  explicit empty message so an empty group is never a blank box, and an
 *  expander so EVERY related product is reachable from the UI (a generic can
 *  hold up to 389 brands, so a fixed preview would strand most of them). */
function Group({
  title, hint, items, total, show, empty,
}: {
  title: string; hint?: string; items: Card[]; total: number;
  show?: "form" | "strength"; empty: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? items : items.slice(0, RENDER_CAP);
  // Only a server-side cap can leave rows truly unreachable; the client-side
  // preview is now expandable.
  const notReturned = Math.max(0, total - items.length);
  return (
    <div className="glass card">
      <div className="row-between wrap" style={{ gap: 8 }}>
        <h3 style={{ marginTop: 0, marginBottom: 0 }}>
          {title} {total > 0 && <span className="badge">{total}</span>}
        </h3>
      </div>
      {hint && <p className="tiny muted" style={{ marginTop: 6 }}>{hint}</p>}
      {total === 0 && <div className="muted small">{empty}</div>}
      {shown.map((a) => <RelatedRow key={a.id} a={a} show={show} />)}
      {notReturned > 0 && (
        <div className="tiny muted" style={{ marginTop: 6 }}>
          +{notReturned} more could not be returned.
        </div>
      )}
      {items.length > RENDER_CAP && (
        <button
          className="btn btn-sm"
          style={{ marginTop: 10 }}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Show fewer" : `Show all ${total.toLocaleString()}`}
        </button>
      )}
    </div>
  );
}

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
  const hasGeneric = d.generic.id != null;

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
          {hasGeneric && d.same_generic_total > 0 && (
            <span className="badge">{d.same_generic_total} other brands share this generic</span>
          )}
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
          <Group
            title="Alternative brands"
            hint="Same active ingredient, strength and dosage form — cheapest first."
            items={d.alternatives}
            total={d.alternatives_count}
            empty={hasGeneric
              ? "No other brand has this exact generic, strength and form."
              : "This brand has no generic recorded, so alternatives cannot be matched."}
          />
          <Group
            title="Other dosage forms"
            hint="Same active ingredient and strength, in a different form."
            items={d.other_forms}
            total={d.other_forms_count}
            show="form"
            empty="No other dosage form at this strength."
          />
          <Group
            title="Other strengths"
            hint="Same active ingredient and dosage form, at a different strength."
            items={d.other_strengths}
            total={d.other_strengths_count}
            show="strength"
            empty="No other strength in this dosage form."
          />
          {(d.brand_family_count > 0) && (
            <Group
              title="Same brand family"
              hint="Same brand line, different strength or form."
              items={d.brand_family}
              total={d.brand_family_count}
              empty="No other product in this brand family."
            />
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
