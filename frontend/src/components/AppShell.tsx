/*
  The frame around every staff screen.

  A sidebar on a desk, and a bottom bar on a phone, where it is within
  reach of one thumb. Both show only what the person's roles can use,
  in workflow order.

  The bottom bar holds the first few destinations and moves the rest
  into More, because a bar with fifteen items in it cannot be hit. An
  administrator sees every item, so this is the normal case, not an
  edge one.
*/

import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  AccountIcon,
  CaretLeftIcon,
  CaretRightIcon,
  MoreIcon,
  SignOutIcon,
  ICON_SIZE,
} from "../design/icons";
import { logout, type StaffUser } from "../features/auth/session";
import { NAV_SECTIONS, PHONE_BAR_LIMIT, type NavItem, type NavSection } from "../navigation";
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
  // Collapsing is for this session only. It is a preference about the
  // screen in front of you, not a setting worth storing.
  const [railed, setRailed] = useState(false);

  const sections = visibleSections(user);
  const items = sections.flatMap((section) => section.items);
  const barItems = items.slice(0, PHONE_BAR_LIMIT);

  return (
    <div className={`${styles.shell} ${railed ? styles.shellRailed : ""}`}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <BrandMark compact={railed} />
        </div>

        <nav className={styles.nav} aria-label="Main">
          {sections.map((section) => (
            <div key={section.title} className={styles.section}>
              {section.title && <p className={styles.sectionTitle}>{section.title}</p>}
              {section.items.map((item) => (
                <SidebarLink key={item.to} item={item} railed={railed} />
              ))}
            </div>
          ))}
        </nav>

        <button
          type="button"
          className={styles.railToggle}
          aria-pressed={railed}
          onClick={() => setRailed((on) => !on)}
        >
          {railed ? <CaretRightIcon aria-hidden /> : <CaretLeftIcon aria-hidden />}
          <span className={styles.linkLabel}>Collapse</span>
        </button>
      </aside>

      <div className={styles.frame}>
        <header className={styles.header}>
          <Breadcrumbs items={items} />
          <AccountMenu user={user} />
        </header>

        <main className={styles.content}>
          <Outlet />
        </main>
      </div>

      <nav className={styles.phoneBar} aria-label="Main">
        {barItems.map((item) => (
          <NavLink key={item.to} to={item.to} className={phoneLinkClass}>
            <item.icon size={ICON_SIZE.control} aria-hidden />
            {item.label}
          </NavLink>
        ))}

        <button type="button" className={styles.phoneLink} popoverTarget="nav-more">
          <MoreIcon size={ICON_SIZE.control} aria-hidden />
          More
        </button>
      </nav>

      <MoreSheet sections={sections} user={user} />
    </div>
  );
}


// ============================================================
// Sidebar
// ============================================================

function SidebarLink({ item, railed }: { item: NavItem; railed: boolean }) {
  return (
    <NavLink
      to={item.to}
      className={linkClass}
      /* In the rail the label is hidden, so the icon needs a name. */
      title={railed ? item.label : undefined}
    >
      <item.icon size={ICON_SIZE.control} aria-hidden />
      <span className={styles.linkLabel}>{item.label}</span>
    </NavLink>
  );
}


// ============================================================
// Header
// ============================================================

/* Where you are, as the trail of navigation that reaches this screen.
   A record's own reference is its page title, not a crumb, because the
   shell does not know what the record is called. */
function Breadcrumbs({ items }: { items: readonly NavItem[] }) {
  const { pathname } = useLocation();
  const current = items.find(
    (item) => pathname === item.to || pathname.startsWith(`${item.to}/`),
  );

  if (!current) return <p className={styles.crumbs} />;

  const isRecord = pathname !== current.to;

  return (
    <nav className={styles.crumbs} aria-label="Breadcrumb">
      {isRecord ? (
        <>
          <NavLink to={current.to} className={styles.crumbLink}>
            {current.label}
          </NavLink>
          <CaretRightIcon size={ICON_SIZE.inline} aria-hidden />
          <span className={styles.crumbHere}>Record</span>
        </>
      ) : (
        <span className={styles.crumbHere}>{current.label}</span>
      )}
    </nav>
  );
}

function AccountMenu({ user }: { user: StaffUser }) {
  return (
    <>
      <button
        type="button"
        className={styles.accountButton}
        popoverTarget="account-menu"
        aria-label={`Account: ${user.name}`}
      >
        <AccountIcon size={ICON_SIZE.section} aria-hidden />
        <span className={styles.accountButtonName}>{user.name}</span>
      </button>

      <div id="account-menu" popover="auto" className={styles.accountMenu}>
        <p className={styles.accountName}>{user.name}</p>
        <p className={styles.accountRole}>{roleLabel(user)}</p>
        <SignOutButton />
      </div>
    </>
  );
}


// ============================================================
// Phone
// ============================================================

/* Everything the bottom bar could not hold, plus sign out. */
function MoreSheet({
  sections,
  user,
}: {
  sections: readonly NavSection[];
  user: StaffUser;
}) {
  return (
    <div id="nav-more" popover="auto" className={styles.sheet}>
      <p className={styles.sheetName}>{user.name}</p>
      <p className={styles.sheetRole}>{roleLabel(user)}</p>

      {sections.map((section) => (
        <div key={section.title} className={styles.sheetSection}>
          {section.title && <p className={styles.sectionTitle}>{section.title}</p>}
          {section.items.map((item) => (
            <NavLink key={item.to} to={item.to} className={styles.sheetLink}>
              <item.icon size={ICON_SIZE.control} aria-hidden />
              {item.label}
            </NavLink>
          ))}
        </div>
      ))}

      <SignOutButton className={styles.sheetSignOut} />
    </div>
  );
}


// ============================================================
// Helpers
// ============================================================

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
      icon={<SignOutIcon aria-hidden />}
      loading={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      Sign out
    </Button>
  );
}

function visibleSections(user: StaffUser): NavSection[] {
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => canSee(item, user)),
  })).filter((section) => section.items.length > 0);
}

function canSee(item: NavItem, user: StaffUser) {
  return (
    item.roles.length === 0 ||
    user.is_administrator ||
    item.roles.some((role) => user.roles.includes(role))
  );
}

function roleLabel(user: StaffUser) {
  const roles = user.roles.map((role) => ROLE_LABELS[role] ?? role).join(", ");
  return roles || (user.is_administrator ? "Administrator" : "No role yet");
}

function linkClass({ isActive }: { isActive: boolean }) {
  return isActive ? `${styles.link} ${styles.linkActive}` : styles.link;
}

function phoneLinkClass({ isActive }: { isActive: boolean }) {
  return isActive ? `${styles.phoneLink} ${styles.phoneLinkActive}` : styles.phoneLink;
}
