import { useEffect, useState, type ReactNode } from "react";
import { IconArrowDown, IconArrowUp } from "./Icons";

export function Spinner() { return <span className="spinner" />; }

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="empty">
      <div className="row" style={{ justifyContent: "center", marginBottom: 12 }}><Spinner /></div>
      <div className="muted small">{label}</div>
    </div>
  );
}

export function Empty({ icon, title, hint, action }: { icon?: ReactNode; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      {icon && <div className="empty-icon">{icon}</div>}
      <h3>{title}</h3>
      {hint && <p className="muted small" style={{ maxWidth: 420, margin: "0 auto 16px" }}>{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="empty">
      <div className="empty-icon">⚠️</div>
      <h3>Something went wrong</h3>
      <p className="muted small">{message}</p>
      {onRetry && <button className="btn btn-sm" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="glass stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="tiny muted" style={{ marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

export function Badge({ children, tone = "" }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone ? "badge-" + tone : ""}`}>{children}</span>;
}

export function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => { const t = setTimeout(onDone, 3200); return () => clearTimeout(t); }, [onDone]);
  return <div className="toast">{message}</div>;
}

export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const node = msg ? <Toast message={msg} onDone={() => setMsg(null)} /> : null;
  return { toast: setMsg, toastNode: node };
}

export function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="glass card modal" onClick={(e) => e.stopPropagation()}>
        <div className="row-between" style={{ marginBottom: 14 }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button className="btn btn-sm btn-ghost" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

// Single scroll button: scrolls to bottom, then flips to scroll-to-top.
export function ScrollButton() {
  const [atBottom, setAtBottom] = useState(false);
  useEffect(() => {
    function onScroll() {
      const scrolled = window.scrollY + window.innerHeight;
      setAtBottom(scrolled >= document.body.scrollHeight - 80);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  function go() {
    if (atBottom) window.scrollTo({ top: 0, behavior: "smooth" });
    else window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }
  return (
    <button className="scroll-btn" onClick={go} title={atBottom ? "Back to top" : "Scroll to bottom"} aria-label={atBottom ? "Back to top" : "Scroll to bottom"}>
      {atBottom ? <IconArrowUp size={20} /> : <IconArrowDown size={20} />}
    </button>
  );
}

export function Ecg() {
  return (
    <svg className="ecg" viewBox="0 0 300 40" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 20 H40 L48 20 L54 6 L60 34 L66 20 H110 L118 20 L124 8 L130 32 L136 20 H190 L198 20 L204 6 L210 34 L216 20 H300" />
    </svg>
  );
}
