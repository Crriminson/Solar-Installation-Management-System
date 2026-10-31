/*
  Talks to the Django API.

  Every network call in the app goes through here, so there is one place
  that knows about URLs, CSRF tokens and error handling.

  Django protects unsafe requests with a CSRF token stored in a cookie.
  We read that cookie and send it back in a header.
*/

const API_BASE = "/api/v1";

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

  path is relative to /api/v1, for example "enquiries/".
*/
export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const csrfToken = readCookie("csrftoken");

  const response = await fetch(`${API_BASE}/${path}`, {
    ...options,
    credentials: "same-origin",       // send the session cookie
    headers: {
      "Content-Type": "application/json",
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

/* Convenience wrappers so screens read clearly. */

export function apiGet<T>(path: string) {
  return apiRequest<T>(path);
}

export function apiPost<T>(path: string, data: unknown) {
  return apiRequest<T>(path, { method: "POST", body: JSON.stringify(data) });
}
