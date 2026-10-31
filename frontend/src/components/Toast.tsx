/*
  Brief confirmation that something worked.

  Toasts carry short success messages only. An error is not a toast: it
  stays on the screen until it is resolved, beside the thing that
  failed, where it can name the field (design.md section 12).

  A toast is never the only record of an outcome either. It confirms a
  change the screen already shows, so missing one loses nothing.
*/

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { CloseIcon, ConfirmIcon, ICON_SIZE } from "../design/icons";
import { ToastContext } from "./ToastContext";
import styles from "./Toast.module.css";

/* Long enough to read a short sentence, short enough not to linger. */
const DISMISS_AFTER_MS = 4000;

/* Older toasts are dropped past this, so a burst cannot cover the page. */
const MAX_VISIBLE = 3;

interface Toast {
  id: number;
  message: string;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<readonly Toast[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback((message: string) => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, message }].slice(-MAX_VISIBLE));
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}

      {/* Polite, so a confirmation never interrupts what is being read. */}
      <div className={styles.region} role="status" aria-live="polite">
        {toasts.map((toast) => (
          <ToastRow key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}


// ============================================================
// Helpers
// ============================================================

function ToastRow({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: number) => void;
}) {
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(toast.id), DISMISS_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <div className={styles.toast}>
      <ConfirmIcon className={styles.icon} size={ICON_SIZE.control} aria-hidden />
      <p className={styles.message}>{toast.message}</p>
      <button
        type="button"
        className={styles.close}
        aria-label="Dismiss"
        onClick={() => onDismiss(toast.id)}
      >
        <CloseIcon size={ICON_SIZE.inline} aria-hidden />
      </button>
    </div>
  );
}
