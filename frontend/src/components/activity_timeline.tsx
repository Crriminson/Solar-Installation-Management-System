/* Paginated, read-only actor and reason history for an authorized record. */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";
import type { Paginated } from "../features/enquiries/types";
import { formatDateTime } from "../lib/format";
import Pagination from "./Pagination";
import { EmptyMessage, ErrorMessage, LoadingMessage } from "./StateMessage";
import styles from "./activity_timeline.module.css";

interface ActivityEvent { id: number; action: string; actor_name: string; reason: string; created_at: string }

export default function ActivityTimeline({ endpoint, revision }: { endpoint: string; revision: number }) {
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ["activity", endpoint, revision, page],
    queryFn: () => apiGet<Paginated<ActivityEvent>>(`${endpoint}?page=${page}`) });
  return <section className={styles.section}>
    <h2 className={styles.heading}>Activity</h2>
    {query.isPending && <LoadingMessage label="Loading activity…" />}
    {query.isError && <ErrorMessage error={query.error} onRetry={query.refetch} />}
    {query.data?.count === 0 && <EmptyMessage>No activity recorded yet.</EmptyMessage>}
    <ol className={styles.list}>{query.data?.results.map((entry) => <li key={entry.id}>
      <strong>{entry.action.replaceAll("_", " ")}</strong>
      <div className={styles.caption}>{entry.actor_name} · {formatDateTime(entry.created_at)}</div>
      {entry.reason && <p>{entry.reason}</p>}
    </li>)}</ol>
    {query.data && <Pagination page={page} count={query.data.count} onChange={setPage} />}
  </section>;
}
