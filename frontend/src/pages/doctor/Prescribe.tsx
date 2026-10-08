import { useCallback, useEffect, useMemo, useState } from "react";
import { api, getToken } from "../../core/api";
import { useToast, Badge, Loading } from "../../design-system/UI";
import { MedicineSearch } from "../../components/MedicineSearch";
import { IconPlus, IconTrash, IconShield, IconAlert, IconCheck, IconPrinter, IconFile } from "../../design-system/Icons";

interface P { id: number; full_name: string; patient_code: string; sex?: string | null; dob?: string | null; }
interface Item {
  brand_id: number | null; name: string; strength: string; form: string;
  slots: Record<string, number>; meal: string; duration: number | null; kind: string;
}
interface TestRow { test_id: number | null; name: string; note: string; price_min?: number | null; }
interface Warn { code: string; severity: string; message: string; medicines_involved?: string[]; }
interface MyRx { id: number; rx_code: string; status: string; issued_at: string | null; patient_name: string | null; patient_code: string | null; diagnosis: string | null; versions: number; }
interface VersionRow { version: number; reason: string | null; created_at: string | null; content_hash: string | null; item_count: number; test_count: number; }
interface Doctor { name?: string; speciality?: string; qualifications?: string; designation?: string; bmdc_no?: string; }

const SLOTS = ["morning", "noon", "evening", "night"];
const MEALS: Record<string, string> = { after: "After food", before: "Before food", empty_stomach: "Empty stomach", bedtime: "Bedtime" };

function slotText(slots: Record<string, number>) {
  const parts = SLOTS.filter((s) => slots[s]).map((s) => `${s.slice(0, 2).replace(/^\w/, (c) => c.toUpperCase())} ${slots[s]}`);
  return parts.length ? parts.join(" + ") : "—";
}
function durText(it: Item) {
  if (it.kind === "course") return it.duration ? `${it.duration} day${it.duration === 1 ? "" : "s"}` : "—";
  return it.kind.replace(/_/g, " ");
}

export default function DoctorPrescribe() {
  const [patients, setPatients] = useState<P[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [tests, setTests] = useState<TestRow[]>([]);
  const [diagnosis, setDiagnosis] = useState("");
  const [complaints, setComplaints] = useState("");
  const [advice, setAdvice] = useState("");
  const [warnings, setWarnings] = useState<Warn[]>([]);
  const [acks, setAcks] = useState<Record<string, boolean>>({});
  const [rxId, setRxId] = useState<number | null>(null);
  const [rxCode, setRxCode] = useState("");
  const [status, setStatus] = useState<string>("draft");
  const [versions, setVersions] = useState<VersionRow[]>([]);
  const [mine, setMine] = useState<MyRx[]>([]);
  const [doctor, setDoctor] = useState<Doctor>({});
  const [busy, setBusy] = useState(false);
  const [booting, setBooting] = useState(true);
  const { toast, toastNode } = useToast();

  const patient = useMemo(() => patients.find((p) => p.id === pid) || null, [patients, pid]);

  const loadMine = useCallback(() => {
    api.get<{ results: MyRx[] }>("/api/prescriptions/mine?limit=25")
      .then((r) => setMine(r.results)).catch(() => {});
  }, []);

  useEffect(() => {
    Promise.all([
      api.get<{ results: P[] }>("/api/doctor/patients?limit=100").catch(() => ({ results: [] as P[] })),
      api.get<any>("/api/doctor/profile").catch(() => null),
    ]).then(([p, d]) => {
      setPatients(p.results);
      if (p.results[0]) setPid(p.results[0].id);
      const prof = d?.doctor && typeof d.doctor === "object" ? d.doctor : (d || {});
      setDoctor(prof || {});
    }).finally(() => setBooting(false));
    loadMine();
  }, [loadMine]);

  function addItem(brandId: number) {
    api.get<any>(`/api/medicines/${brandId}`).then((d) => {
      setItems((prev) => [...prev, {
        brand_id: brandId, name: d.brand.name, strength: d.brand.strength || "", form: d.brand.form || "",
        slots: { morning: 1, night: 1 }, meal: "after", duration: 7, kind: "course",
      }]);
    }).catch((e: any) => toast(e.message));
  }
  function upd(i: number, patch: Partial<Item>) { setItems((prev) => prev.map((it, idx) => idx === i ? { ...it, ...patch } : it)); }
  function setSlot(i: number, slot: string, v: number) { setItems((prev) => prev.map((it, idx) => idx === i ? { ...it, slots: { ...it.slots, [slot]: v } } : it)); }
  function rm(i: number) { setItems((prev) => prev.filter((_, idx) => idx !== i)); }

  function addTestRow() { setTests((prev) => [...prev, { test_id: null, name: "", note: "" }]); }
  function pickTest(i: number, testId: number) {
    api.get<any>(`/api/tests/${testId}`).then((t) => {
      const name = t?.test?.name || t?.name || "";
      setTests((prev) => prev.map((row, idx) => idx === i ? { ...row, test_id: testId, name } : row));
    }).catch((e: any) => toast(e.message));
  }
  function updTest(i: number, patch: Partial<TestRow>) { setTests((prev) => prev.map((row, idx) => idx === i ? { ...row, ...patch } : row)); }
  function rmTest(i: number) { setTests((prev) => prev.filter((_, idx) => idx !== i)); }

  function payload() {
    return {
      patient_id: pid,
      diagnosis: diagnosis || null,
      chief_complaints: complaints || null,
      advice: advice || null,
      items: items.map((it) => ({
        brand_id: it.brand_id,
        dose: {
          slots: it.slots,
          unit: (it.form || "tablet").toLowerCase().includes("syrup") ? "syrup" : "tablet",
          meal: it.meal,
          duration: it.kind === "course" ? { value: it.duration, unit: "day" } : { kind: it.kind },
        },
      })),
      tests: tests.filter((t) => t.test_id || t.name.trim()).map((t) => ({
        test_id: t.test_id, free_text_name: t.test_id ? null : t.name.trim(), note: t.note || null,
      })),
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

  async function refreshVersions(id: number) {
    try {
      const v = await api.get<{ results: VersionRow[] }>(`/api/prescriptions/${id}/versions`);
      setVersions(v.results);
    } catch { /* non-fatal */ }
  }

  // Save = create on first use (version 1), append-a-version on every later save.
  async function save() {
    if (!pid || (items.length === 0 && tests.length === 0)) return;
    setBusy(true);
    try {
      if (rxId == null) {
        const r = await api.post<{ id: number; rx_code: string; version: number }>("/api/prescriptions", payload());
        setRxId(r.id); setRxCode(r.rx_code);
        toast(`Saved ${r.rx_code} (version ${r.version})`);
        await refreshVersions(r.id);
      } else {
        const r = await api.put<{ rx_code: string; version: number; previous_versions_preserved: number }>(`/api/prescriptions/${rxId}`, payload());
        toast(`Saved as version ${r.version} — ${r.previous_versions_preserved} earlier version(s) kept`);
        await refreshVersions(rxId);
      }
      loadMine();
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  }

  async function finalize() {
    if (rxId == null) { toast("Save the prescription first"); return; }
    setBusy(true);
    try {
      const r = await api.post<{ rx_code: string; version: number }>(`/api/prescriptions/${rxId}/finalize`);
      setStatus("finalized");
      toast(`Sealed ${r.rx_code} as version ${r.version} — no QR yet (added when printed)`);
      await refreshVersions(rxId);
      loadMine();
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  }

  async function openExisting(id: number) {
    setBusy(true);
    try {
      const d = await api.get<any>(`/api/prescriptions/${id}`);
      setRxId(d.id); setRxCode(d.rx_code); setStatus(d.status);
      setDiagnosis(d.diagnosis || ""); setComplaints(d.chief_complaints || ""); setAdvice(d.advice || "");
      if (d.patient?.id) setPid(d.patient.id);
      setItems((d.items || []).map((it: any) => {
        const dose = it.dose || {};
        const dur = dose.duration || {};
        return {
          brand_id: it.brand_id ?? null, name: it.name || "", strength: it.strength || "", form: it.form || "",
          slots: dose.slots || {}, meal: dose.meal || "after",
          duration: dur.value ?? null, kind: dur.kind || (dur.value ? "course" : "continue"),
        };
      }));
      setTests((d.tests || []).map((t: any) => ({ test_id: t.test_id ?? null, name: t.name || "", note: t.note || "" })));
      await refreshVersions(id);
      toast(`Opened ${d.rx_code} (version ${d.versions_count})`);
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  }

  // Print WITH the QR. The endpoint is authenticated, so the token is sent as a
  // header via fetch rather than opening the URL directly.
  async function print() {
    if (rxId == null) { toast("Save the prescription first"); return; }
    setBusy(true);
    try {
      const res = await fetch(`/api/prescriptions/${rxId}/print`, { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!res.ok) throw new Error(`Print failed (${res.status})`);
      const html = await res.text();
      const w = window.open("", "_blank");
      if (!w) { toast("Allow pop-ups to print"); return; }
      w.document.open(); w.document.write(html); w.document.close();
      setTimeout(() => { try { w.focus(); w.print(); } catch { /* the user can print manually */ } }, 400);
    } catch (e: any) { toast(e.message); } finally { setBusy(false); }
  }

  function reset() {
    setRxId(null); setRxCode(""); setStatus("draft"); setItems([]); setTests([]);
    setDiagnosis(""); setComplaints(""); setAdvice(""); setWarnings([]); setAcks({}); setVersions([]);
  }

  if (booting) return <div className="container"><Loading /></div>;

  return (
    <div className="container">
      {toastNode}
      <div className="row-between wrap" style={{ gap: 10 }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>Write a prescription</h1>
          <p className="muted" style={{ margin: 0 }}>
            The sheet on the right updates as you type. Save → seal → print (the QR is added at print time).
          </p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          {rxCode && <Badge tone={status === "finalized" ? "ok" : ""}>{rxCode} · {status}</Badge>}
          <button className="btn btn-ghost btn-sm" onClick={reset} disabled={busy}>New</button>
        </div>
      </div>

      <div className="grid grid-2" style={{ alignItems: "start", marginTop: 14 }}>
        {/* ------------------------------------------------ editor */}
        <div className="col" style={{ gap: 14 }}>
          <div className="glass card">
            <label className="field"><span>Patient</span>
              <select className="input" value={pid ?? ""} onChange={(e) => setPid(Number(e.target.value))}>
                {patients.length === 0 && <option value="">No patients linked</option>}
                {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.patient_code})</option>)}
              </select>
            </label>
            <div className="grid grid-2" style={{ gap: 10, marginTop: 10 }}>
              <label className="field"><span>Chief complaints</span>
                <input className="input" value={complaints} onChange={(e) => setComplaints(e.target.value)} placeholder="Sore throat, fever 2 days" />
              </label>
              <label className="field"><span>Diagnosis</span>
                <input className="input" value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} placeholder="Acute pharyngitis" />
              </label>
            </div>
            <label className="field" style={{ marginTop: 10 }}><span>Advice</span>
              <textarea className="input" rows={2} value={advice} onChange={(e) => setAdvice(e.target.value)} placeholder="Rest, fluids, review in 5 days…" />
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
                <button className="btn btn-sm btn-ghost" onClick={() => rm(i)} aria-label="Remove"><IconTrash size={15} /></button>
              </div>
              <div className="row wrap" style={{ gap: 10, marginTop: 10 }}>
                {SLOTS.map((s) => (
                  <label key={s} className="field" style={{ width: 84 }}>
                    <span style={{ textTransform: "capitalize" }}>{s}</span>
                    <input className="input" type="number" step="0.5" min="0" value={it.slots[s] ?? 0}
                           onChange={(e) => setSlot(i, s, Number(e.target.value))} />
                  </label>
                ))}
                <label className="field" style={{ width: 130 }}><span>Meal</span>
                  <select className="input" value={it.meal} onChange={(e) => upd(i, { meal: e.target.value })}>
                    {Object.entries(MEALS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </label>
                <label className="field" style={{ width: 118 }}><span>Duration</span>
                  <select className="input" value={it.kind} onChange={(e) => upd(i, { kind: e.target.value })}>
                    <option value="course">Fixed days</option><option value="continue">Continue</option><option value="as_needed">As needed</option>
                  </select>
                </label>
                {it.kind === "course" && (
                  <label className="field" style={{ width: 90 }}><span>Days</span>
                    <input className="input" type="number" min="1" value={it.duration ?? 7} onChange={(e) => upd(i, { duration: Number(e.target.value) })} />
                  </label>
                )}
              </div>
            </div>
          ))}

          {/* ---- prescribe tests (the previously missing capability) */}
          <div className="glass card">
            <div className="row-between">
              <h3 style={{ margin: 0 }}><IconFile size={18} /> Investigations</h3>
              <button className="btn btn-sm" onClick={addTestRow}><IconPlus size={14} /> Add test</button>
            </div>
            {tests.length === 0 && <div className="muted small" style={{ marginTop: 8 }}>No tests requested yet.</div>}
            {tests.map((t, i) => (
              <div key={i} className="row wrap" style={{ gap: 8, marginTop: 10, alignItems: "flex-end" }}>
                <label className="field" style={{ flex: "1 1 190px" }}><span>Test</span>
                  <TestPicker value={t.name} onPick={(id, name) => id ? pickTest(i, id) : updTest(i, { name })}
                              onType={(name) => updTest(i, { test_id: null, name })} />
                </label>
                <label className="field" style={{ flex: "1 1 160px" }}><span>Note</span>
                  <input className="input" value={t.note} onChange={(e) => updTest(i, { note: e.target.value })} placeholder="e.g. fasting" />
                </label>
                <button className="btn btn-sm btn-ghost" onClick={() => rmTest(i)} aria-label="Remove test"><IconTrash size={15} /></button>
              </div>
            ))}
          </div>

          <div className="row wrap" style={{ gap: 10 }}>
            <button className="btn" onClick={check} disabled={busy || items.length === 0}><IconShield size={16} /> Safety check</button>
            <button className="btn btn-primary" onClick={save} disabled={busy || (!items.length && !tests.length)}>
              {rxId == null ? "Save prescription" : "Save again (new version)"}
            </button>
            <button className="btn" onClick={finalize} disabled={busy || rxId == null}><IconCheck size={16} /> Finalize &amp; seal</button>
            <button className="btn" onClick={print} disabled={busy || rxId == null}><IconPrinter size={16} /> Print (with QR)</button>
          </div>

          {/* ---- reopen a saved prescription to edit it later */}
          <div className="glass card">
            <h3 style={{ marginTop: 0 }}>My prescriptions</h3>
            {mine.length === 0 && <div className="muted small">Nothing saved yet.</div>}
            {mine.map((m) => (
              <div key={m.id} className="row-between" style={{ padding: "7px 0", borderBottom: "1px solid var(--line)" }}>
                <div>
                  <div className="small"><b>{m.rx_code}</b> · {m.patient_name || "—"}</div>
                  <div className="tiny muted">{(m.issued_at || "").slice(0, 10)} · {m.status} · {m.versions} version{m.versions === 1 ? "" : "s"}</div>
                </div>
                <button className="btn btn-sm" onClick={() => openExisting(m.id)} disabled={busy}>Open</button>
              </div>
            ))}
          </div>
        </div>

        {/* ------------------------------------------------ live sheet + side */}
        <div className="col" style={{ gap: 14 }}>
          <LiveSheet patient={patient} doctor={doctor} rxCode={rxCode} diagnosis={diagnosis}
                     complaints={complaints} advice={advice} items={items} tests={tests} />

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

          {versions.length > 0 && (
            <div className="glass card">
              <h3 style={{ marginTop: 0 }}>Version history</h3>
              <div className="tiny muted" style={{ marginBottom: 6 }}>
                Every save appends a version — earlier ones are never overwritten.
              </div>
              {versions.slice().reverse().map((v) => (
                <div key={v.version} className="row-between" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
                  <div>
                    <div className="small"><b>v{v.version}</b> · {v.reason || "saved"}</div>
                    <div className="tiny muted">{(v.created_at || "").slice(0, 19).replace("T", " ")} · {v.item_count} medicine(s) · {v.test_count} test(s)</div>
                  </div>
                  <span className="tiny muted" title={v.content_hash || ""}>{(v.content_hash || "").slice(0, 8)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ test picker */
function TestPicker({ value, onPick, onType }: { value: string; onPick: (id: number | null, name: string) => void; onType: (name: string) => void }) {
  const [q, setQ] = useState(value);
  const [hits, setHits] = useState<{ id: number; name: string; price_min?: number | null }[]>([]);
  const [open, setOpen] = useState(false);
  useEffect(() => { setQ(value); }, [value]);
  useEffect(() => {
    const t = setTimeout(() => {
      if (q.trim().length < 2) { setHits([]); return; }
      api.get<{ results: any[] }>(`/api/tests/search?q=${encodeURIComponent(q.trim())}&limit=6`)
        .then((r) => { setHits((r.results || []).map((x: any) => ({ id: x.id, name: x.name, price_min: x.price_min }))); setOpen(true); })
        .catch(() => setHits([]));
    }, 110);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div style={{ position: "relative" }}>
      <input className="input" value={q} placeholder="Type a test name…"
             onChange={(e) => { setQ(e.target.value); onType(e.target.value); }}
             onFocus={() => hits.length && setOpen(true)}
             onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && hits.length > 0 && (
        <div className="glass search-results" style={{ position: "absolute", zIndex: 20, top: "100%", left: 0, right: 0 }}>
          {hits.map((h) => (
            <div key={h.id} className="search-item" role="button" tabIndex={0}
                 onMouseDown={() => { setQ(h.name); onPick(h.id, h.name); setOpen(false); }}>
              <div className="name">{h.name}</div>
              {h.price_min != null && <div className="meta">from ৳{h.price_min}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ live sheet */
// Mirrors the server-rendered print layout, so what the doctor sees IS what prints.
function LiveSheet({ patient, doctor, rxCode, diagnosis, complaints, advice, items, tests }: {
  patient: P | null; doctor: Doctor; rxCode: string; diagnosis: string; complaints: string; advice: string;
  items: Item[]; tests: TestRow[];
}) {
  const named = tests.filter((t) => t.name.trim());
  return (
    <div className="glass card" style={{ padding: 12 }}>
      <div className="row-between" style={{ marginBottom: 8 }}>
        <div className="tiny muted" style={{ letterSpacing: ".6px", textTransform: "uppercase" }}>Live preview</div>
        <div className="tiny muted">QR appears on print</div>
      </div>
      <div style={{ background: "#fff", color: "#0e1726", borderRadius: 8, padding: "16px 16px 12px", boxShadow: "0 4px 18px rgba(0,0,0,.18)" }}>
        <div style={{ height: 6, borderRadius: 4, background: "linear-gradient(90deg,#0e7c86,#12b3c7 60%,#7fe3d4)" }} />
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 10, paddingBottom: 8, borderBottom: "2px solid #0e1726" }}>
          <div>
            <div style={{ fontSize: 17, fontWeight: 700 }}>{doctor.name || "Doctor name"}</div>
            <div style={{ fontSize: 10.5, color: "#5b6b82", lineHeight: 1.45 }}>
              {doctor.qualifications || "MBBS"}{doctor.designation ? <><br />{doctor.designation}</> : null}
              <br />BMDC Reg. No: {doctor.bmdc_no || "—"}
            </div>
            {doctor.speciality && (
              <span style={{ display: "inline-block", marginTop: 4, fontSize: 10, fontWeight: 700, color: "#fff", background: "#0e7c86", padding: "2px 8px", borderRadius: 999 }}>
                {doctor.speciality}
              </span>
            )}
          </div>
          <div style={{ textAlign: "right", fontSize: 10.5, color: "#5b6b82", maxWidth: "46%" }}>
            <div style={{ fontWeight: 700, color: "#0e1726", fontSize: 12 }}>Attending facility</div>
            <div>BanglaMed</div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 10, fontSize: 11 }}>
          <div style={{ flex: 1, border: "1px solid #c9d4e2", borderRadius: 7, padding: "6px 8px" }}>
            <div style={{ fontSize: 9, color: "#5b6b82", textTransform: "uppercase" }}>Patient</div>
            <b>{patient?.full_name || "—"}</b>
            <div style={{ color: "#5b6b82" }}>{patient?.patient_code || "—"}</div>
          </div>
          <div style={{ flex: 1, border: "1px solid #c9d4e2", borderRadius: 7, padding: "6px 8px" }}>
            <div style={{ fontSize: 9, color: "#5b6b82", textTransform: "uppercase" }}>Sex / DOB</div>
            <b>{patient?.sex || "—"}</b>
            <div style={{ color: "#5b6b82" }}>{patient?.dob || "—"}</div>
          </div>
          <div style={{ flex: 1, border: "1px solid #c9d4e2", borderRadius: 7, padding: "6px 8px" }}>
            <div style={{ fontSize: 9, color: "#5b6b82", textTransform: "uppercase" }}>Rx No.</div>
            <b>{rxCode || "not saved"}</b>
            <div style={{ color: "#5b6b82" }}>{new Date().toISOString().slice(0, 10)}</div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 7, fontSize: 11 }}>
          <div style={{ flex: 1, border: "1px solid #c9d4e2", borderRadius: 7, padding: "6px 8px" }}>
            <div style={{ fontSize: 9, color: "#5b6b82", textTransform: "uppercase" }}>Chief complaints</div>
            <div>{complaints || "—"}</div>
          </div>
          <div style={{ flex: 1, border: "1px solid #c9d4e2", borderRadius: 7, padding: "6px 8px" }}>
            <div style={{ fontSize: 9, color: "#5b6b82", textTransform: "uppercase" }}>Diagnosis</div>
            <div>{diagnosis || "—"}</div>
          </div>
        </div>

        <div style={{ fontSize: 28, fontWeight: 700, fontStyle: "italic", color: "#0e7c86", margin: "12px 0 2px" }}>℞</div>

        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <thead>
            <tr>
              {["#", "Medicine", "Dose", "Duration", "Meal"].map((h) => (
                <th key={h} style={{ textAlign: "left", background: "#f4f8fb", borderBottom: "1.5px solid #c9d4e2", padding: "5px 6px", fontSize: 9.5, textTransform: "uppercase", color: "#5b6b82" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr><td colSpan={5} style={{ padding: "8px 6px", color: "#5b6b82", fontSize: 11 }}>No medicines added yet.</td></tr>
            )}
            {items.map((it, i) => (
              <tr key={i}>
                <td style={{ padding: "6px", borderBottom: "1px solid #e8eef5", color: "#5b6b82" }}>{i + 1}</td>
                <td style={{ padding: "6px", borderBottom: "1px solid #e8eef5" }}>
                  <b>{it.name}</b>
                  <div style={{ color: "#5b6b82", fontSize: 10 }}>{it.strength} · {it.form}</div>
                </td>
                <td style={{ padding: "6px", borderBottom: "1px solid #e8eef5" }}>{slotText(it.slots)}</td>
                <td style={{ padding: "6px", borderBottom: "1px solid #e8eef5" }}>{durText(it)}</td>
                <td style={{ padding: "6px", borderBottom: "1px solid #e8eef5" }}>{MEALS[it.meal] || it.meal}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".6px", color: "#0e7c86", borderBottom: "1px solid #c9d4e2", paddingBottom: 3 }}>
            Investigations requested
          </div>
          {named.length === 0
            ? <div style={{ fontSize: 11, color: "#5b6b82", marginTop: 4 }}>No investigations requested.</div>
            : <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 11 }}>
                {named.map((t, i) => (<li key={i}><b>{t.name}</b>{t.note ? ` — ${t.note}` : ""}</li>))}
              </ul>}
        </div>

        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".6px", color: "#0e7c86", borderBottom: "1px solid #c9d4e2", paddingBottom: 3 }}>Advice</div>
          <div style={{ fontSize: 11, marginTop: 4 }}>{advice || "—"}</div>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 18 }}>
          <div style={{ borderTop: "1.5px solid #0e1726", width: "52%", textAlign: "center", paddingTop: 4, fontSize: 10.5 }}>
            {doctor.name || "Doctor"}
            <div style={{ color: "#5b6b82" }}>Signature &amp; seal</div>
          </div>
          <div style={{ textAlign: "center", border: "1px dashed #c9d4e2", borderRadius: 6, padding: "10px 12px", color: "#5b6b82", fontSize: 9.5 }}>
            ▦ QR on print
            <div>medicine &amp; test prices</div>
          </div>
        </div>
      </div>
    </div>
  );
}
