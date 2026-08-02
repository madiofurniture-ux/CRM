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
import Sales from "@/pages/Sales";
import Visitors from "@/pages/Visitors";
import Leads from "@/pages/Leads";
import Architects from "@/pages/Architects";
import Inventory from "@/pages/Inventory";
import InventoryAnalytics from "@/pages/InventoryAnalytics";
import Tasks from "@/pages/Tasks";
import Projects from "@/pages/Projects";
import Attendance from "@/pages/Attendance";
import RoleManager from "@/pages/RoleManager";

// Previously orphaned — the sidebar linked to these but no route existed
import Outstanding from "@/pages/Outstanding";
import Invoices from "@/pages/Invoices";
import PettyCash from "@/pages/PettyCash";
import Meets from "@/pages/Meets";

// Recovered parity modules
import Reports from "@/pages/Reports";
import Alerts from "@/pages/Alerts";
import DWSurvey from "@/pages/DWSurvey";
import QuoteWorkspace from "@/pages/QuoteWorkspace";
import StockLedger from "@/pages/StockLedger";
import DataCentre from "@/pages/DataCentre";
import FinancialYear from "@/pages/FinancialYear";
import Workflows from "@/pages/Workflows";

function App() {
  return (
    <AuthProvider>
      <Toaster position="top-right" richColors closeButton />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute page="dashboard">
                <Layout><Dashboard /></Layout>
              </ProtectedRoute>
            }
          />
          <Route path="/pipeline" element={<ProtectedRoute page="pipeline"><Layout><Pipeline /></Layout></ProtectedRoute>} />
          <Route path="/quotes" element={<ProtectedRoute page="quotes"><Layout><Quotes /></Layout></ProtectedRoute>} />
          <Route path="/sales" element={<ProtectedRoute page="sales"><Layout><Sales /></Layout></ProtectedRoute>} />
          <Route path="/visitors" element={<ProtectedRoute page="visitors"><Layout><Visitors /></Layout></ProtectedRoute>} />
          <Route path="/leads" element={<ProtectedRoute page="leads"><Layout><Leads /></Layout></ProtectedRoute>} />
          <Route path="/architects" element={<ProtectedRoute page="architects"><Layout><Architects /></Layout></ProtectedRoute>} />
          <Route path="/inventory" element={<ProtectedRoute page="inventory"><Layout><Inventory /></Layout></ProtectedRoute>} />
          <Route path="/inventory/analytics" element={<ProtectedRoute page="inv-analytics"><Layout><InventoryAnalytics /></Layout></ProtectedRoute>} />
          <Route path="/tasks" element={<ProtectedRoute page="tasks"><Layout><Tasks /></Layout></ProtectedRoute>} />
          <Route path="/projects" element={<ProtectedRoute page="projects"><Layout><Projects /></Layout></ProtectedRoute>} />
          <Route path="/attendance" element={<ProtectedRoute page="attendance"><Layout><Attendance /></Layout></ProtectedRoute>} />
          <Route path="/admin/roles" element={<ProtectedRoute page="roles"><Layout><RoleManager /></Layout></ProtectedRoute>} />

          {/* Previously orphaned — sidebar linked here but no route existed */}
          <Route path="/outstanding" element={<ProtectedRoute page="outstanding"><Layout><Outstanding /></Layout></ProtectedRoute>} />
          <Route path="/invoices" element={<ProtectedRoute page="invoice-gen"><Layout><Invoices /></Layout></ProtectedRoute>} />
          <Route path="/petty-cash" element={<ProtectedRoute page="petty"><Layout><PettyCash /></Layout></ProtectedRoute>} />
          <Route path="/meets" element={<ProtectedRoute page="meetplan"><Layout><Meets /></Layout></ProtectedRoute>} />

          {/* Recovered parity modules */}
          <Route path="/reports" element={<ProtectedRoute page="reports"><Layout><Reports /></Layout></ProtectedRoute>} />
          <Route path="/alerts" element={<ProtectedRoute page="alerts"><Layout><Alerts /></Layout></ProtectedRoute>} />
          <Route path="/dw-survey" element={<ProtectedRoute page="dwsurvey"><Layout><DWSurvey /></Layout></ProtectedRoute>} />
          <Route path="/quotes/ws/:id" element={<ProtectedRoute page="quotes"><Layout><QuoteWorkspace /></Layout></ProtectedRoute>} />
          <Route path="/stock-ledger" element={<ProtectedRoute page="stock-ledger"><Layout><StockLedger /></Layout></ProtectedRoute>} />
          <Route path="/data-centre" element={<ProtectedRoute page="data-centre"><Layout><DataCentre /></Layout></ProtectedRoute>} />
          <Route path="/admin/financial-year" element={<ProtectedRoute page="financial-year"><Layout><FinancialYear /></Layout></ProtectedRoute>} />
          <Route path="/admin/workflows" element={<ProtectedRoute page="workflows"><Layout><Workflows /></Layout></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
