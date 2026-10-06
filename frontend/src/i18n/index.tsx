import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "en" | "bn";

const STRINGS: Record<string, { en: string; bn: string }> = {
  "nav.medicines": { en: "Medicines", bn: "ঔষধ" },
  "nav.tests": { en: "Tests", bn: "পরীক্ষা" },
  "nav.doctors": { en: "Find a Doctor", bn: "ডাক্তার খুঁজুন" },
  "nav.hospitals": { en: "Hospitals", bn: "হাসপাতাল" },
  "nav.login": { en: "Sign in", bn: "সাইন ইন" },
  "nav.register": { en: "Create account", bn: "অ্যাকাউন্ট খুলুন" },
  "nav.logout": { en: "Sign out", bn: "সাইন আউট" },
  "nav.dashboard": { en: "Dashboard", bn: "ড্যাশবোর্ড" },
  "nav.prescribe": { en: "Prescribe", bn: "প্রেসক্রিপশন" },
  "nav.patients": { en: "My Patients", bn: "আমার রোগী" },
  "nav.history": { en: "My Records", bn: "আমার রেকর্ড" },
  "nav.reminders": { en: "Reminders", bn: "রিমাইন্ডার" },
  "nav.appointments": { en: "Appointments", bn: "অ্যাপয়েন্টমেন্ট" },
  "nav.analytics": { en: "Analytics", bn: "বিশ্লেষণ" },
  "nav.admin": { en: "Admin", bn: "অ্যাডমিন" },
  "home.eyebrow": { en: "Bangladesh Medicine Intelligence", bn: "বাংলাদেশ ঔষধ ইন্টেলিজেন্স" },
  "home.title1": { en: "Every medicine,", bn: "প্রতিটি ঔষধ," },
  "home.title2": { en: "one search away.", bn: "একটি সার্চেই।" },
  "home.lead": {
    en: "Search 25,000+ brands, compare prices, check dosage, find doctors and hospitals — with a prescription engine and medication-safety checks built in.",
    bn: "২৫,০০০+ ব্র্যান্ড খুঁজুন, দাম তুলনা করুন, ডোজ দেখুন, ডাক্তার ও হাসপাতাল খুঁজুন — প্রেসক্রিপশন ইঞ্জিন ও ঔষধ-নিরাপত্তা যাচাই সহ।",
  },
  "home.search": { en: "Search a medicine, generic or company…", bn: "ঔষধ, জেনেরিক বা কোম্পানি খুঁজুন…" },
  "common.loading": { en: "Loading…", bn: "লোড হচ্ছে…" },
  "common.empty": { en: "Nothing here yet", bn: "এখনো কিছু নেই" },
  "common.save": { en: "Save", bn: "সংরক্ষণ" },
  "common.cancel": { en: "Cancel", bn: "বাতিল" },
  "common.search": { en: "Search", bn: "খুঁজুন" },
  "common.disclaimer": {
    en: "Informational only. Not medical advice. Always consult a registered doctor or pharmacist.",
    bn: "শুধুমাত্র তথ্যের জন্য। চিকিৎসা পরামর্শ নয়। সর্বদা নিবন্ধিত ডাক্তার বা ফার্মাসিস্টের পরামর্শ নিন।",
  },
};

interface I18nCtx { lang: Lang; setLang: (l: Lang) => void; t: (k: string) => string; }
const Ctx = createContext<I18nCtx>({ lang: "en", setLang: () => {}, t: (k) => k });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem("bm_lang") as Lang) || "en");
  useEffect(() => {
    localStorage.setItem("bm_lang", lang);
    document.body.setAttribute("data-lang", lang);
    document.documentElement.setAttribute("lang", lang);
  }, [lang]);
  const t = (k: string) => STRINGS[k]?.[lang] ?? k;
  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}
export function useI18n() { return useContext(Ctx); }
