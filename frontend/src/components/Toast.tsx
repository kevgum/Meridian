import { useEffect } from 'react';
import { Check, TriangleAlert, X } from 'lucide-react';

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

/**
 * A single notice.
 *
 * Failures hold twice as long as confirmations — an analyst who has just been
 * told the audit log did not update needs longer to read it than one who has
 * been told an escalation went through.
 */
function ToastItem({
  toast,
  onDismiss,
}: {
  toast: ToastMessage;
  onDismiss: (id: string) => void;
}) {
  const isSuccess = toast.variant === 'success';

  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), isSuccess ? 4_000 : 9_000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss, isSuccess]);

  return (
    <div
      role="alert"
      className={`anim-dialog flex max-w-sm min-w-72 items-start gap-3 rounded-sm border px-4 py-3 shadow-[var(--shadow-overlay)] ${
        isSuccess
          ? 'border-pass-edge bg-pass-wash text-pass-strong'
          : 'border-warn-edge bg-warn-wash text-warn-strong'
      }`}
    >
      {isSuccess ? (
        <Check size={15} className="mt-0.5 shrink-0 text-pass" aria-hidden="true" />
      ) : (
        <TriangleAlert size={15} className="mt-0.5 shrink-0 text-warn" aria-hidden="true" />
      )}
      <span className="flex-1 text-xs leading-snug font-medium">{toast.message}</span>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss this notice"
        className="row-focus -m-1 shrink-0 rounded-xs p-1 opacity-70 transition-[opacity] duration-100 ease-out hover:opacity-100"
      >
        <X size={13} aria-hidden="true" />
      </button>
    </div>
  );
}

/**
 * Stacked at one corner, fixed — a new notice never moves an existing one, and
 * nothing on the page below shifts when one arrives or leaves.
 */
export default function Toast({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed right-4 bottom-4 flex flex-col gap-2"
      style={{ zIndex: 'var(--z-toast)' }}
      aria-label="Notifications"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
