import { Link } from "react-router-dom";
import { useI18n } from "../i18n";
import { MedicineSearch } from "../components/MedicineSearch";
import { Ecg } from "../design-system/UI";
import { IconPill, IconFlask, IconStethoscope, IconHospital, IconShield, IconQr, IconBell, IconChart } from "../design-system/Icons";

const FEATURES = [
  { icon: <IconPill size={22} />, title: "25,000+ brands", text: "Search every brand, generic and company in the Bangladesh market — with prices and pack sizes." },
  { icon: <IconShield size={22} />, title: "Safety checks", text: "Duplicate-ingredient, interaction, allergy and pregnancy flags before a prescription is issued." },
  { icon: <IconQr size={22} />, title: "Signed prescriptions", text: "Every prescription is sealed with a tamper-evident digital signature and a scannable QR." },
  { icon: <IconFlask size={22} />, title: "Tests & prices", text: "Compare diagnostic test prices across hospitals, with fasting and preparation guidance." },
  { icon: <IconStethoscope size={22} />, title: "Find a doctor", text: "Browse doctors by speciality and district, and book a serial in a few taps." },
  { icon: <IconHospital size={22} />, title: "Hospitals", text: "Locate hospitals and clinics near you with contact details and hours." },
  { icon: <IconBell size={22} />, title: "Reminders", text: "Turn any prescription into a medicine schedule you can tick off." },
  { icon: <IconChart size={22} />, title: "Hospital analytics", text: "Prescription trends, top medicines and doctor activity for hospital administrators." },
];

export default function Home() {
  const { t } = useI18n();
  return (
    <div className="container">
      <section className="hero">
        <div className="hero-eyebrow"><span className="pulse-dot" /> {t("home.eyebrow")}</div>
        <h1 className="hero-title">
          {t("home.title1")}<br /><span className="gradient-text">{t("home.title2")}</span>
        </h1>
        <p className="hero-lead">{t("home.lead")}</p>
        <div style={{ maxWidth: 720, margin: "0 auto" }}>
          <MedicineSearch placeholder={t("home.search")} />
        </div>
        <div className="hero-ecg"><Ecg /></div>
        <div className="row" style={{ justifyContent: "center", gap: 12, marginTop: 22, flexWrap: "wrap" }}>
          <Link to="/medicines" className="btn btn-primary">Browse medicines</Link>
          <Link to="/doctors" className="btn">Find a doctor</Link>
          <Link to="/register" className="btn btn-ghost">Create an account</Link>
        </div>
      </section>

      <section className="grid grid-4" style={{ marginTop: 40 }}>
        {FEATURES.map((f) => (
          <div key={f.title} className="glass card feature">
            <div className="feature-icon">{f.icon}</div>
            <h3>{f.title}</h3>
            <p className="muted small">{f.text}</p>
          </div>
        ))}
      </section>

      <section className="glass card" style={{ marginTop: 28, textAlign: "center" }}>
        <h2 style={{ marginTop: 0 }}>Built for Bangladesh</h2>
        <p className="muted" style={{ maxWidth: 720, margin: "0 auto" }}>
          BanglaMed brings the medicine catalog, doctor directory, hospital finder, prescription engine and
          medication-safety checks into one place — with Bangla dosage instructions and BDT pricing.
        </p>
        <div className="row" style={{ justifyContent: "center", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
          <span className="badge">Bangla dosage</span>
          <span className="badge">BDT pricing</span>
          <span className="badge">QR verification</span>
          <span className="badge">Role-based access</span>
          <span className="badge">Audit trail</span>
        </div>
      </section>
    </div>
  );
}
