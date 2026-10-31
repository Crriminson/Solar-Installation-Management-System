/*
  Staff-only routes.

  Sends anyone signed out to the login screen and back again afterwards.
  This is for the person's convenience: the API refuses the data either
  way, so it is not what keeps these screens private.
*/

import { Navigate, useLocation } from "react-router-dom";

import AppShell from "../../components/AppShell";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { useSession } from "./session";

export default function RequireStaff() {
  const location = useLocation();
  const { data, isPending, isError, error, refetch } = useSession();

  if (isPending) return <LoadingMessage label="Loading…" />;
  if (isError) return <ErrorMessage error={error} onRetry={refetch} />;

  if (!data.user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return <AppShell user={data.user} />;
}
