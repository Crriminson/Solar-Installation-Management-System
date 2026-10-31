/*
  Application entry point.

  Starts React and wraps the app in the two providers every screen needs:

  - QueryClientProvider: caches server data and handles loading/error
    state, so screens do not each write their own fetch logic.
  - BrowserRouter: makes the URL drive which screen is shown.
*/

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { ApiError, isForbidden } from "./api/client";
import { IconDefaults, ICON_SIZE } from "./design/icons";
import { SESSION_QUERY_KEY } from "./features/auth/session";
import "./styles/global.css";

/* Icons inherit the colour of the text they sit beside, and are
   decorative unless a component says otherwise. Set once, so no screen
   has to repeat it. */
const ICON_DEFAULTS = {
  color: "currentColor",
  size: ICON_SIZE.control,
  weight: "regular",
} as const;

// Server data is considered fresh for 30 seconds before refetching.
const STALE_TIME_MS = 30_000;

// A failed read is retried this many times, for a dropped connection.
const MAX_RETRIES = 2;
const STATUS_SERVER_ERROR = 500;

/* Asking again will not change a refusal, so only network and server
   failures are retried. */
function shouldRetry(failureCount: number, error: unknown) {
  const isRefusal = error instanceof ApiError && error.status < STATUS_SERVER_ERROR;
  return !isRefusal && failureCount < MAX_RETRIES;
}

const queryClient: QueryClient = new QueryClient({
  // A refused read may mean the session expired, so check it. Signing
  // out again from here sends the person to the login screen.
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (isForbidden(error) && query.queryKey[0] !== SESSION_QUERY_KEY[0]) {
        queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
      }
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: STALE_TIME_MS,
      refetchOnWindowFocus: false,
      retry: shouldRetry,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <IconDefaults.Provider value={ICON_DEFAULTS}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </IconDefaults.Provider>
    </QueryClientProvider>
  </StrictMode>,
);
