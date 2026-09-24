/**
 * Routes:
 *   /    : landing site (marketing, 3D hero)
 *   /app : the SiliconMind workspace (FRONTEND_SPEC.md), lazy-loaded so the
 *           landing page doesn't ship the canvas/mock-backend code.
 */
import { lazy, Suspense, useEffect } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { LandingPage } from "./pages/LandingPage";

const WorkspacePage = lazy(() => import("./pages/WorkspacePage"));

function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) window.scrollTo(0, 0);
  }, [pathname, hash]);
  return null;
}

export function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route
          path="/app"
          element={
            <Suspense fallback={<div className="route-loading" role="status">Loading workspace…</div>}>
              <WorkspacePage />
            </Suspense>
          }
        />
        <Route path="*" element={<LandingPage />} />
      </Routes>
    </>
  );
}
