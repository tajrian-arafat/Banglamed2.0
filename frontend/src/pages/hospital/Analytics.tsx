import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { Loading, Stat, ErrorState, Badge } from "../../design-system/UI";
import { IconChart, IconUser } from "../../design-system/Icons";

// Two audiences share this page:
//  * hospital_admin — scoped by the server to ITS OWN facility. It sees the
//    facility totals plus a panel listing EVERY doctor working at that facility,
//    not only the ones who happen to have prescriptions.
//  * system_admin — the same view plus a facility picker, because it may read
//    analytics for ANY hospital, and an all-facilities table.
interface A {
  rx_last_30d: number; rx_total: number;
  top_medicines: { name: string; count: number }[];
  top_tests: { name: string; count: number }[];
  doctor_activity: { name: string; count: number }[];
  trend: { date: string; count: number }[];
}
interface FacilityDoctor {
  doctor_id: number; name: string; speciality: string | null; doctor_code: string | null;
  affiliations: number; prescriptions: number; last_activity: string | null;
}
interface Overview {
  scope: string; count: number;
  totals: { facilities: number; rx_total: number; rx_last_30d: number };
  facilities: { hospital_id: number; name: string; district: string | null; rx_total: number }[];
}

export default function HospitalAnalytics() {
  const [d, setD] = useState<A | null>(null);
  const [doctors, setDoctors] = useState<FacilityDoctor[]>([]);
  const [docTotal, setDocTotal] = useState(0);
  const [facility, setFacility] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const sys = await api.get<any>("/api/analytics/system").then(() => true).catch(() => false);
        setIsAdmin(sys);
        const q = facility ? `?hospital_id=${facility}` : "";
        const [a, dc] = await Promise.all([
          api.get<A>(`/api/analytics/hospital${q}`),
          api.get<{ total: number; results: FacilityDoctor[] }>(`/api/analytics/hospital/doctors${q}`).catch(() => ({ total: 0, results: [] })),
        ]);
        setD(a); setDoctors(dc.results); setDocTotal(dc.total);
        if (sys) setOverview(await api.get<Overview>("/api/analytics/hospitals-overview").catch(() => null));
      } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
    })();
  }, [facility]);

  if (err) return <div className="container"><ErrorState message={err} /></div>;
  if (loading || !d) return <div className="container"><Loading /></div>;
  const max = Math.max(1, ...d.trend.map((t) => t.count));

  return (
    <div className="container">
      <div className="row-between wrap">
        <div>
          <h1 style={{ marginBottom: 4 }}>Hospital analytics</h1>
          <p className="muted" style={{ margin: 0 }}>
            {isAdmin ? "All facilities (system admin)." : "Prescription activity for your facility."}
          </p>
        </div>
        {isAdmin && overview && (
          <label className="field" style={{ width: 280 }}>
            <span>Facility</span>
            <select className="input" value={facility} onChange={(e) => setFacility(e.target.value)}>
              <option value="">All facilities ({overview.totals.facilities})</option>
              {overview.facilities.map((h) => (
                <option key={h.hospital_id} value={h.hospital_id}>{h.name} — {h.rx_total} rx</option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="grid grid-4" style={{ marginTop: 18 }}>
        <Stat label="Prescriptions (30d)" value={d.rx_last_30d} />
        <Stat label="Prescriptions (all time)" value={d.rx_total} />
        <Stat label="Doctors at facility" value={docTotal} />
        <Stat label="Prescribing doctors" value={d.doctor_activity.length} />
      </div>

      <div className="glass card" style={{ marginTop: 18 }}>
        <h3 style={{ marginTop: 0 }}><IconChart size={18} /> 14-day trend</h3>
        {d.trend.length === 0 && <div className="muted small">No activity in this window.</div>}
        <div className="bars">
          {d.trend.map((t) => (
            <div key={t.date} className="bar-col" title={`${t.date}: ${t.count}`}>
              <div className="bar" style={{ height: `${(t.count / max) * 100}%` }} />
              <div className="tiny muted">{t.date.slice(8)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Every doctor linked to the facility — the panel that was previously missing */}
      <div className="glass card" style={{ marginTop: 18 }}>
        <div className="row-between">
          <h3 style={{ marginTop: 0 }}><IconUser size={18} /> Doctors at this facility</h3>
          <Badge>{docTotal} total</Badge>
        </div>
        {doctors.length === 0 && <div className="muted small">No doctors are linked to this facility yet.</div>}
        {doctors.map((doc) => (
          <div key={doc.doctor_id} className="list-row">
            <div>
              <div className="name">{doc.name}</div>
              <div className="tiny muted">
                {doc.speciality || "—"} · {doc.doctor_code || "—"} · {doc.affiliations} affiliation(s)
                {doc.last_activity ? ` · last ${doc.last_activity.slice(0, 10)}` : ""}
              </div>
            </div>
            <span className="badge badge-accent">{doc.prescriptions} rx</span>
          </div>
        ))}
      </div>

      <div className="grid grid-3" style={{ marginTop: 18, alignItems: "start" }}>
        <div className="glass card">
          <h3 style={{ marginTop: 0 }}>Top medicines</h3>
          {d.top_medicines.length === 0 && <div className="muted small">No data yet.</div>}
          {d.top_medicines.map((m, i) => <div key={i} className="list-row"><div className="name">{m.name}</div><span className="badge badge-accent">{m.count}</span></div>)}
        </div>
        <div className="glass card">
          <h3 style={{ marginTop: 0 }}>Top tests</h3>
          {d.top_tests.length === 0 && <div className="muted small">No data yet.</div>}
          {d.top_tests.map((m, i) => <div key={i} className="list-row"><div className="name">{m.name}</div><span className="badge badge-accent">{m.count}</span></div>)}
        </div>
        <div className="glass card">
          <h3 style={{ marginTop: 0 }}>Doctor activity</h3>
          {d.doctor_activity.length === 0 && <div className="muted small">No data yet.</div>}
          {d.doctor_activity.map((m, i) => <div key={i} className="list-row"><div className="name">{m.name}</div><span className="badge badge-accent">{m.count}</span></div>)}
        </div>
      </div>

      {isAdmin && overview && (
        <div className="glass card" style={{ marginTop: 18 }}>
          <h3 style={{ marginTop: 0 }}>All facilities</h3>
          <p className="muted small" style={{ marginTop: 0 }}>
            Cross-facility roll-up — visible to the system admin only. {overview.totals.facilities} facilities,
            {overview.totals.rx_total} prescriptions.
          </p>
          {overview.facilities.map((h) => (
            <div key={h.hospital_id} className="list-row">
              <div className="name">{h.name}</div>
              <span className="badge">{h.rx_total} rx</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
