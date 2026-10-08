import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../core/api";
import { bdt } from "../core/format";
import { Loading, ErrorState } from "../design-system/UI";

interface D {
  id: number; name: string; district: string | null; address: string | null; phone: string | null; hours: string | null; about: string | null;
  listed_doctors: number | null; doctors_count: number;
  doctors: { id: number; name: string; speciality: string | null; room: string | null; fee: number | null }[];
}

export default function HospitalDetail() {
  const { id } = useParams();
  const [d, setD] = useState<D | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get<D>(`/api/directory/hospitals/${id}`).then(setD).catch((e) => setErr(e.message)); }, [id]);
  if (err) return <div className="container"><ErrorState message={err} /></div>;
  if (!d) return <div className="container"><Loading /></div>;

  return (
    <div className="container">
      <Link to="/hospitals" className="link small">← Back to hospitals</Link>
      <div className="glass card" style={{ marginTop: 12 }}>
        <h1 style={{ marginTop: 0 }}>{d.name}</h1>
        <div className="muted">{d.district || "—"}</div>
        <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
          {d.address && <span className="badge">{d.address}</span>}
          {d.phone && <span className="badge">{d.phone}</span>}
          {d.hours && <span className="badge">{d.hours}</span>}
        </div>
        {d.about && <p className="prose" style={{ marginTop: 14 }}>{d.about}</p>}
      </div>
      <div className="glass card" style={{ marginTop: 18 }}>
        <h3 style={{ marginTop: 0 }}>
          Doctors at this facility
          {d.doctors_count > 0 && <span className="muted small" style={{ fontWeight: 400 }}> · {d.doctors_count}</span>}
        </h3>
        {d.doctors.length === 0 && (
          <div className="muted small">
            No individual doctor profiles are linked for this facility yet.
            {d.listed_doctors != null && d.listed_doctors > 0 && ` The source listing advertises ${d.listed_doctors} doctors.`}
          </div>
        )}
        <div className="grid grid-2">
          {d.doctors.map((doc) => (
            <Link key={doc.id} to={`/doctors/${doc.id}`} className="list-row">
              <div><div className="name">{doc.name}</div><div className="tiny muted">{doc.speciality || "—"}{doc.room ? ` · ${doc.room}` : ""}</div></div>
              {doc.fee != null && <span className="badge badge-accent">{bdt(doc.fee)}</span>}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
