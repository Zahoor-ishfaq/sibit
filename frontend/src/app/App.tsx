import { lazy, Suspense } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState, PageSkeleton } from "@/components/common/States";
import { ToastProvider } from "@/components/common/Toast";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PrefsProvider } from "@/lib/prefs";
import { SessionProvider } from "@/lib/session";
import WelcomePage from "./WelcomePage";

const ProcessingPage = lazy(() => import("./ProcessingPage"));
const DashboardPage = lazy(() => import("./DashboardPage"));
const RulesPage = lazy(() => import("./RulesPage"));
const ObjectsPage = lazy(() => import("./ObjectsPage"));
const OrderPage = lazy(() => import("./OrderPage"));
const ReportsPage = lazy(() => import("./ReportsPage"));
const SettingsPage = lazy(() => import("./SettingsPage"));
const HitsPage = lazy(() => import("./HitsPage"));

function NotFound() {
  return (
    <EmptyState title="Page not found" className="h-full" action={<Button asChild size="sm"><Link to="/">New comparison</Link></Button>}>
      This page doesn't exist.
    </EmptyState>
  );
}

export default function App() {
  return (
    <PrefsProvider>
      <TooltipProvider>
        <ToastProvider>
          <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <Suspense fallback={<PageSkeleton />}>
              <Routes>
                <Route path="/s/:sid" element={<SessionProvider><AppShell /></SessionProvider>}>
                  <Route index element={<Navigate to="dashboard" replace />} />
                  <Route path="dashboard" element={<DashboardPage />} />
                  <Route path="rules" element={<RulesPage />} />
                  <Route path="objects" element={<ObjectsPage />} />
                  <Route path="order" element={<OrderPage />} />
                  <Route path="reports" element={<ReportsPage />} />
                </Route>
                <Route element={<AppShell />}>
                  <Route path="/" element={<WelcomePage />} />
                  <Route path="/processing/:jobId" element={<ProcessingPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/hits" element={<HitsPage />} />
                  <Route path="/hits/:hid" element={<HitsPage />} />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Routes>
            </Suspense>
          </BrowserRouter>
        </ToastProvider>
      </TooltipProvider>
    </PrefsProvider>
  );
}
