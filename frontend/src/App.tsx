import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import { ErrorBoundary } from './components/ErrorBoundary';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import Predict from './pages/Predict';
import Batch from './pages/Batch';
import Forecast from './pages/Forecast';
import Monitoring from './pages/Monitoring';
import Explain from './pages/Explain';
import NotFound from './pages/NotFound';
import { ToastContainer } from './components/Toast';

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        {/* Landing page — no sidebar, full-bleed */}
        <Route path="/" element={<Landing />} />

        {/* App shell with sidebar + top bar */}
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/predict" element={<Predict />} />
          <Route path="/batch" element={<Batch />} />
          <Route path="/forecast" element={<Forecast />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/explain" element={<Explain />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
      <ToastContainer />
    </ErrorBoundary>
  );
}
