/* A record's status, shown with a shape, a colour and a label. */

import { TONE_SHAPES, type StatusInfo } from "./status";
import styles from "./StatusBadge.module.css";

export default function StatusBadge({ status }: { status: StatusInfo }) {
  return (
    <span className={`${styles.badge} ${styles[status.tone]}`}>
      <span className={styles.shape} aria-hidden="true">
        {TONE_SHAPES[status.tone]}
      </span>
      {status.label}
    </span>
  );
}
