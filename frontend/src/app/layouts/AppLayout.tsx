import { Outlet } from "react-router-dom";

import { DemoBanner } from "@/components/layout/DemoBanner";
import { Header } from "@/components/layout/Header";

export function AppLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <DemoBanner />
      <Header />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
        <Outlet />
      </main>
      <footer className="border-t border-line bg-surface">
        <p className="mx-auto max-w-5xl px-4 py-4 text-xs text-ink-muted">
          All names and records in this prototype are fictional demo data.
        </p>
      </footer>
    </div>
  );
}
