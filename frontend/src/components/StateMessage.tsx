/*
  The states a screen shows in place of its content.

  Spec.md section 6 asks every list to handle loading, empty, error and
  permission-denied. Keeping them here means each looks the same and
  none gets forgotten.

  Loading draws the shape of the content that is coming rather than the
  word "Loading", so the page does not jump when the rows arrive. The
  label is still announced for a screen reader.
*/

import type { ReactNode } from "react";

import { describeError, isForbidden } from "../api/client";
import { BlockedIcon, EmptyIcon, ForbiddenIcon, RetryIcon } from "../design/icons";
import Button from "./Button";
import styles from "./StateMessage.module.css";

/* Rows drawn while a list loads. Enough to fill the fold, few enough
   that the real list does not shift the page when it replaces them. */
const SKELETON_ROWS = 6;

export function LoadingMessage({
  label,
  rows = SKELETON_ROWS,
}: {
  label: string;
  rows?: number;
}) {
  return (
    <div className={styles.skeleton} role="status" aria-busy="true">
      <span className={styles.srOnly}>{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <span key={index} className={styles.skeletonRow} aria-hidden="true" />
      ))}
    </div>
  );
}

/* For a record screen rather than a list: a few blocks of varying
   width, which reads as a form rather than a table. */
export function LoadingRecord({ label }: { label: string }) {
  return (
    <div className={styles.skeletonRecord} role="status" aria-busy="true">
      <span className={styles.srOnly}>{label}</span>
      <span className={`${styles.skeletonRow} ${styles.skeletonTitle}`} aria-hidden="true" />
      <span className={styles.skeletonCard} aria-hidden="true" />
      <span className={styles.skeletonCard} aria-hidden="true" />
    </div>
  );
}

export function EmptyMessage({
  children,
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={styles.message}>
      <EmptyIcon className={styles.messageIcon} aria-hidden />
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
        <ForbiddenIcon className={styles.alertIcon} aria-hidden />
        <p className={styles.text}>
          You do not have access to this. Ask an administrator if you need it.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.alert} role="alert">
      <BlockedIcon className={styles.alertIcon} aria-hidden />
      <p className={styles.text}>{describeError(error)}</p>
      {onRetry && (
        <Button icon={<RetryIcon aria-hidden />} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
