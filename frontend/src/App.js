import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";

import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Pipeline from "@/pages/Pipeline";
import Quotes from "@/pages/Quotes";
import Invoices from "@/pages/Invoices";
import Sales from "@/pages/Sales";
import Visitors from "@/pages/Visitors";
import Leads from "@/pages/Leads";
import Architects from "@/pages/Architects";
import Inventory from "@/pages/Inventory";
import InventoryAnalytics from "@/pages/InventoryAnalytics";
import Tasks from "@/pages/Tasks";
import Meets from "@/pages/Meets";
import PettyCash from "@/pages/PettyCash";
import Outstanding from "@/pages/Outstanding";
import Attendance from "@/pages/Attendance";
import RoleManager from "@/pages/RoleManager";

const P = (page, Comp) => (
  <ProtectedRoute page={page}><Layout><Comp /></Layout></ProtectedRoute>
);

function App() {
  return (
    <AuthProvider>
      <Toaster position="top-right" richColors closeButton />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={P("dashboard", Dashboard)} />
          <Route path="/pipeline" element={P("pipeline", Pipeline)} />
          <Route path="/quotes" element={P("quotes", Quotes)} />
          <Route path="/invoices" element={P("invoices", Invoices)} />
          <Route path="/sales" element={P("sales", Sales)} />
          <Route path="/visitors" element={P("visitors", Visitors)} />
          <Route path="/leads" element={P("leads", Leads)} />
          <Route path="/architects" element={P("architects", Architects)} />
          <Route path="/inventory" element={P("inventory", Inventory)} />
          <Route path="/inventory/analytics" element={P("inv-analytics", InventoryAnalytics)} />
          <Route path="/tasks" element={P("tasks", Tasks)} />
          <Route path="/meets" element={P("meets", Meets)} />
          <Route path="/petty-cash" element={P("petty-cash", PettyCash)} />
          <Route path="/outstanding" element={P("outstanding", Outstanding)} />
          <Route path="/attendance" element={P("attendance", Attendance)} />
          <Route path="/admin/roles" element={P("roles", RoleManager)} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
