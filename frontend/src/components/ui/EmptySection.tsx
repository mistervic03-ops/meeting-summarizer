/**
 * Renders a small placeholder when a result section has no items.
 */
export default function EmptySection({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-dashed border-slate-300 bg-white px-4 py-3 text-center text-sm font-medium text-slate-500 dark:bg-app-surface">
      {message}
    </div>
  );
}
