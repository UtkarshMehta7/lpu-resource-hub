import { Outlet } from "react-router-dom";

import { DemoBanner } from "@/components/layout/DemoBanner";
import {
  Monogram,
  PRODUCT_NAME,
  UNIVERSITY_NAME,
  UNIVERSITY_SHORT,
} from "@/components/layout/Brand";
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
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3 px-4 py-4">
          <Monogram className="size-7 text-[10px]" />
          <p className="text-xs text-ink-muted">
            <span className="font-medium text-ink">{UNIVERSITY_NAME}</span> · {PRODUCT_NAME} (
            {UNIVERSITY_SHORT} prototype). Not an official {UNIVERSITY_SHORT} system unless formally
            adopted. All names and records shown are fictional demo data.
          </p>
        </div>
      </footer>
    </div>
  );
}
