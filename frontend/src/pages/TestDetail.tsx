import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { Loading, ErrorState, Badge } from "../design-system/UI";

interface D {
  id: number; name: string; sample_type: string | null; price_min: number | null; price_max: number | null;
  fasting_required: boolean; fasting_hours_min: number | null; fasting_hours_max: number | null;
  prep_text: string | null; report_time: string | null; procedure_text: string | null;
  prices: { hospital_name: string; location: string | null; price: number | null; badge: string | null }[];
  disclaimer: string;
}

export default function TestDetail() {
  const { id } = useParams();
  const [d, setD] = useState<D | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get<D>(`/api/tests/${id}`).then(setD).catch((e) => setErr(e.message)); }, [id]);
  if (err) return <div className="container"><ErrorState message={err} /></div>;
  if (!d) return <div className="container"><Loading /></div>;

  return (
    <div className="container">
      <Link to="/tests" className="link small">← Back to tests</Link>
      <div className="glass card" style={{ marginTop: 12 }}>
        <h1 style={{ marginTop: 0 }}>{d.name}</h1>
        <div className="row wrap" style={{ gap: 8 }}>
          {d.sample_type && <span className="badge">Sample: {d.sample_type}</span>}
          {d.fasting_required && <span className="badge badge-warn">Fasting {d.fasting_hours_min ?? ""}{d.fasting_hours_max ? `–${d.fasting_hours_max}` : ""}h</span>}
          {d.report_time && <span className="badge">Report: {d.report_time}</span>}
          {d.price_min != null && <span className="badge badge-accent">{bdt(d.price_min)}{d.price_max && d.price_max !== d.price_min ? ` – ${bdt(d.price_max)}` : ""}</span>}
        </div>
      </div>
      <div className="grid grid-2" style={{ marginTop: 18, alignItems: "start" }}>
        <div className="col" style={{ gap: 14 }}>
          {d.prep_text && <div className="glass card"><h3 style={{ marginTop: 0 }}>Preparation</h3><p className="prose">{d.prep_text}</p></div>}
          {d.procedure_text && <div className="glass card"><h3 style={{ marginTop: 0 }}>How it is done</h3><p className="prose">{d.procedure_text}</p></div>}
          {!d.prep_text && !d.procedure_text && <div className="glass card muted">No preparation or procedure notes recorded.</div>}
        </div>
        <div className="glass card">
          <h3 style={{ marginTop: 0 }}>Prices by hospital</h3>
          {d.prices.length === 0 && <div className="muted small">No hospital prices recorded.</div>}
          {d.prices.map((p, i) => (
            <div key={i} className="list-row">
              <div>
                <div className="name">{p.hospital_name}</div>
                <div className="tiny muted">{p.location || "—"}</div>
              </div>
              <div className="row" style={{ gap: 6 }}>
                {p.badge && <Badge tone="ok">{p.badge}</Badge>}
                <span className="badge badge-accent">{bdt(p.price)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <p className="tiny muted" style={{ marginTop: 14 }}>{d.disclaimer}</p>
    </div>
  );
}
