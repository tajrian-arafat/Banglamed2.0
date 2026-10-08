import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../core/api";
import { dateStr } from "../core/format";
import { Loading, ErrorState, Badge } from "../design-system/UI";
import { IconShield, IconCheck, IconAlert } from "../design-system/Icons";

interface Rx {
  rx_code: string; issued_at: string; status: string;
  doctor: { name: string; bmdc_no: string | null; speciality: string | null; qualifications: string | null } | null;
  patient: { patient_code: string; full_name: string; sex: string | null; dob: string | null } | null;
  diagnosis: string | null; chief_complaints: string | null; notes: string | null; advice: string | null;
  items: { name: string | null; form: string | null; strength: string | null; bn_dosage_text: string | null; instructions: string | null;
           company?: string | null; unit_price?: number | null; strip_price?: number | null;
           pack_size?: string | null; pack_price?: number | null; alternative_companies?: number }[];
  tests: { name: string | null; note: string | null; price_min?: number | null; price_max?: number | null }[];
  verified: boolean; disclaimer: string;
}

/** Currency for the catalogue (BDT). */
function tk(v?: number | null) { return v == null ? null : `\u09f3${v.toFixed(2)}`; }

export default function RxPublic() {
  const { token } = useParams();
  const [d, setD] = useState<Rx | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get<Rx>(`/api/prescriptions/public/${token}`).then(setD).catch((e) => setErr(e.message)); }, [token]);
  if (err) return <div className="container"><ErrorState message={err} /></div>;
  if (!d) return <div className="container"><Loading /></div>;

  return (
    <div className="container narrow">
      <div className="glass card">
        <div className="row-between wrap">
          <div>
            <div className="tiny muted">Prescription</div>
            <h1 style={{ margin: "4px 0" }}>{d.rx_code}</h1>
            <div className="tiny muted">Issued {dateStr(d.issued_at)}</div>
          </div>
          <div className="col" style={{ alignItems: "flex-end", gap: 6 }}>
            {d.verified ? <Badge tone="ok"><IconCheck size={13} /> Verified</Badge> : <Badge tone="warn"><IconAlert size={13} /> Unverified</Badge>}
            <Badge>{d.status}</Badge>
          </div>
        </div>
        <div className="divider" />
        <div className="grid grid-2">
          <div>
            <div className="tiny muted">Doctor</div>
            <div className="name">{d.doctor?.name || "\u2014"}</div>
            <div className="tiny muted">{d.doctor?.speciality || ""}{d.doctor?.bmdc_no ? ` \u00b7 BMDC ${d.doctor.bmdc_no}` : ""}</div>
          </div>
          <div>
            <div className="tiny muted">Patient</div>
            <div className="name">{d.patient?.full_name || "\u2014"}</div>
            <div className="tiny muted">{d.patient?.patient_code || ""}</div>
          </div>
        </div>
      </div>

      {(d.diagnosis || d.chief_complaints) && (
        <div className="glass card" style={{ marginTop: 14 }}>
          {d.chief_complaints && <><div className="tiny muted">Chief complaints</div><p className="prose">{d.chief_complaints}</p></>}
          {d.diagnosis && <><div className="tiny muted">Diagnosis</div><p className="prose">{d.diagnosis}</p></>}
        </div>
      )}

      <div className="glass card" style={{ marginTop: 14 }}>
        <h3 style={{ marginTop: 0 }}>Medicines</h3>
        {d.items.length === 0 && <div className="muted small">No medicines listed.</div>}
        {d.items.map((it, i) => (
          <div key={i} className="rx-item">
            <div className="row-between">
              <div className="name">{i + 1}. {it.name || "\u2014"} <span className="tiny muted">{it.strength || ""}</span></div>
              <span className="tiny muted">{it.form || ""}</span>
            </div>
            {it.bn_dosage_text && <div className="bn-dosage">{it.bn_dosage_text}</div>}
            {it.instructions && <div className="tiny muted">{it.instructions}</div>}
            <div className="row wrap" style={{ gap: 10, marginTop: 4 }}>
              {it.company && <span className="tiny muted">{it.company}</span>}
              {tk(it.unit_price) && <Badge>{tk(it.unit_price)} / unit</Badge>}
              {tk(it.pack_price) && <Badge tone="ok">{it.pack_size ? `${it.pack_size} \u00b7 ` : ""}{tk(it.pack_price)}</Badge>}
              {tk(it.strip_price) && <span className="tiny muted">{tk(it.strip_price)} / strip</span>}
              {!!it.alternative_companies && <span className="tiny muted">{it.alternative_companies} alternative compan{it.alternative_companies === 1 ? "y" : "ies"}</span>}
            </div>
          </div>
        ))}
      </div>

      {d.tests.length > 0 && (
        <div className="glass card" style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>Tests advised</h3>
          {d.tests.map((t, i) => (
            <div key={i} className="list-row">
              <div className="name">{t.name || "\u2014"}</div>
              <div className="row" style={{ gap: 8, alignItems: "center" }}>
                {t.note && <span className="tiny muted">{t.note}</span>}
                {(tk(t.price_min) || tk(t.price_max)) && (
                  <Badge tone="ok">{tk(t.price_min) && tk(t.price_max) ? `${tk(t.price_min)} \u2013 ${tk(t.price_max)}` : (tk(t.price_min) || tk(t.price_max))}</Badge>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {d.advice && <div className="glass card" style={{ marginTop: 14 }}><h3 style={{ marginTop: 0 }}>Advice</h3><p className="prose">{d.advice}</p></div>}

      <div className="glass card alert-note" style={{ marginTop: 14 }}>
        <div className="row" style={{ gap: 8 }}><IconShield size={16} /><strong className="small">Integrity</strong></div>
        <p className="tiny muted" style={{ marginBottom: 0 }}>
          {d.verified ? "The digital seal on this prescription is intact \u2014 its contents have not been altered since it was issued." : "This prescription is not sealed or the seal could not be verified."}
        </p>
      </div>
      <p className="tiny muted" style={{ marginTop: 12 }}>{d.disclaimer}</p>
    </div>
  );
}
