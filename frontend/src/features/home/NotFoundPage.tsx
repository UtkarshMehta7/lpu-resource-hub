import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="py-16 text-center">
      <p className="text-sm font-medium text-brand-700">404</p>
      <h1 className="mt-2 text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-ink-muted">The page you are looking for does not exist.</p>
      <Link
        to="/"
        className="mt-6 inline-block rounded-md bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800"
      >
        Back to home
      </Link>
    </section>
  );
}
