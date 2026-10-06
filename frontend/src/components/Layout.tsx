import { Link, NavLink, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../core/auth";
import { useTheme } from "../core/theme";
import { useI18n } from "../i18n";
import { Background } from "../design-system/Background";
import { ScrollButton } from "../design-system/UI";
import { IconGlobe, IconLogout, IconMoon, IconSun } from "../design-system/Icons";

const PUBLIC_LINKS = [
  { to: "/medicines", key: "nav.medicines" },
  { to: "/tests", key: "nav.tests" },
  { to: "/doctors", key: "nav.doctors" },
  { to: "/hospitals", key: "nav.hospitals" },
];

function roleLinks(role: string) {
  if (role === "patient") return [
    { to: "/patient", key: "nav.dashboard" },
    { to: "/patient/history", key: "nav.history" },
    { to: "/patient/reminders", key: "nav.reminders" },
    { to: "/patient/appointments", key: "nav.appointments" },
  ];
  if (role === "doctor") return [
    { to: "/doctor", key: "nav.dashboard" },
    { to: "/doctor/prescribe", key: "nav.prescribe" },
    { to: "/doctor/patients", key: "nav.patients" },
    { to: "/doctor/schedule", key: "nav.appointments" },
  ];
  if (role === "hospital_admin") return [
    { to: "/hospital/analytics", key: "nav.analytics" },
    { to: "/hospital/doctors", key: "nav.doctors" },
  ];
  if (role === "system_admin") return [
    { to: "/admin", key: "nav.admin" },
    { to: "/hospital/analytics", key: "nav.analytics" },
  ];
  return [];
}

export function Layout({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const { lang, setLang, t } = useI18n();
  const nav = useNavigate();
  const links = me ? roleLinks(me.role) : [];

  return (
    <>
      <Background />
      <div className="bg-aurora" aria-hidden="true" />
      <div className="app-shell">
        <nav className="nav">
          <div className="container nav-inner">
            <Link to="/" className="brand">
              <span className="brand-mark">B</span>
              <span>Bangla<span className="gradient-text">Med</span></span>
            </Link>
            <div className="nav-links">
              {PUBLIC_LINKS.map((l) => (
                <NavLink key={l.to} to={l.to} className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}>
                  {t(l.key)}
                </NavLink>
              ))}
              {links.map((l) => (
                <NavLink key={l.to} to={l.to} end className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}>
                  {t(l.key)}
                </NavLink>
              ))}
            </div>
            <div className="spacer" />
            <button className="btn btn-icon btn-ghost" onClick={() => setLang(lang === "en" ? "bn" : "en")} title="Language">
              <IconGlobe size={17} />
            </button>
            <button className="btn btn-icon btn-ghost" onClick={toggle} title="Theme">
              {theme === "dark" ? <IconSun size={17} /> : <IconMoon size={17} />}
            </button>
            {me ? (
              <div className="row" style={{ gap: 8 }}>
                <span className="badge badge-accent" title={me.full_name}>{me.role.replace("_", " ")}</span>
                <button className="btn btn-sm btn-ghost" onClick={() => { logout(); nav("/"); }} title={t("nav.logout")}>
                  <IconLogout size={15} />
                </button>
              </div>
            ) : (
              <div className="row" style={{ gap: 8 }}>
                <Link to="/login" className="btn btn-sm btn-ghost">{t("nav.login")}</Link>
                <Link to="/register" className="btn btn-sm btn-primary">{t("nav.register")}</Link>
              </div>
            )}
          </div>
        </nav>

        <main className="page">{children}</main>

        <footer className="footer">
          <div className="container row-between wrap">
            <div><strong>BanglaMed 2.0</strong> — {t("common.disclaimer")}</div>
            <div className="row" style={{ gap: 14 }}>
              <Link to="/medicines" className="muted small">{t("nav.medicines")}</Link>
              <Link to="/doctors" className="muted small">{t("nav.doctors")}</Link>
              <Link to="/hospitals" className="muted small">{t("nav.hospitals")}</Link>
            </div>
          </div>
        </footer>
      </div>
      <ScrollButton />
    </>
  );
}
