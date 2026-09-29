import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import LiveMonitor from './pages/LiveMonitor';
import Experiments from './pages/Experiments';
import ReviewQueue from './pages/ReviewQueue';
import Analytics from './pages/Analytics';
import Reports from './pages/Reports';
import Settings from './pages/Settings';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="live" element={<LiveMonitor />} />
          <Route path="experiments" element={<Experiments />} />
          <Route path="review" element={<ReviewQueue />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
