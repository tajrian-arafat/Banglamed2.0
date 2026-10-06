import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth, type Role } from "./core/auth";
import { Layout } from "./components/Layout";
import { Loading } from "./design-system/UI";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Medicines from "./pages/Medicines";
import MedicineDetail from "./pages/MedicineDetail";
import Tests from "./pages/Tests";
import TestDetail from "./pages/TestDetail";
import Doctors from "./pages/Doctors";
import DoctorDetail from "./pages/DoctorDetail";
import Hospitals from "./pages/Hospitals";
import HospitalDetail from "./pages/HospitalDetail";
import RxPublic from "./pages/RxPublic";
import PatientDashboard from "./pages/patient/Dashboard";
import PatientHistory from "./pages/patient/History";
import PatientUpload from "./pages/patient/Upload";
import PatientReminders from "./pages/patient/Reminders";
import PatientAppointments from "./pages/patient/Appointments";
import PatientProfile from "./pages/patient/Profile";
import DoctorDashboard from "./pages/doctor/Dashboard";
import DoctorPrescribe from "./pages/doctor/Prescribe";
import DoctorPatients from "./pages/doctor/Patients";
import DoctorSchedule from "./pages/doctor/Schedule";
import DoctorProfile from "./pages/doctor/Profile";
import HospitalAnalytics from "./pages/hospital/Analytics";
import HospitalDoctors from "./pages/hospital/Doctors";
import AdminPanel from "./pages/admin/Admin";
import NotFound from "./pages/NotFound";

function Guard({ roles, children }: { roles: Role[]; children: JSX.Element }) {
  const { me, loading } = useAuth();
  if (loading) return <Loading />;
  if (!me) return <Navigate to="/login" replace />;
  if (!roles.includes(me.role)) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/medicines" element={<Medicines />} />
        <Route path="/medicines/q/:q" element={<Medicines />} />
        <Route path="/medicines/:id" element={<MedicineDetail />} />
        <Route path="/tests" element={<Tests />} />
        <Route path="/tests/:id" element={<TestDetail />} />
        <Route path="/doctors" element={<Doctors />} />
        <Route path="/doctors/:id" element={<DoctorDetail />} />
        <Route path="/hospitals" element={<Hospitals />} />
        <Route path="/hospitals/:id" element={<HospitalDetail />} />
        <Route path="/rx/:token" element={<RxPublic />} />

        <Route path="/patient" element={<Guard roles={["patient"]}><PatientDashboard /></Guard>} />
        <Route path="/patient/history" element={<Guard roles={["patient"]}><PatientHistory /></Guard>} />
        <Route path="/patient/upload" element={<Guard roles={["patient"]}><PatientUpload /></Guard>} />
        <Route path="/patient/reminders" element={<Guard roles={["patient"]}><PatientReminders /></Guard>} />
        <Route path="/patient/appointments" element={<Guard roles={["patient"]}><PatientAppointments /></Guard>} />
        <Route path="/patient/profile" element={<Guard roles={["patient"]}><PatientProfile /></Guard>} />

        <Route path="/doctor" element={<Guard roles={["doctor"]}><DoctorDashboard /></Guard>} />
        <Route path="/doctor/prescribe" element={<Guard roles={["doctor"]}><DoctorPrescribe /></Guard>} />
        <Route path="/doctor/patients" element={<Guard roles={["doctor"]}><DoctorPatients /></Guard>} />
        <Route path="/doctor/schedule" element={<Guard roles={["doctor"]}><DoctorSchedule /></Guard>} />
        <Route path="/doctor/profile" element={<Guard roles={["doctor"]}><DoctorProfile /></Guard>} />

        <Route path="/hospital/analytics" element={<Guard roles={["hospital_admin", "system_admin"]}><HospitalAnalytics /></Guard>} />
        <Route path="/hospital/doctors" element={<Guard roles={["hospital_admin", "system_admin"]}><HospitalDoctors /></Guard>} />
        <Route path="/admin" element={<Guard roles={["system_admin"]}><AdminPanel /></Guard>} />

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
