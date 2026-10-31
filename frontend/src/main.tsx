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
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import "./styles/global.css";

// Server data is considered fresh for 30 seconds before refetching.
const STALE_TIME_MS = 30_000;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: STALE_TIME_MS, refetchOnWindowFocus: false },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
