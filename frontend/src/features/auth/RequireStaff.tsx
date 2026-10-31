/*
  Staff-only routes.

  Sends anyone signed out to the login screen and back again afterwards.
  This is for the person's convenience: the API refuses the data either
  way, so it is not what keeps these screens private.
*/

import { Navigate, Outlet, useLocation } from "react-router-dom";

import AppShell from "../../components/AppShell";
import PresentShell from "../../components/PresentShell";
import { ErrorMessage, LoadingMessage } from "../../components/StateMessage";
import { useSession } from "./session";

/*
  `chrome={false}` keeps the sign-in check and drops the shell, for the
  screens a customer is handed the device on. Spec.md F06: the customer
  sees their document "and nothing else — no margins, no other
  customers, no staff navigation".
*/
export default function RequireStaff({ chrome = true }: { chrome?: boolean }) {
  const location = useLocation();
  const { data, isPending, isError, error, refetch } = useSession();

  if (isPending) return <LoadingMessage label="Loading…" />;
  if (isError) return <ErrorMessage error={error} onRetry={refetch} />;

  if (!data.user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  if (chrome) return <AppShell user={data.user} />;

  return (
    <PresentShell>
      <Outlet />
    </PresentShell>
  );
}
