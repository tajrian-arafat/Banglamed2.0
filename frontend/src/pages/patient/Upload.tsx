import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../core/api";
import { bdt } from "../../core/format";
import { Loading, Badge } from "../../design-system/UI";
import { MedicineSearch } from "../../components/MedicineSearch";
import {
  IconUpload, IconAlert, IconPlus, IconTrash, IconShield, IconCheck, IconFile,
} from "../../design-system/Icons";

interface P { id: number; full_name: string; patient_code: string; }
interface Quality {
  ok?: boolean; issues?: string[]; notes?: string[]; width?: number; height?: number;
  brightness?: number; sharpness?: number; note?: string;
}
interface MedRow {
  brand_id: number | null; name: string; generic?: string | null; company?: string | null;
  strength?: string | null; form?: string | null; unit_price?: number | null;
  doses_per_day?: number; duration_days?: number | null;
  windows?: Record<string, number | null>; full_course?: number | null; priced?: boolean;
}
interface TestRow {
  test_id: number | null; name: string; price_min?: number | null; price_max?: number | null;
  sample_type?: string | null; fasting_required?: boolean; priced?: boolean;
}
interface Guard { code: string; severity: string; message: string; medicines_involved?: string[]; }
interface SideEffect { brand_id: number; name: string; generic?: string | null; side_effects?: string | null; contraindications?: string | null; }
interface Interaction { a: string; b: string; a_generic?: string | null; b_generic?: string | null; note: string; }
interface Analysis {
  medicines: MedRow[]; tests: TestRow[];
  totals: {
    windows: Record<string, number>; window_labels: Record<string, string>;
    full_course: number | null; full_course_complete: boolean;
    tests_total: number; grand_total_full_course: number | null; currency: string;
  };
  safety: {
    guards: Guard[]; guard_count: number; side_effects: SideEffect[];
    interactions: Interaction[]; interaction_count: number; checked: boolean;
  };
  disclaimer?: string;
}
interface Parsed {
  mode?: string; provider?: string; message?: string;
  medicines?: { brand_id: number; brand: string; generic?: string; strength?: string; form?: string; dose?: any; duration?: any }[];
  tests?: { test_id: number; name: string; price_min?: number | null }[];
}

const WINDOW_ORDER = ["5d", "7d", "15d", "30d"];

export default function PatientUpload() {
  const [patients, setPatients] = useState<P[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [err, setErr] = useState("");
  const [caps, setCaps] = useState<{ auto_read_enabled?: boolean; ocr_provider?: string } | null>(null);

  // Manual-entry state — the fallback path, always available.
  const [manualMeds, setManualMeds] = useState<{ brand_id: number | null; name: string; days: number }[]>([]);
  const [manualTests, setManualTests] = useState<{ test_id: number | null; name: string }[]>([]);

  useEffect(() => {
    api.get<{ results: P[] }>("/api/patients").then((r) => {
      setPatients(r.results);
      if (r.results[0]) setPid(r.results[0].id);
    }).catch(() => {});
    api.get<{ auto_read_enabled?: boolean; ocr_provider?: string }>("/api/interpreter/capabilities")
      .then(setCaps).catch(() => {});
  }, []);

  const runAnalyze = useCallback(async (
    meds: { brand_id: number | null; name?: string; dose?: any; duration_days?: number | null }[],
    tests: { test_id: number | null; name?: string }[],
  ) => {
    if (!meds.length && !tests.length) { setAnalysis(null); return; }
    try {
      const r = await api.post<Analysis>("/api/interpreter/analyze", {
        patient_id: pid, medicines: meds, tests,
      });
      setAnalysis(r);
    } catch (e: any) { setErr(e.message); }
  }, [pid]);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f || !pid) return;
    setBusy(true); setErr(""); setQuality(null); setParsed(null); setAnalysis(null);
    try {
      const r = await api.upload<{ quality: Quality; parsed: Parsed; analysis: Analysis }>(
        `/api/records/${pid}/upload`, f,
      );
      setQuality(r.quality); setParsed(r.parsed); setAnalysis(r.analysis);
      // Seed the manual form from whatever was read, so the patient can correct
      // a mis-read row instead of retyping everything.
      setManualMeds((r.parsed.medicines || []).map((m) => ({
        brand_id: m.brand_id, name: m.brand, days: m.duration?.value || 7,
      })));
      setManualTests((r.parsed.tests || []).map((t) => ({ test_id: t.test_id, name: t.name })));
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  function addMed() { setManualMeds((p) => [...p, { brand_id: null, name: "", days: 7 }]); }
  function updMed(i: number, patch: Partial<{ brand_id: number | null; name: string; days: number }>) {
    setManualMeds((p) => p.map((m, idx) => (idx === i ? { ...m, ...patch } : m)));
  }
  function rmMed(i: number) { setManualMeds((p) => p.filter((_, idx) => idx !== i)); }
  function addTest() { setManualTests((p) => [...p, { test_id: null, name: "" }]); }
  function updTest(i: number, patch: Partial<{ test_id: number | null; name: string }>) {
    setManualTests((p) => p.map((t, idx) => (idx === i ? { ...t, ...patch } : t)));
  }
  function rmTest(i: number) { setManualTests((p) => p.filter((_, idx) => idx !== i)); }

  function recalc() {
    runAnalyze(
      manualMeds.filter((m) => m.brand_id || m.name.trim()).map((m) => ({
        brand_id: m.brand_id, name: m.name || undefined, duration_days: m.days,
      })),
      manualTests.filter((t) => t.test_id || t.name.trim()).map((t) => ({
        test_id: t.test_id, name: t.name || undefined,
      })),
    );
  }

  const totals = analysis?.totals;
  const safety = analysis?.safety;
  const readFailed = parsed && (parsed.mode === "typed_fallback" || parsed.mode === "ocr_no_match");
  const hasManual = manualMeds.length > 0 || manualTests.length > 0;

  const windowRows = useMemo(() => {
    if (!totals) return [];
    return WINDOW_ORDER.map((k) => ({ key: k, label: totals.window_labels[k] || k, value: totals.windows[k] ?? 0 }));
  }, [totals]);

  return (
    <div className="container">
      <h1>Upload a prescription</h1>
      <p className="muted">
        Snap or upload a photo of a paper prescription. We read the medicines and tests,
        price them, and check them for safety. If the photo cannot be read, type them in below.
      </p>

      {patients.length > 1 && (
        <select className="input" style={{ maxWidth: 320, marginBottom: 16 }} value={pid ?? ""}
                onChange={(e) => setPid(Number(e.target.value))}>
          {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
        </select>
      )}

      <div className="grid grid-2" style={{ alignItems: "start", gap: 16 }}>
        {/* ------------------------------------------------ left: upload + entry */}
        <div className="col" style={{ gap: 14 }}>
          <label className="glass card dropzone">
            <IconUpload size={30} />
            <div className="name">{busy ? "Reading…" : "Choose an image"}</div>
            <div className="tiny muted">PNG or JPEG, up to 8 MB</div>
            <input type="file" accept="image/*" onChange={onFile} hidden disabled={busy} />
          </label>

          {caps && !caps.auto_read_enabled && (
            <div className="alert alert-note">
              <div className="row" style={{ gap: 8 }}>
                <IconAlert size={16} />
                <span className="small">Automatic reading is unavailable right now — use the manual entry below.</span>
              </div>
            </div>
          )}

          {busy && <Loading label="Reading your prescription…" />}
          {err && <div className="alert alert-error">{err}</div>}

          {quality && (
            <div className="glass card">
              <h3 style={{ marginTop: 0 }}>Image quality</h3>
              <div className="row wrap" style={{ gap: 8 }}>
                <Badge tone={quality.ok ? "ok" : "warn"}>{quality.ok ? "Good" : "Needs attention"}</Badge>
                {quality.width && <span className="badge">{quality.width}×{quality.height}</span>}
                {quality.brightness != null && <span className="badge">brightness {quality.brightness}</span>}
                {quality.sharpness != null && <span className="badge">sharpness {quality.sharpness}</span>}
              </div>
              {quality.issues && quality.issues.length > 0 && (
                <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
                  {quality.issues.map((i) => <span key={i} className="badge badge-warn">{i.replace(/_/g, " ")}</span>)}
                </div>
              )}
              {quality.notes && quality.notes.length > 0 && (
                <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
                  {quality.notes.map((i) => <span key={i} className="badge">{i.replace(/_/g, " ")}</span>)}
                </div>
              )}
            </div>
          )}

          {parsed && (
            <div className="glass card">
              <h3 style={{ marginTop: 0 }}>Reading result</h3>
              {readFailed ? (
                <div className="row" style={{ gap: 8 }}>
                  <IconAlert size={16} />
                  <span className="small">{parsed.message}</span>
                </div>
              ) : (
                <>
                  <div className="row wrap" style={{ gap: 8, marginBottom: 8 }}>
                    <Badge tone="ok"><IconCheck size={13} /> Read automatically</Badge>
                    {parsed.provider && <span className="badge">{parsed.provider}</span>}
                    <span className="badge">{(parsed.medicines || []).length} medicine(s)</span>
                    <span className="badge">{(parsed.tests || []).length} test(s)</span>
                  </div>
                  {(parsed.medicines || []).length === 0 && (parsed.tests || []).length === 0 && (
                    <div className="muted small">Nothing could be matched — type it in below.</div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ---- manual entry: medicines */}
          <div className="glass card card-search">
            <div className="row-between">
              <h3 style={{ margin: 0 }}><IconPlus size={18} /> Medicines</h3>
              <button className="btn btn-sm" onClick={addMed}><IconPlus size={14} /> Add medicine</button>
            </div>
            <div className="tiny muted" style={{ marginTop: 4 }}>
              Read automatically, or type a name and pick from the catalog.
            </div>
            {manualMeds.length === 0 && <div className="muted small" style={{ marginTop: 8 }}>No medicines yet.</div>}
            {manualMeds.map((m, i) => (
              <div key={i} className="row wrap" style={{ gap: 8, marginTop: 10, alignItems: "flex-end" }}>
                <label className="field" style={{ flex: "1 1 220px" }}>
                  <span>Medicine</span>
                  {m.brand_id ? (
                    <div className="row-between" style={{ gap: 8 }}>
                      <span className="small"><b>{m.name}</b></span>
                      <button className="btn btn-sm btn-ghost" onClick={() => updMed(i, { brand_id: null, name: "" })}>Change</button>
                    </div>
                  ) : (
                    <MedicineSearch
                      placeholder="Type a medicine name…"
                      onPick={(id) => {
                        api.get<any>(`/api/medicines/${id}`).then((d) => {
                          updMed(i, { brand_id: id, name: d.brand.name });
                        }).catch(() => {});
                      }}
                    />
                  )}
                </label>
                <label className="field" style={{ width: 96 }}>
                  <span>Days</span>
                  <input className="input" type="number" min={1} value={m.days}
                         onChange={(e) => updMed(i, { days: Number(e.target.value) })} />
                </label>
                <button className="btn btn-sm btn-ghost" onClick={() => rmMed(i)} aria-label="Remove"><IconTrash size={15} /></button>
              </div>
            ))}
          </div>

          {/* ---- manual entry: tests */}
          <div className="glass card">
            <div className="row-between">
              <h3 style={{ margin: 0 }}><IconFile size={18} /> Tests</h3>
              <button className="btn btn-sm" onClick={addTest}><IconPlus size={14} /> Add test</button>
            </div>
            {manualTests.length === 0 && <div className="muted small" style={{ marginTop: 8 }}>No tests yet.</div>}
            {manualTests.map((t, i) => (
              <div key={i} className="row wrap" style={{ gap: 8, marginTop: 10, alignItems: "flex-end" }}>
                <label className="field" style={{ flex: "1 1 220px" }}>
                  <span>Test</span>
                  <TestPicker value={t.name} onPick={(id, name) => updTest(i, { test_id: id, name })}
                              onType={(name) => updTest(i, { test_id: null, name })} />
                </label>
                <button className="btn btn-sm btn-ghost" onClick={() => rmTest(i)} aria-label="Remove"><IconTrash size={15} /></button>
              </div>
            ))}
          </div>

          <div className="row wrap" style={{ gap: 10 }}>
            <button className="btn btn-primary" onClick={recalc} disabled={busy || !hasManual}>
              <IconCheck size={16} /> Price &amp; check safety
            </button>
          </div>
        </div>

        {/* ------------------------------------------------ right: totals + safety */}
        <div className="col" style={{ gap: 14 }}>
          {totals && (
            <div className="glass card">
              <h3 style={{ marginTop: 0 }}>Estimated cost</h3>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr><th>Timeframe</th><th style={{ textAlign: "right" }}>Medicines</th></tr>
                  </thead>
                  <tbody>
                    {windowRows.map((w) => (
                      <tr key={w.key}>
                        <td>{w.label}</td>
                        <td style={{ textAlign: "right" }}>{bdt(w.value)}</td>
                      </tr>
                    ))}
                    <tr>
                      <td><b>Full course</b></td>
                      <td style={{ textAlign: "right" }}>
                        <b>{totals.full_course != null ? bdt(totals.full_course) : "—"}</b>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              {!totals.full_course_complete && (
                <div className="tiny muted" style={{ marginTop: 6 }}>
                  Full course needs a duration for every medicine.
                </div>
              )}
              <div className="row-between" style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--line)" }}>
                <span className="small">Tests</span>
                <b>{bdt(totals.tests_total)}</b>
              </div>
              {totals.grand_total_full_course != null && (
                <div className="row-between" style={{ marginTop: 6 }}>
                  <span className="small">Medicines + tests (full course)</span>
                  <b className="accent">{bdt(totals.grand_total_full_course)}</b>
                </div>
              )}
            </div>
          )}

          {/* ---- Safety panel: always present, all guards + side effects + interactions */}
          <div className="glass card">
            <h3 style={{ marginTop: 0 }}><IconShield size={18} /> Safety</h3>
            {!safety || !safety.checked ? (
              <div className="muted small">
                Add medicines and press “Price &amp; check safety” to see every guard, the side
                effects of each medicine, and any interactions between them.
              </div>
            ) : (
              <>
                <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
                  <Badge tone={safety.guard_count ? "warn" : "ok"}>
                    {safety.guard_count} guard{safety.guard_count === 1 ? "" : "s"}
                  </Badge>
                  <span className="badge">{safety.interaction_count} interaction(s)</span>
                  <span className="badge">{safety.side_effects.length} medicine profile(s)</span>
                </div>

                {safety.guards.length === 0 && (
                  <div className="alert alert-note" style={{ marginBottom: 10 }}>
                    <div className="row" style={{ gap: 6 }}><IconCheck size={15} /><span className="small">No safety guards triggered.</span></div>
                  </div>
                )}
                {safety.guards.map((w, i) => (
                  <div key={i} className={`alert ${w.severity === "critical" ? "alert-error" : "alert-note"}`} style={{ marginBottom: 8 }}>
                    <div className="row-between">
                      <div className="row" style={{ gap: 6 }}>
                        <IconAlert size={15} /><strong className="small">{w.code.replace(/_/g, " ")}</strong>
                      </div>
                      <Badge tone={w.severity === "critical" ? "warn" : ""}>{w.severity}</Badge>
                    </div>
                    <div className="tiny" style={{ marginTop: 4 }}>{w.message}</div>
                  </div>
                ))}

                {safety.interactions.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <div className="tiny muted" style={{ textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>
                      Interactions between prescribed medicines
                    </div>
                    {safety.interactions.map((x, i) => (
                      <div key={i} className="alert alert-note" style={{ marginBottom: 8 }}>
                        <div className="small"><b>{x.a}</b> + <b>{x.b}</b></div>
                        <div className="tiny" style={{ marginTop: 4 }}>{x.note}</div>
                      </div>
                    ))}
                  </div>
                )}

                <div style={{ marginTop: 12 }}>
                  <div className="tiny muted" style={{ textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>
                    Side effects &amp; contraindications
                  </div>
                  {safety.side_effects.map((s) => (
                    <div key={s.brand_id} style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
                      <div className="small"><b>{s.name}</b>{s.generic ? <span className="muted"> · {s.generic}</span> : null}</div>
                      <div className="tiny" style={{ marginTop: 4 }}>
                        <b>Side effects:</b> {s.side_effects || "Not recorded in the catalog."}
                      </div>
                      <div className="tiny" style={{ marginTop: 2 }}>
                        <b>Contraindications:</b> {s.contraindications || "Not recorded in the catalog."}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {analysis?.disclaimer && <div className="tiny muted">{analysis.disclaimer}</div>}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ test picker */
function TestPicker({ value, onPick, onType }: {
  value: string; onPick: (id: number, name: string) => void; onType: (name: string) => void;
}) {
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
        <div className="glass search-results" style={{ position: "absolute", zIndex: 60, top: "100%", left: 0, right: 0 }}>
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
