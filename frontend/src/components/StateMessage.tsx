/*
  The states a screen shows in place of its content.

  Spec.md section 6 asks every list to handle loading, empty, error and
  permission-denied. Keeping them here means each looks the same and
  none gets forgotten.
*/

import { describeError, isForbidden } from "../api/client";
import Button from "./Button";
import styles from "./StateMessage.module.css";

export function LoadingMessage({ label }: { label: string }) {
  return <p className={styles.message}>{label}</p>;
}

export function EmptyMessage({
  children,
  action,
}: {
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className={styles.message}>
      <p className={styles.text}>{children}</p>
      {action}
    </div>
  );
}

/* A failed load, or a refusal, with a way to try again where it helps. */
export function ErrorMessage({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  if (isForbidden(error)) {
    return (
      <div className={styles.alert} role="alert">
        <p className={styles.text}>
          You do not have access to this. Ask an administrator if you need it.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.alert} role="alert">
      <p className={styles.text}>{describeError(error)}</p>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}
