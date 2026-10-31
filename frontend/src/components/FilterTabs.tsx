/* The saved views above a list, such as All, Unassigned and Overdue. */

import styles from "./FilterTabs.module.css";

interface FilterTabsProps {
  label: string;
  options: readonly { key: string; label: string }[];
  value: string;
  onChange: (key: string) => void;
}

export default function FilterTabs({ label, options, value, onChange }: FilterTabsProps) {
  return (
    <div className={styles.tabs} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.key}
          type="button"
          className={option.key === value ? styles.active : styles.tab}
          aria-pressed={option.key === value}
          onClick={() => onChange(option.key)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
