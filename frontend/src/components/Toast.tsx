import { useEffect } from 'react';
import { CheckCircle, XCircle, X } from 'lucide-react';

export type ToastVariant = 'success' | 'error';

export interface ToastMessage {
  id: string;
  message: string;
  variant: ToastVariant;
}

interface Props {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

function ToastItem({ toast, onDismiss }: { toast: ToastMessage; onDismiss: (id: string) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 4_000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  const isSuccess = toast.variant === 'success';

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`flex items-center gap-3 px-4 py-3 rounded-lg shadow-xl border text-sm font-medium min-w-72 max-w-sm ${
        isSuccess
          ? 'bg-green-900/90 border-green-600/50 text-green-100'
          : 'bg-red-900/90 border-red-600/50 text-red-100'
      }`}
    >
      {isSuccess ? (
        <CheckCircle size={16} className="text-green-400 shrink-0" />
      ) : (
        <XCircle size={16} className="text-red-400 shrink-0" />
      )}
      <span className="flex-1">{toast.message}</span>
      <button
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className="shrink-0 opacity-60 hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-white/50 rounded"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export default function Toast({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      aria-label="Notifications"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
