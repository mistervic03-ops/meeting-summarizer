import { ActionItem } from "../api/types";
import EmptySection from "./ui/EmptySection";
import { normalizeDisplayText } from "../utils/displayText";

/**
 * Renders one action item card with owner, due date, and confidence state.
 */
function ActionItemCard({ isQuiet, item }: { isQuiet?: boolean; item: ActionItem }) {
  const owner = item.owner?.trim() || "담당자 미지정";
  const dueDate = item.due_date?.trim() || "기한 미정";
  const task = normalizeDisplayText(item.task);
  const hasOwner = Boolean(item.owner?.trim());
  const hasDueDate = Boolean(item.due_date?.trim());
  const isLowConfidence = item.confidence === "low";

  return (
    <article
      className={[
        "border-b border-slate-200 px-1 transition-colors duration-150 ease-out last:border-b-0 hover:bg-white/65 dark:border-app-line dark:hover:bg-app-hover",
        isQuiet ? "py-2.5" : "py-3"
      ].join(" ")}
    >
      <div className="grid gap-2.5 lg:grid-cols-[minmax(0,1fr)_132px_132px_76px] lg:items-start">
        <div className="min-w-0">
          <p className="mb-0.5 text-[11px] font-medium text-slate-400 dark:text-app-subtle lg:hidden">할 일</p>
          <h2 className={`break-words font-semibold leading-[1.58] text-slate-950 dark:text-app-text ${isQuiet ? "text-[13px]" : "text-[14px]"}`}>{task}</h2>
        </div>

        <div className="min-w-0">
          <p className="mb-0.5 text-[11px] font-medium text-slate-400 dark:text-app-subtle lg:hidden">담당자</p>
          <span
            className={[
              "block max-w-full min-w-0 break-words text-[13px] leading-[1.55]",
              hasOwner ? "text-slate-600 dark:text-app-muted" : "font-semibold text-amber-700 dark:text-app-warning"
            ].join(" ")}
          >
            {owner}
          </span>
        </div>

        <div className="min-w-0">
          <p className="mb-0.5 text-[11px] font-medium text-slate-400 dark:text-app-subtle lg:hidden">기한</p>
          <span
            className={[
              "block max-w-full min-w-0 break-words text-[13px] leading-[1.55]",
              hasDueDate ? "text-slate-600 dark:text-app-muted" : "font-semibold text-amber-700 dark:text-app-warning"
            ].join(" ")}
          >
            {dueDate}
          </span>
        </div>

        <div className="min-w-0">
          <p className="mb-0.5 text-[11px] font-medium text-slate-400 dark:text-app-subtle lg:hidden">상태</p>
          <span
            className={[
              "inline-flex rounded-md border px-1.5 py-0.5 text-[11px] font-medium",
              isLowConfidence
                ? "border-amber-200 bg-transparent text-amber-700 dark:border-app-warning-border dark:text-app-warning"
                : "border-slate-200 bg-transparent text-slate-500 dark:border-app-line dark:text-app-muted"
            ].join(" ")}
          >
            {isLowConfidence ? (isQuiet ? "확인" : "검토 필요") : "정리됨"}
          </span>
        </div>
      </div>
    </article>
  );
}

/**
 * Renders the action item tab.
 */
export default function ActionsTab({ isQuiet = false, items }: { isQuiet?: boolean; items: ActionItem[] }) {
  if (!items.length) {
    return (
      <section className="border-y border-slate-200 bg-transparent py-3 dark:border-app-line">
        <EmptySection message={isQuiet ? "명확한 액션 아이템이 없습니다." : "액션 아이템이 없습니다."} />
      </section>
    );
  }

  return (
    <section className={`${isQuiet ? "border-y border-slate-200 dark:border-app-line" : "border-y border-slate-300 dark:border-app-border"} bg-transparent`}>
      <div className="hidden grid-cols-[minmax(0,1fr)_132px_132px_76px] gap-2.5 border-b border-slate-200 px-1 py-2.5 text-[11px] font-semibold text-slate-500 dark:border-app-line dark:text-app-muted lg:grid">
        <span>할 일</span>
        <span>담당자</span>
        <span>기한</span>
        <span>상태</span>
      </div>
      {items.map((item, index) => (
        <ActionItemCard key={`${item.task}-${index}`} isQuiet={isQuiet} item={item} />
      ))}
    </section>
  );
}
