/* The director's figures (F15). Read-only. */

import { apiGet } from "../../api/client";

export type MetricKind = "count" | "money" | "hours";

export interface MetricCard {
  key: string;
  label: string;
  caption: string;
  kind: MetricKind;
  value: number | string;
  records: number;
}

export interface MetricRow {
  reference: string;
  label: string;
  detail: string;
  url: string;
  date: string | null;
  amount: string | null;
}

export interface Dashboard {
  period: { key: string; from: string; to: string; label: string };
  groups: { title: string; cards: MetricCard[] }[];
  jobs: MetricRow[];
}

export interface MetricRows {
  key: string;
  label: string;
  caption: string;
  kind: MetricKind;
  period: string;
  rows: MetricRow[];
}

export function fetchDashboard(params: URLSearchParams) {
  return apiGet<Dashboard>(`dashboard/?${params}`);
}

export function fetchMetric(key: string, params: URLSearchParams) {
  return apiGet<MetricRows>(`dashboard/metrics/${key}/?${params}`);
}

/* Plain links, so the browser downloads with the session it already has. */
export function metricCsvUrl(key: string, params: URLSearchParams) {
  return `/api/v1/dashboard/export/${key}.csv?${params}`;
}

export function summaryPdfUrl(params: URLSearchParams) {
  return `/api/v1/dashboard/export/summary.pdf?${params}`;
}
