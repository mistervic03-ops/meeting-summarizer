import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Decision, JobResult, MeetingType } from "../api/types";
import ActionsTab from "./ActionsTab";
import ContextHelp from "./ui/ContextHelp";
import EmptySection from "./ui/EmptySection";
import SectionHeading from "./ui/SectionHeading";
import { normalizeDisplayText } from "../utils/displayText";
import { getSummaryLabels, resolveMeetingType, splitDiscussionNotes, usesQuietActionTone } from "../utils/resultView";

const SUMMARY_FACT_PREVIEW_LIMIT = 6;

/**
 * Renders the decision status badge in the summary tab.
 */
function DecisionBadge({ status }: { status: Decision["status"] }) {
  const label = normalizeDisplayText(status);
  const className =
    status === "확정"
      ? "border-slate-200 bg-transparent text-slate-600 dark:border-app-line dark:text-app-muted"
      : "border-amber-200 bg-transparent text-amber-700 dark:border-app-warning-border dark:text-app-warning";

  return (
    <span className={`inline-flex min-w-9 shrink-0 items-center justify-center whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-none ${className}`}>
      {label}
    </span>
  );
}

function DecisionList({ decisions }: { decisions: Decision[] }) {
  return (
    <div className="border-y border-slate-300 dark:border-app-border">
      {decisions.map((decision) => (
        <article key={`${decision.status}-${decision.decision}`} className="border-b border-slate-200 py-3 last:border-b-0 dark:border-app-line">
          <div className="flex items-start justify-between gap-3">
            <p className="min-w-0 flex-1 break-words text-[13px] font-medium leading-[1.68] text-slate-900 dark:text-app-body">
              {normalizeDisplayText(decision.decision)}
            </p>
            <DecisionBadge status={decision.status} />
          </div>
        </article>
      ))}
    </div>
  );
}

/**
 * Renders the summary tab with facts, decisions, speakers, and warnings.
 */
export default function SummaryTab({
  discussionNotes,
  displayWarnings,
  meetingType,
  result,
  summaryFacts
}: {
  discussionNotes?: string[];
  displayWarnings?: string[];
  meetingType?: MeetingType;
  result: JobResult;
  summaryFacts?: string[];
}) {
  const [isSummaryExpanded, setIsSummaryExpanded] = useState(false);
  const resolvedMeetingType = resolveMeetingType(meetingType ?? result.meeting_type);
  const splitFacts = splitDiscussionNotes(result.summary_facts ?? []);
  const visibleSummaryFacts = summaryFacts ?? splitFacts.summaryFacts;
  const shouldCollapseSummary = visibleSummaryFacts.length > SUMMARY_FACT_PREVIEW_LIMIT;
  const displayedSummaryFacts =
    shouldCollapseSummary && !isSummaryExpanded ? visibleSummaryFacts.slice(0, SUMMARY_FACT_PREVIEW_LIMIT) : visibleSummaryFacts;
  const visibleDiscussionNotes = discussionNotes ?? splitFacts.discussionNotes;
  const actionItems = result.action_items ?? [];
  const decisions = result.decisions ?? [];
  const confirmedDecisions = decisions.filter((decision) => decision.status === "확정");
  const tentativeDecisions = decisions.filter((decision) => decision.status === "미확정");
  const speakerHighlights = result.speaker_highlights ?? [];
  const warnings = displayWarnings ?? result.warnings ?? [];
  const labels = getSummaryLabels(resolvedMeetingType);
  const sectionOrder = getSectionOrder(resolvedMeetingType);

  useEffect(() => {
    setIsSummaryExpanded(false);
  }, [result.job_id, visibleSummaryFacts.length]);

  const sectionMap = {
    actions: (
      <section key="actions">
        <SectionHeading count={actionItems.length} title="액션 아이템" />
        <ActionsTab isQuiet={usesQuietActionTone(resolvedMeetingType)} items={actionItems} />
      </section>
    ),
    decisions: decisions.length ? (
      <div key="decisions" className="space-y-7">
        {confirmedDecisions.length ? (
          <section>
            <SectionHeading count={confirmedDecisions.length} title="주요 결정사항" />
            <DecisionList decisions={confirmedDecisions} />
          </section>
        ) : null}
        {tentativeDecisions.length ? (
          <section>
            <SectionHeading count={tentativeDecisions.length} title="검토/논의된 방향" />
            <DecisionList decisions={tentativeDecisions} />
          </section>
        ) : null}
      </div>
    ) : null,
    notes: visibleDiscussionNotes.length ? (
      <section key="notes">
        <SectionHeading count={visibleDiscussionNotes.length} title={labels.discussionTitle} />
        <div className="border-y border-slate-200 dark:border-app-line">
          {visibleDiscussionNotes.map((note) => (
            <p key={note} className="break-words border-b border-slate-100 py-[9px] text-[13px] leading-[1.72] text-slate-600 last:border-b-0 dark:border-app-line dark:text-app-muted">
              {normalizeDisplayText(note)}
            </p>
          ))}
        </div>
      </section>
    ) : null,
    speakers: (
      <section key="speakers">
        <SectionHeading count={speakerHighlights.length} title={labels.speakerTitle} />
        {speakerHighlights.length ? (
          <div className="border-y border-slate-300 dark:border-app-border">
            {speakerHighlights.map((highlight) => (
              <p
                key={highlight}
                className="break-words border-b border-slate-100 py-[9px] text-[13px] leading-[1.72] text-slate-700 last:border-b-0 dark:border-app-line dark:text-app-body"
              >
                {normalizeDisplayText(highlight)}
              </p>
            ))}
          </div>
        ) : (
          <EmptySection message={`${labels.speakerTitle}이 없습니다.`} />
        )}
      </section>
    ),
    summary: (
      <section key="summary">
        <SectionHeading count={visibleSummaryFacts.length} title={labels.summaryTitle} />
        {visibleSummaryFacts.length ? (
          <>
            <div className="border-y border-slate-300 dark:border-app-border">
              {displayedSummaryFacts.map((fact) => (
                <p key={fact} className="break-words border-b border-slate-100 py-[9px] text-[13px] leading-[1.72] text-slate-700 last:border-b-0 dark:border-app-line dark:text-app-body">
                  {normalizeDisplayText(fact)}
                </p>
              ))}
            </div>
            {shouldCollapseSummary ? (
              <button
                className="mt-2 inline-flex h-7 items-center rounded-sm px-0.5 text-[12px] font-medium text-slate-500 transition-colors duration-150 ease-out hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:text-app-muted dark:hover:text-app-text"
                type="button"
                onClick={() => setIsSummaryExpanded((current) => !current)}
              >
                {isSummaryExpanded ? "접기" : `더 보기 ${visibleSummaryFacts.length - SUMMARY_FACT_PREVIEW_LIMIT}`}
              </button>
            ) : null}
          </>
        ) : (
          <EmptySection message={`${labels.summaryTitle}이 없습니다.`} />
        )}
      </section>
    ),
    warnings: warnings.length ? (
      <section key="warnings">
        <details open={warnings.length <= 2 && resolvedMeetingType === "execution"} className="group border-y border-slate-200 py-3 dark:border-app-line">
          <summary className="group/review flex cursor-pointer list-none items-center justify-between gap-3 rounded-sm transition-colors duration-150 ease-out hover:bg-white/65 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:hover:bg-app-hover">
            <div className="min-w-0">
              <h2 className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-slate-800 dark:text-app-body">
                {labels.warningTitle}
                <ContextHelp stopPropagation text={labels.warningHelp} />
              </h2>
              <p className="mt-0.5 text-[11px] leading-4 text-slate-500 dark:text-app-muted">
                {labels.warningMeta} {warnings.length}
              </p>
            </div>
            <ChevronDown className="shrink-0 text-slate-400 transition-transform duration-150 ease-out group-open:rotate-180 dark:text-app-subtle" size={16} />
          </summary>
          <div className="mt-2.5 space-y-2">
            {warnings.map((warning) => (
              <p key={warning} className="break-words border-l border-slate-200 pl-3 text-[13px] leading-[1.68] text-slate-600 dark:border-app-line dark:text-app-muted">
                {normalizeDisplayText(warning)}
              </p>
            ))}
          </div>
        </details>
      </section>
    ) : null
  };

  return (
    <div className="space-y-7">
      {sectionOrder.map((sectionName) => sectionMap[sectionName])}
    </div>
  );
}

function getSectionOrder(_meetingType: MeetingType): Array<"actions" | "decisions" | "notes" | "speakers" | "summary" | "warnings"> {
  return ["summary", "decisions", "actions", "speakers", "notes", "warnings"];
}
