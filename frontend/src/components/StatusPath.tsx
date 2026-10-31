/*
  A record's journey, and what its current stage needs.

  Display only. Changing state always goes through an explicit action,
  so the backend can check it. See spec.md section 9.
*/

import styles from "./StatusPath.module.css";

interface Stage {
  key: string;
  label: string;
}

interface StatusPathProps {
  stages: readonly Stage[];
  current: string;
  guidance?: string;
}

export default function StatusPath({ stages, current, guidance }: StatusPathProps) {
  const currentIndex = stages.findIndex((stage) => stage.key === current);

  return (
    <div className={styles.wrapper}>
      <ol className={styles.path}>
        {stages.map((stage, index) => (
          <li
            key={stage.key}
            className={stageClass(index, currentIndex)}
            aria-current={index === currentIndex ? "step" : undefined}
          >
            {stage.label}
          </li>
        ))}
      </ol>
      {guidance && <p className={styles.guidance}>{guidance}</p>}
    </div>
  );
}

function stageClass(index: number, currentIndex: number) {
  if (index === currentIndex) return `${styles.stage} ${styles.current}`;
  return index < currentIndex ? `${styles.stage} ${styles.passed}` : styles.stage;
}
