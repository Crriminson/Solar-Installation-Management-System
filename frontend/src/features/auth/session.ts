/* Who is signed in, and how to sign in and out. */

import { useQuery } from "@tanstack/react-query";

import { apiGet, apiPost } from "../../api/client";

export interface StaffUser {
  id: number;
  name: string;
  roles: string[];
  is_administrator: boolean;
  can_approve_surveys: boolean;
  can_manage_catalogue: boolean;
  can_review_packages: boolean;
  can_view_costs: boolean;
}

interface Session {
  user: StaffUser | null;
}

export const SESSION_QUERY_KEY = ["session"];

function fetchSession() {
  return apiGet<Session>("auth/session/");
}

export function login(credentials: { username: string; password: string }) {
  return apiPost<Session>("auth/login/", credentials);
}

export function logout() {
  return apiPost<void>("auth/logout/");
}

/* Reading the session also sets the CSRF cookie that login needs. */
export function useSession() {
  return useQuery({ queryKey: SESSION_QUERY_KEY, queryFn: fetchSession });
}

/* The signed-in person. Only for screens inside RequireStaff. */
export function useStaffUser() {
  return useSession().data!.user!;
}

export function hasRole(user: StaffUser, role: string) {
  return user.is_administrator || user.roles.includes(role);
}
