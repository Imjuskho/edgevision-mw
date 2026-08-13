import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../hooks/useAuth";
import { LoadingOverlay } from "../components/Spinner";
import type { View } from "./paths";
import { canAccessView, isAdminRole } from "../utils/roles";

export function AdminRoute({ children }: { children: ReactNode }) {
  const { user, isAuthenticated } = useAuth();

  if (isAuthenticated && user === null) {
    return <LoadingOverlay message="Loading..." />;
  }

  if (!isAdminRole(user?.role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export function RoleRoute({ view, children }: { view: View; children: ReactNode }) {
  const { user, isAuthenticated } = useAuth();

  if (isAuthenticated && user === null) {
    return <LoadingOverlay message="Loading..." />;
  }

  if (!canAccessView(user?.role, view)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export function useIsAdmin(): boolean {
  const { user } = useAuth();
  return isAdminRole(user?.role);
}
