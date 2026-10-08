import { useEffect, useState } from "react";
import { api } from "../../core/api";
import { Loading, Badge } from "../../design-system/UI";
import { IconUpload, IconAlert } from "../../design-system/Icons";

interface P { id: number; full_name: string; patient_code: string; }
interface Quality { ok?: boolean; issues?: string[]; width?: number; height?: number; brightness?: number; sharpness?: number; note?: string; }
interface Parsed { mode?: string; message?: string; candidates?: { raw: string; matches: { brand: string; score: number }[] }[]; }

export default function PatientUpload() {
  const [patients, setPatients] = useState<P[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get<{ results: P[] }>("/api/patients").then((r) => { setPatients(r.results); if (r.results[0]) setPid(r.results[0].id); });
  }, []);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f || !pid) return;
    setBusy(true); setErr(""); setQuality(null); setParsed(null);
    try {
      const r = await api.upload<{ quality: Quality; parsed: Parsed }>(`/api/records/${pid}/upload`, f);
      setQuality(r.quality); setParsed(r.parsed);
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="container narrow">
      <h1>Upload a prescription</h1>
      <p className="muted">Snap or upload a photo of a paper prescription. We check the image quality and try to read the medicines.</p>
      {patients.length > 1 && (
        <select className="input" style={{ maxWidth: 320, marginBottom: 16 }} value={pid ?? ""} onChange={(e) => setPid(Number(e.target.value))}>
          {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
        </select>
      )}
      <label className="glass card dropzone">
        <IconUpload size={30} />
        <div className="name">{busy ? "Processing…" : "Choose an image"}</div>
        <div className="tiny muted">PNG or JPEG, up to 8 MB</div>
        <input type="file" accept="image/*" onChange={onFile} hidden disabled={busy} />
      </label>
      {busy && <Loading label="Reading your prescription…" />}
      {err && <div className="alert alert-error" style={{ marginTop: 14 }}>{err}</div>}
      {quality && (
        <div className="glass card" style={{ marginTop: 14 }}>
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
          {quality.note && <p className="tiny muted">{quality.note}</p>}
        </div>
      )}
      {parsed && (
        <div className="glass card" style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>Reading result</h3>
          {parsed.mode === "typed_fallback" ? (
            <div className="row" style={{ gap: 8 }}><IconAlert size={16} /><span className="small">{parsed.message}</span></div>
          ) : (
            <>
              {(parsed.candidates || []).length === 0 && <div className="muted small">No medicines could be read automatically.</div>}
              {(parsed.candidates || []).map((c, i) => (
                <div key={i} className="list-row">
                  <div><div className="name">{c.raw}</div><div className="tiny muted">{c.matches.map((m) => m.brand).join(", ")}</div></div>
                  <span className="badge badge-accent">{Math.round((c.matches[0]?.score || 0) * 100)}%</span>
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
