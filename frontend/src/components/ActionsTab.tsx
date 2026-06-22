import { ActionItem } from "../api/types";
import EmptySection from "./ui/EmptySection";
import { normalizeDisplayText } from "../utils/displayText";

/**
 * Renders one action item card with owner, due date, and confidence state.
 */
function ActionItemCard({ isQuiet, item }: { isQuiet?: boolean; item: ActionItem }) {
  const owner = getMeaningfulMetadata(item.owner);
  const dueDate = getMeaningfulMetadata(item.due_date);
  const task = normalizeDisplayText(item.task);
  const isLowConfidence = item.confidence === "low";

  return (
    <article
      className={[
        "border-b border-slate-200 px-1 transition-colors duration-150 ease-out last:border-b-0 hover:bg-white/65 dark:border-app-line dark:hover:bg-app-hover",
        isQuiet ? "py-2.5" : "py-3"
      ].join(" ")}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <h2 className={`break-words font-semibold leading-[1.58] text-slate-950 dark:text-app-text ${isQuiet ? "text-[13px]" : "text-[14px]"}`}>{task}</h2>
          {owner || dueDate ? (
            <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[12px] leading-5 text-slate-500 dark:text-app-muted">
              {owner ? (
                <span className="min-w-0 break-words">
                  <span className="text-slate-400 dark:text-app-subtle">담당자</span> {owner}
                </span>
              ) : null}
              {dueDate ? (
                <span className="min-w-0 break-words">
                  <span className="text-slate-400 dark:text-app-subtle">기한</span> {dueDate}
                </span>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="shrink-0">
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
      {items.map((item, index) => (
        <ActionItemCard key={`${item.task}-${index}`} isQuiet={isQuiet} item={item} />
      ))}
    </section>
  );
}

function getMeaningfulMetadata(value?: string): string {
  const normalizedValue = normalizeDisplayText(value ?? "");
  const key = normalizedValue.replace(/\s+/g, "").toLowerCase();
  if (!key || ["미정", "검토필요", "확인필요"].includes(key)) {
    return "";
  }
  return normalizedValue;
}
