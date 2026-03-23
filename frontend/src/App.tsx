import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Predict from './pages/Predict';
import Batch from './pages/Batch';
import Forecast from './pages/Forecast';
import Monitoring from './pages/Monitoring';
import Explain from './pages/Explain';
import { ToastContainer } from './components/Toast';

export default function App() {
  return (
    <>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/predict" element={<Predict />} />
          <Route path="/batch" element={<Batch />} />
          <Route path="/forecast" element={<Forecast />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/explain" element={<Explain />} />
        </Route>
      </Routes>
      <ToastContainer />
    </>
  );
}
