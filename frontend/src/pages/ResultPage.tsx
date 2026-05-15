import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  Clipboard,
  Copy,
  Download,
  FileText,
  MessageSquareText,
  UserRound
} from "lucide-react";
import { ActionItem, Decision, JobResult } from "../api/types";

type ResultTab = "summary" | "actions" | "minutes";

interface ResultPageProps {
  filename?: string;
  meetingDate?: string;
  result?: JobResult;
  onCopy?: (minutes: string) => void;
  onDownload?: () => void;
}

const EMPTY_RESULT: JobResult = {
  job_id: "preview",
  filename: "회의 녹음 파일",
  minutes: "",
  action_items: [],
  summary_facts: [],
  decisions: [],
  speaker_highlights: [],
  warnings: []
};

const TABS: Array<{ id: ResultTab; label: string }> = [
  { id: "summary", label: "요약" },
  { id: "actions", label: "액션 아이템" },
  { id: "minutes", label: "전체 회의록" }
];

/**
 * Returns today's date as a compact Korean display label.
 */
function getDefaultMeetingDate(): string {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium"
  }).format(new Date());
}

/**
 * Copies text to the clipboard when browser permissions allow it.
 */
async function copyToClipboard(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

/**
 * Renders a small placeholder when a result section has no items.
 */
function EmptySection({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-5 py-8 text-center text-sm font-medium text-slate-500">
      {message}
    </div>
  );
}

/**
 * Renders a section heading with an optional item count.
 */
function SectionHeading({ count, title }: { count?: number; title: string }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h2 className="text-lg font-bold text-slate-950">{title}</h2>
      {typeof count === "number" ? (
        <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-bold text-brand-600">{count}</span>
      ) : null}
    </div>
  );
}

/**
 * Renders the decision status badge in the summary tab.
 */
function DecisionBadge({ status }: { status: Decision["status"] }) {
  const className =
    status === "확정" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700";

  return <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${className}`}>{status}</span>;
}

/**
 * Renders the summary tab with facts, decisions, speakers, and warnings.
 */
function SummaryTab({ result }: { result: JobResult }) {
  const summaryFacts = result.summary_facts ?? [];
  const decisions = result.decisions ?? [];
  const speakerHighlights = result.speaker_highlights ?? [];
  const warnings = result.warnings ?? [];

  return (
    <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <SectionHeading count={summaryFacts.length} title="빠른 요약" />
        {summaryFacts.length ? (
          <div className="grid gap-3">
            {summaryFacts.map((fact) => (
              <article key={fact} className="rounded-lg border border-brand-100 bg-brand-50/60 p-4">
                <p className="text-sm leading-6 text-slate-800">{fact}</p>
              </article>
            ))}
          </div>
        ) : (
          <EmptySection message="빠른 요약이 없습니다." />
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <SectionHeading count={decisions.length} title="주요 결정사항" />
        {decisions.length ? (
          <div className="space-y-3">
            {decisions.map((decision) => (
              <article key={`${decision.status}-${decision.decision}`} className="rounded-lg border border-slate-200 p-4">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-semibold leading-6 text-slate-900">{decision.decision}</p>
                  <DecisionBadge status={decision.status} />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptySection message="주요 결정사항이 없습니다." />
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm sm:p-6 xl:col-span-2">
        <SectionHeading count={speakerHighlights.length} title="주요 발언 요약" />
        {speakerHighlights.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {speakerHighlights.map((highlight) => (
              <article key={highlight} className="flex gap-3 rounded-lg border border-slate-200 p-4">
                <MessageSquareText className="mt-0.5 shrink-0 text-brand-500" size={19} />
                <p className="text-sm leading-6 text-slate-700">{highlight}</p>
              </article>
            ))}
          </div>
        ) : (
          <EmptySection message="주요 발언 요약이 없습니다." />
        )}
      </section>

      {warnings.length ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-5 sm:p-6 xl:col-span-2">
          <SectionHeading count={warnings.length} title="확인 필요" />
          <div className="space-y-3">
            {warnings.map((warning) => (
              <div key={warning} className="flex gap-3 rounded-lg bg-white/70 p-4 text-sm leading-6 text-amber-900">
                <AlertTriangle className="mt-0.5 shrink-0 text-amber-600" size={18} />
                <p>{warning}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

/**
 * Renders one action item card with owner, due date, and confidence state.
 */
function ActionItemCard({ item }: { item: ActionItem }) {
  const owner = item.owner?.trim() || "담당자 미지정";
  const dueDate = item.due_date?.trim() || "기한 미정";
  const hasOwner = Boolean(item.owner?.trim());
  const hasDueDate = Boolean(item.due_date?.trim());

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex gap-3">
          <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand-100 text-brand-600">
            <CheckCircle2 size={20} />
          </div>
          <div>
            <h2 className="text-base font-bold leading-6 text-slate-950">{item.task}</h2>
            {item.confidence === "low" ? (
              <p className="mt-2 text-xs font-semibold text-slate-400">낮은 신뢰도</p>
            ) : null}
          </div>
        </div>

        <div className="grid gap-2 sm:min-w-48">
          <span
            className={[
              "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold",
              hasOwner ? "bg-brand-50 text-brand-700" : "bg-slate-100 text-slate-400"
            ].join(" ")}
          >
            <UserRound size={16} />
            {owner}
          </span>
          <span
            className={[
              "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold",
              hasDueDate ? "bg-slate-100 text-slate-700" : "bg-slate-100 text-slate-400"
            ].join(" ")}
          >
            <CalendarDays size={16} />
            {dueDate}
          </span>
        </div>
      </div>
    </article>
  );
}

/**
 * Renders the action item tab.
 */
function ActionsTab({ items }: { items: ActionItem[] }) {
  if (!items.length) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <EmptySection message="액션 아이템이 없습니다." />
      </section>
    );
  }

  return (
    <section className="space-y-4">
      {items.map((item, index) => (
        <ActionItemCard key={`${item.task}-${index}`} item={item} />
      ))}
    </section>
  );
}

/**
 * Renders the full minutes tab with markdown formatting.
 */
function MinutesTab({ minutes }: { minutes: string }) {
  if (!minutes.trim()) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <EmptySection message="전체 회의록이 없습니다." />
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
      <ReactMarkdown
        components={{
          h1: ({ children }) => <h1 className="mb-4 text-2xl font-bold text-slate-950">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-3 mt-6 text-xl font-bold text-slate-950">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-2 mt-5 text-lg font-bold text-slate-900">{children}</h3>,
          li: ({ children }) => <li className="ml-5 list-disc leading-7 text-slate-700">{children}</li>,
          p: ({ children }) => <p className="mb-4 leading-7 text-slate-700">{children}</p>,
          strong: ({ children }) => <strong className="font-bold text-slate-950">{children}</strong>
        }}
      >
        {minutes}
      </ReactMarkdown>
    </section>
  );
}

/**
 * Renders the professional meeting result page with summary, action, and full-minutes tabs.
 */
export default function ResultPage({
  filename,
  meetingDate,
  result = EMPTY_RESULT,
  onCopy,
  onDownload
}: ResultPageProps) {
  const [activeTab, setActiveTab] = useState<ResultTab>("summary");
  const title = filename || result.filename || "회의록";
  const dateLabel = meetingDate || getDefaultMeetingDate();
  const actionItems = result.action_items ?? [];
  const factsCount = result.summary_facts?.length ?? 0;
  const decisionsCount = result.decisions?.length ?? 0;

  const tabPanel = useMemo(() => {
    if (activeTab === "actions") {
      return <ActionsTab items={actionItems} />;
    }

    if (activeTab === "minutes") {
      return <MinutesTab minutes={result.minutes} />;
    }

    return <SummaryTab result={result} />;
  }, [activeTab, actionItems, result]);

  /**
   * Copies the full minutes text and allows callers to hook into the action.
   */
  async function handleCopy() {
    await copyToClipboard(result.minutes);
    onCopy?.(result.minutes);
  }

  return (
    <main className="min-h-screen bg-[#F6F4F8] px-4 py-6 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-6xl">
        <header className="rounded-lg border border-white/70 bg-white p-5 shadow-card sm:p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="mb-3 flex items-center gap-3">
                <div className="grid size-10 place-items-center rounded-lg bg-brand-500 text-white shadow-lg shadow-brand-500/25">
                  <FileText size={20} />
                </div>
                <span className="text-sm font-bold text-brand-600">BigxData 회의록</span>
              </div>
              <h1 className="truncate text-2xl font-bold tracking-normal text-slate-950 sm:text-3xl">{title}</h1>
              <p className="mt-2 flex items-center gap-2 text-sm font-medium text-slate-500">
                <CalendarDays size={16} />
                {dateLabel}
              </p>
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-700 transition hover:border-brand-200 hover:text-brand-600"
                type="button"
                onClick={handleCopy}
              >
                <Copy size={17} />
                복사
              </button>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-brand-500 px-4 text-sm font-bold text-white shadow-lg shadow-brand-500/25 transition hover:bg-brand-600"
                type="button"
                onClick={onDownload}
              >
                <Download size={17} />
                다운로드
              </button>
            </div>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg bg-slate-50 px-4 py-3">
              <p className="text-xs font-semibold text-slate-500">빠른 요약</p>
              <p className="mt-1 text-lg font-bold text-slate-950">{factsCount}</p>
            </div>
            <div className="rounded-lg bg-slate-50 px-4 py-3">
              <p className="text-xs font-semibold text-slate-500">결정사항</p>
              <p className="mt-1 text-lg font-bold text-slate-950">{decisionsCount}</p>
            </div>
            <div className="rounded-lg bg-slate-50 px-4 py-3">
              <p className="text-xs font-semibold text-slate-500">액션 아이템</p>
              <p className="mt-1 text-lg font-bold text-slate-950">{actionItems.length}</p>
            </div>
          </div>
        </header>

        <nav className="mt-6 overflow-x-auto rounded-lg border border-slate-200 bg-white p-1 shadow-sm" aria-label="결과 탭">
          <div className="grid min-w-max grid-cols-3 gap-1">
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id;

              return (
                <button
                  key={tab.id}
                  className={[
                    "h-11 rounded-lg px-5 text-sm font-bold transition",
                    isActive ? "bg-brand-500 text-white shadow-lg shadow-brand-500/20" : "text-slate-500 hover:bg-brand-50 hover:text-brand-600"
                  ].join(" ")}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </nav>

        <section className="mt-6 pb-10">{tabPanel}</section>

        <div className="fixed bottom-5 right-5 hidden rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-500 shadow-lg lg:flex">
          <Clipboard className="mr-2 text-brand-500" size={15} />
          결과 검토 모드
        </div>
      </div>
    </main>
  );
}
