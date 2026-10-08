import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { Loading, ErrorState } from "../design-system/UI";

interface D {
  id: number; doctor_code: string; name: string; speciality: string | null; qualifications: string | null;
  designation: string | null; bmdc_no: string | null; district: string | null; city: string | null;
  affiliations: { hospital_id: number; hospital: string | null; room: string | null; fee: number | null }[];
  schedules: { id: number; date: string; total_serials: number; session_start: string | null; session_end: string | null; fee: number | null }[];
}

export default function DoctorDetail() {
  const { id } = useParams();
  const [d, setD] = useState<D | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get<D>(`/api/directory/doctors/${id}`).then(setD).catch((e) => setErr(e.message)); }, [id]);
  if (err) return <div className="container"><ErrorState message={err} /></div>;
  if (!d) return <div className="container"><Loading /></div>;

  return (
    <div className="container">
      <Link to="/doctors" className="link small">← Back to doctors</Link>
      <div className="glass card" style={{ marginTop: 12 }}>
        <h1 style={{ marginTop: 0 }}>{d.name}</h1>
        <div className="muted">{d.speciality || "—"}</div>
        <div className="tiny muted" style={{ marginTop: 4 }}>{d.qualifications || ""}</div>
        <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
          {d.bmdc_no && <span className="badge">BMDC {d.bmdc_no}</span>}
          {d.district && <span className="badge">{d.district}</span>}
          <span className="badge">{d.doctor_code}</span>
        </div>
      </div>
      <div className="grid grid-2" style={{ marginTop: 18, alignItems: "start" }}>
        <div className="glass card">
          <h3 style={{ marginTop: 0 }}>Chambers</h3>
          {d.affiliations.length === 0 && <div className="muted small">No chamber information recorded.</div>}
          {d.affiliations.map((a, i) => (
            <Link key={i} to={`/hospitals/${a.hospital_id}`} className="list-row">
              <div>
                <div className="name">{a.hospital || `Hospital #${a.hospital_id}`}</div>
                {a.room && <div className="tiny muted">{a.room}</div>}
              </div>
              {a.fee != null && <span className="badge badge-accent">{bdt(a.fee)}</span>}
            </Link>
          ))}
        </div>
        <div className="glass card">
          <h3 style={{ marginTop: 0 }}>Upcoming schedules</h3>
          {d.schedules.length === 0 && <div className="muted small">No schedules published yet.</div>}
          {d.schedules.map((s) => (
            <div key={s.id} className="list-row">
              <div><div className="name">{s.date}</div><div className="tiny muted">{s.session_start || ""}{s.session_end ? `–${s.session_end}` : ""} · {s.total_serials} serials</div></div>
              {s.fee != null && <span className="badge badge-accent">{bdt(s.fee)}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
