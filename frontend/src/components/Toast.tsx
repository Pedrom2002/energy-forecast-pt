import { useEffect, useState, useCallback } from 'react';
import { CheckCircle, AlertTriangle, X, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';

type ToastType = 'success' | 'error' | 'info';

interface ToastMessage {
  id: number;
  type: ToastType;
  text: string;
}

let _addToast: ((type: ToastType, text: string) => void) | null = null;

/** Imperative API — call from anywhere */
export const toast = {
  success: (text: string) => _addToast?.('success', text),
  error: (text: string) => _addToast?.('error', text),
  info: (text: string) => _addToast?.('info', text),
};

const ICONS: Record<ToastType, React.ReactNode> = {
  success: <CheckCircle className="w-4 h-4 text-energy-green" aria-hidden="true" />,
  error: <AlertTriangle className="w-4 h-4 text-energy-red" aria-hidden="true" />,
  info: <Info className="w-4 h-4 text-primary-400" aria-hidden="true" />,
};

const TONE: Record<ToastType, string> = {
  success: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-100',
  error: 'border-rose-400/30 bg-rose-500/10 text-rose-100',
  info: 'border-primary-400/30 bg-primary-500/10 text-primary-100',
};

/** Auto-dismiss duration (ms) — rule: toast-dismiss 3-5s */
const AUTO_DISMISS_MS = 4000;

let nextId = 0;

export function ToastContainer() {
  const [messages, setMessages] = useState<ToastMessage[]>([]);
  const { t } = useTranslation();

  const add = useCallback((type: ToastType, text: string) => {
    const id = ++nextId;
    setMessages((prev) => [...prev, { id, type, text }]);
    setTimeout(() => {
      setMessages((prev) => prev.filter((m) => m.id !== id));
    }, AUTO_DISMISS_MS);
  }, []);

  useEffect(() => {
    _addToast = add;
    return () => { _addToast = null; };
  }, [add]);

  const dismiss = (id: number) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
  };

  if (messages.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-[200] flex flex-col gap-2 max-w-sm w-full pointer-events-none"
      aria-live="polite"
      aria-label={t('toast.listAria')}
    >
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-xl border
            text-sm font-medium animate-slide-in-right backdrop-blur-xl shadow-lg
            ${TONE[msg.type]}`}
          role="status"
        >
          {ICONS[msg.type]}
          <span className="flex-1">{msg.text}</span>
          <button
            type="button"
            onClick={() => dismiss(msg.id)}
            className="shrink-0 p-1 rounded hover:bg-white/10 transition cursor-pointer"
            aria-label={t('toast.closeAria')}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
