/** Persistent prototype disclaimer shown on every page. */
export function DemoBanner() {
  return (
    <div role="note" className="border-b border-amber-200 bg-amber-50 text-amber-900">
      <p className="mx-auto max-w-5xl px-4 py-2 text-center text-xs sm:text-sm">
        <strong className="font-semibold">Prototype · Demo data only.</strong> This is a
        proposed/prototype research platform and is not an official LPU system unless formally
        adopted or authorized.
      </p>
    </div>
  );
}
