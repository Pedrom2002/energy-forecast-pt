import { useEffect, useState, useCallback } from 'react';
import { CheckCircle, AlertTriangle, X, Info } from 'lucide-react';

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
  success: <CheckCircle className="w-4 h-4 text-green-500" aria-hidden="true" />,
  error: <AlertTriangle className="w-4 h-4 text-red-500" aria-hidden="true" />,
  info: <Info className="w-4 h-4 text-primary-500" aria-hidden="true" />,
};

const BG: Record<ToastType, string> = {
  success: 'bg-green-50 border-green-200 text-green-800',
  error: 'bg-red-50 border-red-200 text-red-800',
  info: 'bg-primary-50 border-primary-200 text-primary-800',
};

const DARK_BG: Record<ToastType, string> = {
  success: 'dark:bg-green-900/30 dark:border-green-800 dark:text-green-200',
  error: 'dark:bg-red-900/30 dark:border-red-800 dark:text-red-200',
  info: 'dark:bg-primary-900/30 dark:border-primary-800 dark:text-primary-200',
};

/** Auto-dismiss duration (ms) — rule: toast-dismiss 3-5s */
const AUTO_DISMISS_MS = 4000;

let nextId = 0;

export function ToastContainer() {
  const [messages, setMessages] = useState<ToastMessage[]>([]);

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
      aria-label="Notificacoes"
    >
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-xl border shadow-lg
            text-sm font-medium animate-slide-in-right
            ${BG[msg.type]} ${DARK_BG[msg.type]}`}
          role="status"
        >
          {ICONS[msg.type]}
          <span className="flex-1">{msg.text}</span>
          <button
            type="button"
            onClick={() => dismiss(msg.id)}
            className="shrink-0 p-1 rounded hover:bg-black/5 dark:hover:bg-white/10 transition cursor-pointer"
            aria-label="Fechar notificacao"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
