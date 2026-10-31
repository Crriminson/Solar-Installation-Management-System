/*
  My Work, the staff home page. F20 grows this into every role's queue.

  It answers one question: what is waiting on me? One group per role, so
  someone holding several roles sees all their work on one page and has
  nothing to switch. Every count is live and opens its own records.
*/

import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import Cue from "../../components/Cue";
import PageHeader from "../../components/PageHeader";
import Reference from "../../components/Reference";
import { EmptyMessage, ErrorMessage } from "../../components/StateMessage";
import { businessToday, describeLateness, formatDate } from "../../lib/format";
import { hasRole, useStaffUser, type StaffUser } from "../auth/session";
import { fetchEnquiries, type QueueFilters } from "../enquiries/api";
import { QUEUE_REFRESH_MS } from "../enquiries/queue";
import type { EnquiryListItem } from "../enquiries/types";
import styles from "./MyWorkPage.module.css";

/* How many urgent items to list. The cue opens the rest. */
const URGENT_ROWS = 5;

export default function MyWorkPage() {
  const user = useStaffUser();
  const showSales = hasRole(user, "sales");
  const showOperations = hasRole(user, "operations_manager");

  return (
    <>
      <PageHeader title="My work" subtitle={formatDate(businessToday())} />

      {showSales && <SalesWork />}
      {showOperations && <OperationsWork />}
      {!showSales && !showOperations && <NoQueue user={user} />}
    </>
  );
}


// ============================================================
// Groups
// ============================================================

function SalesWork() {
  const fresh = useCount({ status: "new" });
  const overdue = useQuery(queueQuery({ overdue: true }));
  const unassigned = useCount({ unassigned: true });

  return (
    <section className={styles.group}>
      <h2 className={styles.groupTitle}>Sales</h2>
      <div className={styles.cues}>
        <Cue label="New enquiries" count={fresh} to="/enquiries?view=new" />
        <Cue
          label="Overdue"
          count={overdue.data?.count}
          to="/enquiries?view=overdue"
          urgent
        />
        <Cue label="Unassigned" count={unassigned} to="/enquiries?view=unassigned" />
      </div>

      {overdue.isError && <ErrorMessage error={overdue.error} onRetry={overdue.refetch} />}

      {overdue.data && overdue.data.results.length > 0 && (
        <>
          <h3 className={styles.listTitle}>Overdue</h3>
          <ul className={styles.list}>
            {overdue.data.results.slice(0, URGENT_ROWS).map((enquiry) => (
              <OverdueRow key={enquiry.id} enquiry={enquiry} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function OperationsWork() {
  const unassigned = useCount({ unassigned: true });

  return (
    <section className={styles.group}>
      <h2 className={styles.groupTitle}>Operations</h2>
      <div className={styles.cues}>
        <Cue
          label="Leads with no owner"
          count={unassigned}
          to="/enquiries?view=unassigned"
        />
      </div>
    </section>
  );
}

/* Honest about roles whose features do not exist yet. */
function NoQueue({ user }: { user: StaffUser }) {
  return (
    <EmptyMessage>
      {user.roles.length === 0
        ? "You have no role yet. Ask an administrator to give you one."
        : "There is no work queue for your role yet."}
    </EmptyMessage>
  );
}


// ============================================================
// Helpers
// ============================================================

function OverdueRow({ enquiry }: { enquiry: EnquiryListItem }) {
  return (
    <li className={styles.row}>
      <Link to={`/enquiries?view=overdue&selected=${enquiry.id}`}>
        <Reference>{enquiry.reference}</Reference>
      </Link>
      <span>{enquiry.site.customer.full_name}</span>
      <span className={styles.action}>{enquiry.next_action}</span>
      <span className={styles.late}>
        {enquiry.next_action_due && describeLateness(enquiry.next_action_due)}
      </span>
    </li>
  );
}

function queueQuery(filters: QueueFilters) {
  return {
    queryKey: ["enquiries", "work", filters],
    queryFn: () => fetchEnquiries(filters),
    refetchInterval: QUEUE_REFRESH_MS,
  };
}

function useCount(filters: QueueFilters) {
  return useQuery(queueQuery(filters)).data?.count;
}
