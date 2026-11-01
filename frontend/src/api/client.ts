/*
  Talks to the Django API.

  Every network call in the app goes through here, so there is one place
  that knows about URLs, CSRF tokens and error handling.

  Django protects unsafe requests with a CSRF token stored in a cookie.
  We read that cookie and send it back in a header.
*/

const API_BASE = "/api/v1";

const STATUS_FORBIDDEN = 403;
const STATUS_TOO_MANY_REQUESTS = 429;
const STATUS_SERVER_ERROR = 500;

/* Reads a cookie by name. Returns null when it is not set. */
function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
  return match ? decodeURIComponent(match[2]) : null;
}

/* Thrown when the API replies with an error status. */
export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(status: number, message: string, details: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

/*
  Makes a request and returns the parsed JSON body.

  path is relative to /api/v1, for example "enquiries/". A FormData body
  is sent as it is, so the browser can set the multipart boundary.
*/
export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const csrfToken = readCookie("csrftoken");
  const isUpload = options.body instanceof FormData;

  const response = await fetch(`${API_BASE}/${path}`, {
    ...options,
    credentials: "same-origin",       // send the session cookie
    headers: {
      ...(isUpload ? {} : { "Content-Type": "application/json" }),
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      ...options.headers,
    },
  });

  // 204 means success with no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(response.status, "Request failed", body);
  }

  return body as T;
}

/*
  Posts and hands back the open response, for a reply that arrives in
  pieces. Only a refusal is read here; the caller reads the rest.
*/
export async function apiStream(path: string, data: unknown, signal: AbortSignal) {
  const csrfToken = readCookie("csrftoken");

  const response = await fetch(`${API_BASE}/${path}`, {
    method: "POST",
    body: JSON.stringify(data),
    signal,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, "Request failed", body);
  }

  return response;
}

/* Convenience wrappers so screens read clearly. */

export function apiGet<T>(path: string) {
  return apiRequest<T>(path);
}

export function apiPost<T>(path: string, data?: unknown) {
  return apiRequest<T>(path, {
    method: "POST",
    body: data instanceof FormData ? data : JSON.stringify(data ?? {}),
  });
}

export function apiPatch<T>(path: string, data: unknown) {
  return apiRequest<T>(path, {
    method: "PATCH",
    body: data instanceof FormData ? data : JSON.stringify(data),
  });
}


// ============================================================
// Reading errors
// ============================================================

/* Field errors arrive from the API as { field: ["message"] }. */
export type FieldErrors = Record<string, string[]>;

/* Errors tied to one field. A { detail } reply is about the whole request. */
export function fieldErrorsFrom(error: unknown): FieldErrors {
  if (!(error instanceof ApiError) || !isPlainObject(error.details)) return {};

  return Object.fromEntries(
    Object.entries(error.details).filter(
      ([key, value]) => key !== "detail" && Array.isArray(value),
    ),
  ) as FieldErrors;
}

/* One sentence for the person using the screen, never a raw failure. */
export function describeError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The connection dropped. Check your network and try again.";
  }

  if (error.status === STATUS_TOO_MANY_REQUESTS) {
    return "Too many attempts from this network. Please wait and try again.";
  }

  if (error.status >= STATUS_SERVER_ERROR) {
    return "Something went wrong on our side. Please try again.";
  }

  if (isPlainObject(error.details)) {
    if (typeof error.details.detail === "string") return error.details.detail;

    const [firstMessages] = Object.values(fieldErrorsFrom(error));
    if (firstMessages?.[0]) return firstMessages[0];
  }

  if (error.status === STATUS_FORBIDDEN) {
    return "You do not have access to this.";
  }

  return "That could not be saved. Please check it and try again.";
}

export function isForbidden(error: unknown) {
  return error instanceof ApiError && error.status === STATUS_FORBIDDEN;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
