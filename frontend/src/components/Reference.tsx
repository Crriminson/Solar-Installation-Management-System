/* A code such as ENQ-2026-00104 or a serial, set in mono so it reads as one. */

import styles from "./Reference.module.css";

export default function Reference({ children }: { children: React.ReactNode }) {
  return <span className={styles.reference}>{children}</span>;
}
