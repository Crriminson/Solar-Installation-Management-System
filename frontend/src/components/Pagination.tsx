/*
  Page controls under a list.

  The size must match DEFAULT_PAGE_SIZE in the Django settings, which
  decides how many rows each page really holds.
*/

import Button from "./Button";
import styles from "./Pagination.module.css";

const PAGE_SIZE = 25;

interface PaginationProps {
  page: number;
  count: number;
  onChange: (page: number) => void;
}

export default function Pagination({ page, count, onChange }: PaginationProps) {
  const first = (page - 1) * PAGE_SIZE + 1;
  const last = Math.min(page * PAGE_SIZE, count);
  const hasNext = last < count;

  if (count <= PAGE_SIZE) return null;

  return (
    <nav className={styles.pagination} aria-label="Pages">
      <span className={styles.range}>
        {first}–{last} of {count}
      </span>
      <Button disabled={page === 1} onClick={() => onChange(page - 1)}>
        Previous
      </Button>
      <Button disabled={!hasNext} onClick={() => onChange(page + 1)}>
        Next
      </Button>
    </nav>
  );
}
