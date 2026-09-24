import { Link, Outlet } from "react-router-dom";

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
      <Header />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">
        <Outlet />
      </main>
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-4">
          <Monogram className="size-7 text-[10px]" />
          <p className="flex-1 text-xs text-ink-muted">
            <span className="font-medium text-ink">{UNIVERSITY_NAME}</span> · {PRODUCT_NAME} (
            {UNIVERSITY_SHORT} prototype). Not an official {UNIVERSITY_SHORT} system unless formally
            adopted. All names and records shown are fictional demo data.
          </p>
          {/* The administration entrance, findable without knowing the URL. */}
          <Link to="/admin/login" className="text-xs text-ink-muted hover:underline">
            Administration
          </Link>
        </div>
      </footer>
    </div>
  );
}
