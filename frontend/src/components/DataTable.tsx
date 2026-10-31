/*
  The table behind every list.

  On a phone each row becomes a stacked card, labelled from its column
  headers, so status and next step are never hidden off to the side.
  See design.md section 4.
*/

import type { ReactNode } from "react";

import styles from "./DataTable.module.css";

export interface Column<Row> {
  header: string;
  render: (row: Row) => ReactNode;
  numeric?: boolean;
}

interface DataTableProps<Row> {
  caption: string;
  columns: readonly Column<Row>[];
  rows: readonly Row[];
  rowKey: (row: Row) => string | number;
  onRowClick?: (row: Row) => void;
  selectedKey?: string | number | null;
}

export default function DataTable<Row>({
  caption,
  columns,
  rows,
  rowKey,
  onRowClick,
  selectedKey,
}: DataTableProps<Row>) {
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <caption className={styles.caption}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.header}
                scope="col"
                className={column.numeric ? styles.numeric : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {rows.map((row) => {
            const key = rowKey(row);
            return (
              <tr
                key={key}
                className={rowClass(Boolean(onRowClick), key === selectedKey)}
                tabIndex={onRowClick ? 0 : undefined}
                onClick={onRowClick && (() => onRowClick(row))}
                onKeyDown={
                  onRowClick &&
                  ((event) => {
                    if (event.key === "Enter") onRowClick(row);
                  })
                }
              >
                {columns.map((column) => (
                  <td
                    key={column.header}
                    className={column.numeric ? styles.numeric : undefined}
                    data-label={column.header}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function rowClass(clickable: boolean, selected: boolean) {
  if (selected) return `${styles.clickable} ${styles.selected}`;
  return clickable ? styles.clickable : undefined;
}
