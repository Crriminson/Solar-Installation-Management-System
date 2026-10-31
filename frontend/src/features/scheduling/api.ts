/* Scheduling calls. */

import { apiGet, apiPost } from "../../api/client";
import type { Paginated } from "../enquiries/types";
import type { Job } from "./types";

export function fetchJobs(params: URLSearchParams) {
  return apiGet<Paginated<Job>>(`jobs/?${params}`);
}

export function fetchJob(id: string) {
  return apiGet<Job>(`jobs/${id}/`);
}

export function createJob(data: Record<string, unknown>) {
  return apiPost<Job>("jobs/create/", data);
}

export function rescheduleJob(job: Job, data: {
  starts_at: string; ends_at: string; reason: string;
}) {
  return apiPost<Job>(`jobs/${job.id}/reschedule/`, { revision: job.revision, ...data });
}

export function blockJob(job: Job, reason: string, owner: number) {
  return apiPost<Job>(`jobs/${job.id}/block/`, {
    revision: job.revision, reason, owner,
  });
}

export function startJob(job: Job) {
  return apiPost<Job>(`jobs/${job.id}/start/`, { revision: job.revision });
}

export function cancelJob(job: Job, reason: string) {
  return apiPost<Job>(`jobs/${job.id}/cancel/`, { revision: job.revision, reason });
}
