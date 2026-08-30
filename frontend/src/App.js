import "@/App.css";
import { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";

// Login is the only screen every visitor needs before auth, so it stays in
// the main bundle. Everything past it loads on demand — the app was
// shipping all ~27 pages in one bundle regardless of which one you landed
// on, which is most of what made the very first load feel slow.
import Login from "@/pages/Login";
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Pipeline = lazy(() => import("@/pages/Pipeline"));
const Quotes = lazy(() => import("@/pages/Quotes"));
const Sales = lazy(() => import("@/pages/Sales"));
const Visitors = lazy(() => import("@/pages/Visitors"));
const Leads = lazy(() => import("@/pages/Leads"));
const Architects = lazy(() => import("@/pages/Architects"));
const Inventory = lazy(() => import("@/pages/Inventory"));
const InventoryAnalytics = lazy(() => import("@/pages/InventoryAnalytics"));
const Tasks = lazy(() => import("@/pages/Tasks"));
const Projects = lazy(() => import("@/pages/Projects"));
const Attendance = lazy(() => import("@/pages/Attendance"));
const RoleManager = lazy(() => import("@/pages/RoleManager"));

// Previously orphaned — the sidebar linked to these but no route existed
const Outstanding = lazy(() => import("@/pages/Outstanding"));
const Invoices = lazy(() => import("@/pages/Invoices"));
const PettyCash = lazy(() => import("@/pages/PettyCash"));
const Meets = lazy(() => import("@/pages/Meets"));

// Recovered parity modules
const Reports = lazy(() => import("@/pages/Reports"));
const Alerts = lazy(() => import("@/pages/Alerts"));
const DWSurvey = lazy(() => import("@/pages/DWSurvey"));
const QuoteWorkspace = lazy(() => import("@/pages/QuoteWorkspace"));
const StockLedger = lazy(() => import("@/pages/StockLedger"));
const DataCentre = lazy(() => import("@/pages/DataCentre"));
const FinancialYear = lazy(() => import("@/pages/FinancialYear"));
const Workflows = lazy(() => import("@/pages/Workflows"));
const BusinessSettings = lazy(() => import("@/pages/BusinessSettings"));

// 11-stage operational flow: Requirement + Configurator + Customer
const Requirements = lazy(() => import("@/pages/Requirements"));
const Configurator = lazy(() => import("@/pages/Configurator"));
const Customers = lazy(() => import("@/pages/Customers"));
const QuoteFollowups = lazy(() => import("@/pages/QuoteFollowups"));

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-screen text-sm text-[var(--ink-3)]">
      Loading…
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <Toaster position="top-right" richColors closeButton />
      <BrowserRouter>
        <Suspense fallback={<PageLoader />}>
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
          <Route path="/admin/business" element={<ProtectedRoute page="business"><Layout><BusinessSettings /></Layout></ProtectedRoute>} />
          <Route path="/requirements" element={<ProtectedRoute page="requirements"><Layout><Requirements /></Layout></ProtectedRoute>} />
          <Route path="/configurator" element={<ProtectedRoute page="configurator"><Layout><Configurator /></Layout></ProtectedRoute>} />
          <Route path="/customers" element={<ProtectedRoute page="customers"><Layout><Customers /></Layout></ProtectedRoute>} />
          <Route path="/quotes/followups" element={<ProtectedRoute page="quote-followups"><Layout><QuoteFollowups /></Layout></ProtectedRoute>} />
        </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
