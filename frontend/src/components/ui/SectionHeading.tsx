/**
 * Renders a section heading with an optional item count.
 */
export default function SectionHeading({ count, title }: { count?: number; title: string }) {
  return (
    <div className="mb-3.5 flex items-center justify-between gap-3">
      <h2 className="min-w-0 text-[14px] font-semibold leading-5 text-slate-950 dark:text-app-text">{title}</h2>
      {typeof count === "number" ? <span className="shrink-0 text-[11px] font-semibold text-slate-500 dark:text-app-muted">{count}</span> : null}
    </div>
  );
}
