import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import Layout from './components/Layout';
import SystemStatusProvider from './components/SystemStatusProvider';

// Pages load on demand, so e.g. the charting library is only downloaded for Analytics.
const Dashboard = lazy(() => import('./pages/Dashboard'));
const LiveMonitor = lazy(() => import('./pages/LiveMonitor'));
const Experiments = lazy(() => import('./pages/Experiments'));
const ExperimentDetail = lazy(() => import('./pages/ExperimentDetail'));
const ReviewQueue = lazy(() => import('./pages/ReviewQueue'));
const Analytics = lazy(() => import('./pages/Analytics'));
const Reports = lazy(() => import('./pages/Reports'));
const Settings = lazy(() => import('./pages/Settings'));

function PageLoading() {
  return (
    <div className="p-12 flex items-center justify-center gap-2 text-sm text-brand-secondary">
      <Loader2 className="w-4 h-4 animate-spin" /> Loading…
    </div>
  );
}

const page = (element: React.ReactNode) => <Suspense fallback={<PageLoading />}>{element}</Suspense>;

function App() {
  return (
    <SystemStatusProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={page(<Dashboard />)} />
            <Route path="live" element={page(<LiveMonitor />)} />
            <Route path="experiments" element={page(<Experiments />)} />
            <Route path="experiments/:id" element={page(<ExperimentDetail />)} />
            <Route path="review" element={page(<ReviewQueue />)} />
            <Route path="analytics" element={page(<Analytics />)} />
            <Route path="reports" element={page(<Reports />)} />
            <Route path="settings" element={page(<Settings />)} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </SystemStatusProvider>
  );
}

export default App;
