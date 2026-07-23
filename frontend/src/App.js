import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";

import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Alerts from "@/pages/Alerts";
import Pipeline from "@/pages/Pipeline";
import Quotes from "@/pages/Quotes";
import QuoteWorkspace from "@/pages/QuoteWorkspace";
import Sales from "@/pages/Sales";
import Visitors from "@/pages/Visitors";
import Leads from "@/pages/Leads";
import Architects from "@/pages/Architects";
import Projects from "@/pages/Projects";
import DWSurvey from "@/pages/DWSurvey";
import Outstanding from "@/pages/Outstanding";
import Inventory from "@/pages/Inventory";
import StockLedger from "@/pages/StockLedger";
import InventoryAnalytics from "@/pages/InventoryAnalytics";
import Invoices from "@/pages/Invoices";
import PettyCash from "@/pages/PettyCash";
import Meets from "@/pages/Meets";
import Reports from "@/pages/Reports";
import DataCentre from "@/pages/DataCentre";
import Tasks from "@/pages/Tasks";
import Attendance from "@/pages/Attendance";
import RoleManager from "@/pages/RoleManager";

// page = the permission id from lib/nav.js that gates the route.
const R = (page, El) => (
  <ProtectedRoute page={page}><Layout>{El}</Layout></ProtectedRoute>
);

function App() {
  return (
    <AuthProvider>
      <Toaster position="top-right" richColors closeButton />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={R("dashboard", <Dashboard />)} />
          <Route path="/alerts" element={R("alerts", <Alerts />)} />
          <Route path="/pipeline" element={R("pipeline", <Pipeline />)} />
          <Route path="/quotes" element={R("quotes", <Quotes />)} />
          <Route path="/quotes/ws/:id" element={R("quotes", <QuoteWorkspace />)} />
          <Route path="/sales" element={R("sales", <Sales />)} />
          <Route path="/visitors" element={R("visitors", <Visitors />)} />
          <Route path="/leads" element={R("leads", <Leads />)} />
          <Route path="/architects" element={R("architects", <Architects />)} />
          <Route path="/projects" element={R("projects", <Projects />)} />
          <Route path="/dw-survey" element={R("dwsurvey", <DWSurvey />)} />
          <Route path="/outstanding" element={R("outstanding", <Outstanding />)} />
          <Route path="/inventory" element={R("inventory", <Inventory />)} />
          <Route path="/stock-ledger" element={R("stock-ledger", <StockLedger />)} />
          <Route path="/inventory/analytics" element={R("inv-analytics", <InventoryAnalytics />)} />
          <Route path="/invoices" element={R("invoice-gen", <Invoices />)} />
          <Route path="/petty-cash" element={R("petty", <PettyCash />)} />
          <Route path="/meets" element={R("meetplan", <Meets />)} />
          <Route path="/reports" element={R("reports", <Reports />)} />
          <Route path="/data-centre" element={R("data-centre", <DataCentre />)} />
          <Route path="/tasks" element={R("tasks", <Tasks />)} />
          <Route path="/attendance" element={R("attendance", <Attendance />)} />
          <Route path="/admin/roles" element={R("roles", <RoleManager />)} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
