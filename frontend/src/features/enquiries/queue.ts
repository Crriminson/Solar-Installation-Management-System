/* Shared settings for screens that show the sales queue. */

/* A queue stays open all day, so it checks for new work by itself.
   Polling rather than a live socket, per spec.md section 3.3. */
export const QUEUE_REFRESH_MS = 60_000;
