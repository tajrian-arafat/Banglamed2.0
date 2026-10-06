export function bdt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return "৳" + v.toLocaleString("en-BD", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
export function num(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("en-US");
}
export function dateStr(s: string | null | undefined): string {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return s; }
}
export function timeStr(s: string | null | undefined): string {
  if (!s) return "—";
  try { return new Date(s).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); }
  catch { return s; }
}
