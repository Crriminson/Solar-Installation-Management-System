/*
  Labelled form controls.

  Each one ties its label, hint and error to the control, so a screen
  reader announces them and a typed error sits beside its own field.
*/

import { useId, type ReactNode } from "react";

import styles from "./Field.module.css";

interface FieldShellProps {
  label: string;
  required?: boolean;
  hint?: string;
  error?: string;
  wide?: boolean;
}

/* Everything around a control, with ids it can point back to. */
function FieldShell({
  label,
  required,
  hint,
  error,
  wide,
  children,
}: FieldShellProps & {
  children: (ids: {
    id: string;
    "aria-invalid": boolean;
    "aria-describedby": string | undefined;
  }) => ReactNode;
}) {
  const id = useId();
  const noteId = `${id}-note`;
  const hasNote = Boolean(hint || error);

  return (
    <div className={`${styles.field} ${wide ? styles.wide : ""}`}>
      <label className={`${styles.label} ${required ? styles.required : ""}`} htmlFor={id}>
        {label}
      </label>

      {children({
        id,
        "aria-invalid": Boolean(error),
        "aria-describedby": hasNote ? noteId : undefined,
      })}

      {error && <span id={noteId} className={styles.error}>{error}</span>}
      {hint && !error && <span id={noteId} className={styles.hint}>{hint}</span>}
    </div>
  );
}


// ============================================================
// Text, number and date
// ============================================================

interface TextFieldProps extends FieldShellProps {
  value: string;
  onChange: (value: string) => void;
  type?: string;
  inputMode?: "text" | "decimal" | "numeric" | "tel" | "email";
  autoComplete?: string;
  unit?: string;
  max?: string;
}

export function TextField({
  value,
  onChange,
  type = "text",
  inputMode,
  autoComplete,
  unit,
  max,
  ...shell
}: TextFieldProps) {
  return (
    <FieldShell {...shell}>
      {(ids) => (
        <div className={styles.withUnit}>
          <input
            {...ids}
            className={styles.control}
            type={type}
            inputMode={inputMode}
            autoComplete={autoComplete}
            value={value}
            max={max}
            onChange={(event) => onChange(event.target.value)}
          />
          {unit && <span className={styles.unit}>{unit}</span>}
        </div>
      )}
    </FieldShell>
  );
}


// ============================================================
// Choice
// ============================================================

export interface Option {
  value: string;
  label: string;
}

interface SelectFieldProps extends FieldShellProps {
  value: string;
  onChange: (value: string) => void;
  options: readonly Option[];
  placeholder?: string;
}

export function SelectField({
  value,
  onChange,
  options,
  placeholder,
  ...shell
}: SelectFieldProps) {
  return (
    <FieldShell {...shell}>
      {(ids) => (
        <select
          {...ids}
          className={styles.control}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          {placeholder !== undefined && <option value="">{placeholder}</option>}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </FieldShell>
  );
}


// ============================================================
// Long text
// ============================================================

interface TextAreaFieldProps extends FieldShellProps {
  value: string;
  onChange: (value: string) => void;
}

export function TextAreaField({ value, onChange, ...shell }: TextAreaFieldProps) {
  return (
    <FieldShell {...shell}>
      {(ids) => (
        <textarea
          {...ids}
          className={`${styles.control} ${styles.textarea}`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </FieldShell>
  );
}


// ============================================================
// File
// ============================================================

interface FileFieldProps extends FieldShellProps {
  accept: string;
  onChange: (file: File | null) => void;
}

export function FileField({ accept, onChange, ...shell }: FileFieldProps) {
  return (
    <FieldShell {...shell}>
      {(ids) => (
        <input
          {...ids}
          className={styles.file}
          type="file"
          accept={accept}
          onChange={(event) => onChange(event.target.files?.[0] ?? null)}
        />
      )}
    </FieldShell>
  );
}
