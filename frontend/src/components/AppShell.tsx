/*
  The frame around every staff screen.

  A sidebar on a desk, and a bottom bar on a phone, where it is within
  reach of one thumb. Both show only what the person's roles can use,
  in workflow order.
*/

import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { logout, type StaffUser } from "../features/auth/session";
import { NAV_SECTIONS, type NavItem } from "../navigation";
import BrandMark from "./BrandMark";
import Button from "./Button";
import styles from "./AppShell.module.css";

const ROLE_LABELS: Record<string, string> = {
  administrator: "Administrator",
  sales: "Sales",
  operations_manager: "Operations Manager",
  warehouse: "Warehouse",
  technician: "Technician",
  support: "Support",
  finance: "Finance",
  director: "Director",
};

export default function AppShell({ user }: { user: StaffUser }) {
  const sections = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => canSee(item, user)),
  })).filter((section) => section.items.length > 0);

  return (
    <div className={styles.shell}>
      <header className={styles.phoneTop}>
        <BrandMark />
      </header>

      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <BrandMark />
        </div>

        <nav className={styles.nav} aria-label="Main">
          {sections.map((section) => (
            <div key={section.title} className={styles.section}>
              {section.title && <p className={styles.sectionTitle}>{section.title}</p>}
              {section.items.map((item) => (
                <NavLink key={item.to} to={item.to} className={linkClass}>
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <Account user={user} />
      </aside>

      <main className={styles.content}>
        <Outlet />
      </main>

      <nav className={styles.phoneBar} aria-label="Main">
        {sections.flatMap((section) => section.items).map((item) => (
          <NavLink key={item.to} to={item.to} className={phoneLinkClass}>
            {item.label}
          </NavLink>
        ))}
        <SignOutButton className={styles.phoneSignOut} />
      </nav>
    </div>
  );
}


// ============================================================
// Helpers
// ============================================================

function Account({ user }: { user: StaffUser }) {
  const roles = user.roles.map((role) => ROLE_LABELS[role] ?? role).join(", ");

  return (
    <div className={styles.account}>
      <p className={styles.accountName}>{user.name}</p>
      <p className={styles.accountRole}>
        {roles || (user.is_administrator ? "Administrator" : "No role yet")}
      </p>
      <SignOutButton className={styles.signOut} />
    </div>
  );
}

function SignOutButton({ className }: { className?: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      // Nothing from this session should linger for the next person.
      queryClient.clear();
      navigate("/login");
    },
  });

  return (
    <Button
      className={className}
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      Sign out
    </Button>
  );
}

function canSee(item: NavItem, user: StaffUser) {
  return (
    item.roles.length === 0 ||
    user.is_administrator ||
    item.roles.some((role) => user.roles.includes(role))
  );
}

function linkClass({ isActive }: { isActive: boolean }) {
  return isActive ? `${styles.link} ${styles.linkActive}` : styles.link;
}

function phoneLinkClass({ isActive }: { isActive: boolean }) {
  return isActive ? `${styles.phoneLink} ${styles.phoneLinkActive}` : styles.phoneLink;
}
