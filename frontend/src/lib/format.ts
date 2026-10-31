/*
  One way to show each kind of value.

  Screens call these rather than formatting by hand, so a rupee amount
  or a date looks the same everywhere. Dates always use the business
  timezone, not the viewer's. See spec.md section 6 and design.md
  section 10.
*/

const BUSINESS_TIMEZONE = "Asia/Kolkata";
const LOCALE = "en-IN";
const MS_PER_DAY = 86_400_000;
const NATIONAL_PHONE_DIGITS = 10;
const PHONE_FIRST_GROUP = 5;

/* ₹3,00,000 — Indian digit grouping, and no paise on whole amounts. */
export function formatMoney(amount: string | number) {
  const value = Number(amount);

  return new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/* 3 kW, 28.5 m. The API sends "3.00", which is noise on a screen. */
export function formatQuantity(value: string | number, unit: string) {
  return `${Number(value)} ${unit}`;
}

/* 31 Oct 2026. Accepts a full timestamp or a plain date. */
export function formatDate(value: string) {
  return new Date(value).toLocaleDateString(LOCALE, {
    timeZone: BUSINESS_TIMEZONE,
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/* 2:30 pm */
export function formatTime(value: string | number | Date) {
  return new Date(value).toLocaleTimeString(LOCALE, {
    timeZone: BUSINESS_TIMEZONE,
    hour: "numeric",
    minute: "2-digit",
  });
}

/* 31 Oct 2026, 2:30 pm */
export function formatDateTime(value: string) {
  return `${formatDate(value)}, ${formatTime(value)}`;
}

/* 98765 43210, so a number can be read out on a call. */
export function formatPhone(phone: string) {
  if (phone.length !== NATIONAL_PHONE_DIGITS) return phone;
  return `${phone.slice(0, PHONE_FIRST_GROUP)} ${phone.slice(PHONE_FIRST_GROUP)}`;
}

/* Today's date in the business timezone, as YYYY-MM-DD. */
export function businessToday() {
  return new Date().toLocaleDateString("en-CA", { timeZone: BUSINESS_TIMEZONE });
}

/* Whole days a due date has passed. Zero or less means it has not. */
export function daysLate(dueDate: string) {
  const today = Date.parse(businessToday());
  return Math.round((today - Date.parse(dueDate)) / MS_PER_DAY);
}

/* "2 days late" */
export function describeLateness(dueDate: string) {
  const days = daysLate(dueDate);
  return `${days} ${days === 1 ? "day" : "days"} late`;
}

/* The current moment as a datetime-local value, in business time. */
export function nowForDateTimeInput() {
  const parts = new Date().toLocaleString("sv-SE", { timeZone: BUSINESS_TIMEZONE });
  return parts.slice(0, "YYYY-MM-DD HH:MM".length).replace(" ", "T");
}

/* A datetime-local value is read as Indian time, whatever the device says. */
export function dateTimeInputToIso(value: string) {
  return new Date(`${value}:00+05:30`).toISOString();
}
