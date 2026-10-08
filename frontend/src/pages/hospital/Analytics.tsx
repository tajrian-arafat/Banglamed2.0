import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { Loading, Stat, ErrorState } from "../../design-system/UI";
import { IconChart } from "../../design-system/Icons";

interface A {
  rx_last_30d: number; rx_total: number;
  top_medicines: { name: string; count: number }[];
  top_tests: { name: string; count: number }[];
  doctor_activity: { name: string; count: number }[];
  trend: { date: string; count: number }[];
}

export default function HospitalAnalytics() {
  const [d, setD] = useState<A | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get<A>("/api/analytics/hospital").then(setD).catch((e) => setErr(e.message)); }, []);
  if (err) return <div className="container"><ErrorState message={err} /></div>;
  if (!d) return <div className="container"><Loading /></div>;
  const max = Math.max(1, ...d.trend.map((t) => t.count));

  return (
    <div className="container">
      <h1>Hospital analytics</h1>
      <p className="muted">Prescription activity for your facility.</p>
      <div className="grid grid-4" style={{ marginTop: 18 }}>
        <Stat label="Prescriptions (30d)" value={d.rx_last_30d} />
        <Stat label="Prescriptions (all time)" value={d.rx_total} />
        <Stat label="Top medicines" value={d.top_medicines.length} />
        <Stat label="Active doctors" value={d.doctor_activity.length} />
      </div>
      <div className="glass card" style={{ marginTop: 18 }}>
        <h3 style={{ marginTop: 0 }}><IconChart size={18} /> 14-day trend</h3>
        <div className="bars">
          {d.trend.map((t) => (
            <div key={t.date} className="bar-col" title={`${t.date}: ${t.count}`}>
              <div className="bar" style={{ height: `${(t.count / max) * 100}%` }} />
              <div className="tiny muted">{t.date.slice(8)}</div>
            </div>
          ))}
        </div>
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
    </div>
  );
}
