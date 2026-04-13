import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import { ErrorBoundary } from './components/ErrorBoundary';
import Dashboard from './pages/Dashboard';
import Predict from './pages/Predict';
import Forecast from './pages/Forecast';
import Monitoring from './pages/Monitoring';
import NotFound from './pages/NotFound';
import { ToastContainer } from './components/Toast';

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        {/* App shell with sidebar + top bar — Dashboard is the single entry point */}
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/predict" element={<Predict />} />
          {/* Legacy redirect: /batch was merged into /forecast */}
          <Route path="/batch" element={<Navigate to="/forecast" replace />} />
          <Route path="/forecast" element={<Forecast />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/explain" element={<Navigate to="/forecast" replace />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
      <ToastContainer />
    </ErrorBoundary>
  );
}
