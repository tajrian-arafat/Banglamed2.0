import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { Loading, useToast, Badge } from "../../design-system/UI";
import { MedicineSearch } from "../../components/MedicineSearch";
import { IconPlus, IconTrash, IconShield, IconAlert, IconCheck, IconQr } from "../../design-system/Icons";

interface P { id: number; full_name: string; patient_code: string; }
interface Item { brand_id: number; name: string; strength: string; form: string; slots: Record<string, number>; meal: string; duration: number | null; kind: string; }
interface Warn { code: string; severity: string; message: string; medicines_involved?: string[]; }

const SLOTS = ["morning", "noon", "evening", "night"];

export default function DoctorPrescribe() {
  const [patients, setPatients] = useState<P[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [diagnosis, setDiagnosis] = useState("");
  const [advice, setAdvice] = useState("");
  const [warnings, setWarnings] = useState<Warn[]>([]);
  const [acks, setAcks] = useState<Record<string, boolean>>({});
  const [rxId, setRxId] = useState<number | null>(null);
  const [rxCode, setRxCode] = useState("");
  const [qr, setQr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { toast, toastNode } = useToast();

  useEffect(() => {
    api.get<{ results: P[] }>("/api/doctor/patients?limit=100").then((r) => { setPatients(r.results); if (r.results[0]) setPid(r.results[0].id); });
  }, []);

  function addItem(brandId: number) {
    api.get<any>(`/api/medicines/${brandId}`).then((d) => {
      setItems((prev) => [...prev, {
        brand_id: brandId, name: d.brand.name, strength: d.brand.strength || "", form: d.brand.form || "",
        slots: { morning: 1, night: 1 }, meal: "after", duration: 7, kind: "course",
      }]);
    });
  }

  function upd(i: number, patch: Partial<Item>) { setItems((prev) => prev.map((it, idx) => idx === i ? { ...it, ...patch } : it)); }
  function setSlot(i: number, slot: string, v: number) { setItems((prev) => prev.map((it, idx) => idx === i ? { ...it, slots: { ...it.slots, [slot]: v } } : it)); }
  function rm(i: number) { setItems((prev) => prev.filter((_, idx) => idx !== i)); }

  function payload() {
    return {
      patient_id: pid,
      diagnosis: diagnosis || null,
      advice: advice || null,
      items: items.map((it) => ({
        brand_id: it.brand_id,
        dose: { slots: it.slots, unit: (it.form || "tablet").toLowerCase().includes("syrup") ? "syrup" : "tablet", meal: it.meal,
                duration: it.kind === "course" ? { value: it.duration, unit: "day" } : { kind: it.kind } },
      })),
      tests: [],
      acknowledgements: Object.keys(acks).filter((k) => acks[k]).map((code) => ({ code, reason: "acknowledged by doctor" })),
    };
  }

  async function check() {
    if (!pid || items.length === 0) return;
    setBusy(true);
    try {
      const r = await api.post<{ warnings: Warn[] }>("/api/prescriptions/safety-check", { patient_id: pid, items: payload().items });
      setWarnings(r.warnings);
      toast(r.warnings.length ? `${r.warnings.length} safety note(s)` : "No safety issues found");
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  }

  async function save() {
    if (!pid || items.length === 0) return;
    setBusy(true);
    try {
      const r = await api.post<{ id: number; rx_code: string }>("/api/prescriptions", payload());
      setRxId(r.id); setRxCode(r.rx_code); toast(`Saved ${r.rx_code}`);
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  }

  async function finalize() {
    if (!rxId) return;
    setBusy(true);
    try {
      await api.post(`/api/prescriptions/${rxId}/finalize`);
      const q = await api.get<{ qr_png_base64: string }>(`/api/prescriptions/${rxId}/qr`);
      setQr(q.qr_png_base64); toast("Prescription finalized & sealed");
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="container">
      {toastNode}
      <h1>Write a prescription</h1>
      <p className="muted">Search medicines, set the dose, run safety checks, then finalize with a digital seal.</p>

      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <div className="col" style={{ gap: 14 }}>
          <div className="glass card">
            <label className="field"><span>Patient</span>
              <select className="input" value={pid ?? ""} onChange={(e) => setPid(Number(e.target.value))}>
                {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.patient_code})</option>)}
              </select>
            </label>
            <label className="field" style={{ marginTop: 10 }}><span>Diagnosis</span>
              <input className="input" value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} placeholder="e.g. Acute pharyngitis" />
            </label>
            <label className="field" style={{ marginTop: 10 }}><span>Advice</span>
              <textarea className="input" rows={2} value={advice} onChange={(e) => setAdvice(e.target.value)} placeholder="Rest, fluids…" />
            </label>
          </div>

          <div className="glass card">
            <h3 style={{ marginTop: 0 }}><IconPlus size={18} /> Add medicine</h3>
            <MedicineSearch onPick={addItem} placeholder="Search a medicine to add…" />
          </div>

          {items.map((it, i) => (
            <div key={i} className="glass card">
              <div className="row-between">
                <div><div className="name">{it.name} <span className="tiny muted">{it.strength}</span></div><div className="tiny muted">{it.form}</div></div>
                <button className="btn btn-sm btn-ghost" onClick={() => rm(i)}><IconTrash size={15} /></button>
              </div>
              <div className="row wrap" style={{ gap: 10, marginTop: 10 }}>
                {SLOTS.map((s) => (
                  <label key={s} className="field" style={{ width: 90 }}>
                    <span style={{ textTransform: "capitalize" }}>{s}</span>
                    <input className="input" type="number" step="0.5" min="0" value={it.slots[s] ?? 0} onChange={(e) => setSlot(i, s, Number(e.target.value))} />
                  </label>
                ))}
                <label className="field" style={{ width: 130 }}><span>Meal</span>
                  <select className="input" value={it.meal} onChange={(e) => upd(i, { meal: e.target.value })}>
                    <option value="after">After food</option><option value="before">Before food</option>
                    <option value="empty_stomach">Empty stomach</option><option value="bedtime">Bedtime</option>
                  </select>
                </label>
                <label className="field" style={{ width: 120 }}><span>Duration</span>
                  <select className="input" value={it.kind} onChange={(e) => upd(i, { kind: e.target.value })}>
                    <option value="course">Fixed days</option><option value="continue">Continue</option><option value="as_needed">As needed</option>
                  </select>
                </label>
                {it.kind === "course" && (
                  <label className="field" style={{ width: 100 }}><span>Days</span>
                    <input className="input" type="number" min="1" value={it.duration ?? 7} onChange={(e) => upd(i, { duration: Number(e.target.value) })} />
                  </label>
                )}
              </div>
            </div>
          ))}

          <div className="row" style={{ gap: 10 }}>
            <button className="btn" onClick={check} disabled={busy || items.length === 0}><IconShield size={16} /> Safety check</button>
            <button className="btn btn-primary" onClick={save} disabled={busy || items.length === 0}>Save draft</button>
            {rxId && <button className="btn btn-primary" onClick={finalize} disabled={busy}><IconCheck size={16} /> Finalize & seal</button>}
          </div>
        </div>

        <div className="col" style={{ gap: 14 }}>
          <div className="glass card">
            <h3 style={{ marginTop: 0 }}><IconShield size={18} /> Safety</h3>
            {warnings.length === 0 && <div className="muted small">Run a safety check to see warnings.</div>}
            {warnings.map((w, i) => (
              <div key={i} className={`alert ${w.severity === "critical" ? "alert-error" : "alert-note"}`} style={{ marginBottom: 8 }}>
                <div className="row-between">
                  <div className="row" style={{ gap: 6 }}><IconAlert size={15} /><strong className="small">{w.code.replace(/_/g, " ")}</strong></div>
                  <Badge tone={w.severity === "critical" ? "warn" : ""}>{w.severity}</Badge>
                </div>
                <div className="tiny" style={{ marginTop: 4 }}>{w.message}</div>
                {w.severity === "critical" && (
                  <label className="row tiny" style={{ gap: 6, marginTop: 6 }}>
                    <input type="checkbox" checked={!!acks[w.code]} onChange={(e) => setAcks({ ...acks, [w.code]: e.target.checked })} />
                    Acknowledge to proceed
                  </label>
                )}
              </div>
            ))}
          </div>
          {rxCode && (
            <div className="glass card">
              <h3 style={{ marginTop: 0 }}><IconQr size={18} /> {rxCode}</h3>
              {qr ? <img src={`data:image/png;base64,${qr}`} alt="Prescription QR" style={{ width: 180, height: 180, background: "#fff", borderRadius: 12, padding: 8 }} />
                  : <div className="muted small">Finalize to generate the verification QR.</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
