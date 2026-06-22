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
import RoleManager from "@/pages/RoleManager";

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
          <Route path="/admin/roles" element={<ProtectedRoute><Layout><RoleManager /></Layout></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
