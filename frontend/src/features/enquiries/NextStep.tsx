/*
  What happens next on a lead, and who holds it.

  Shown as text rather than a second badge. A row carries one status,
  and only a slipped date earns a warning.
*/

import { describeLateness, formatDate } from "../../lib/format";
import type { EnquiryListItem } from "./types";
import styles from "./NextStep.module.css";

export default function NextStep({ enquiry }: { enquiry: EnquiryListItem }) {
  if (enquiry.status === "lost") {
    return <span className={styles.muted}>Closed</span>;
  }

  return (
    <>
      {enquiry.next_action || <span className={styles.missing}>Nothing planned</span>}

      {enquiry.next_action_due && enquiry.is_overdue && (
        <div className={styles.late}>
          <span aria-hidden="true">▲ </span>
          {describeLateness(enquiry.next_action_due)}
        </div>
      )}
      {enquiry.next_action_due && !enquiry.is_overdue && (
        <div className={styles.muted}>Due {formatDate(enquiry.next_action_due)}</div>
      )}

      <div className={styles.muted}>{enquiry.owner_name || "Unassigned"}</div>
    </>
  );
}
