import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import EmptySection from "./ui/EmptySection";
import { normalizeMarkdownForDisplay } from "../utils/displayText";

interface MinutesTabProps {
  isEditing?: boolean;
  minutes: string;
  onChange?: (minutes: string) => void;
}

/**
 * Renders the full minutes tab with markdown formatting.
 */
export default function MinutesTab({ isEditing = false, minutes, onChange }: MinutesTabProps) {
  const displayMinutes = normalizeMarkdownForDisplay(minutes);

  if (!displayMinutes && !isEditing) {
    return (
      <section className="border-y border-slate-200 bg-transparent py-3 dark:border-app-line">
        <EmptySection message="회의록이 없습니다." />
      </section>
    );
  }

  if (isEditing) {
    return (
      <article className="mx-auto max-w-[720px] bg-transparent py-1">
        <label className="sr-only" htmlFor="minutes-editor">
          회의록 편집
        </label>
        <textarea
          className="min-h-[560px] w-full resize-y border-y border-slate-300 bg-transparent px-0 py-4 text-[15px] leading-[1.8] text-slate-800 outline-none transition-colors duration-150 ease-out placeholder:text-slate-400 focus:border-brand-300 dark:border-app-border dark:text-app-body dark:placeholder:text-app-subtle dark:focus:border-app-accent-border"
          id="minutes-editor"
          spellCheck={false}
          value={minutes}
          onChange={(event) => onChange?.(event.target.value)}
        />
      </article>
    );
  }

  return (
    <article className="mx-auto max-w-[720px] bg-transparent py-1">
      <ReactMarkdown
        components={{
          h1: ({ children }) => <h1 className="mb-6 break-words text-[22px] font-semibold leading-tight text-slate-950 dark:text-app-text">{children}</h1>,
          h2: ({ children }) => (
            <h2 className="mb-3 mt-8 break-words border-t border-slate-300 pt-6 text-[17px] font-semibold leading-6 text-slate-950 first:mt-0 first:border-t-0 first:pt-0 dark:border-app-border dark:text-app-text">
              {children}
            </h2>
          ),
          h3: ({ children }) => <h3 className="mb-2 mt-6 break-words text-[15px] font-semibold leading-6 text-slate-900 dark:text-app-body">{children}</h3>,
          ul: ({ children }) => <ul className="mb-6 ml-5 list-disc space-y-1.5">{children}</ul>,
          ol: ({ children }) => <ol className="mb-6 ml-5 list-decimal space-y-1.5">{children}</ol>,
          li: ({ children }) => <li className="break-words pl-1 text-[14px] leading-[1.82] text-slate-700 dark:text-app-body">{children}</li>,
          p: ({ children }) => <p className="mb-[18px] whitespace-pre-wrap break-words text-[15px] leading-[1.82] text-slate-700 dark:text-app-body">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-slate-950 dark:text-app-text">{children}</strong>,
          table: ({ children }) => (
            <div className="mb-6 overflow-x-auto border-y border-slate-200 dark:border-app-line">
              <table className="min-w-full border-collapse text-left text-[14px] leading-6">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-slate-50 text-slate-900 dark:bg-app-panel dark:text-app-text">{children}</thead>,
          tbody: ({ children }) => <tbody className="divide-y divide-slate-200 dark:divide-app-line">{children}</tbody>,
          tr: ({ children }) => <tr>{children}</tr>,
          th: ({ children }) => <th className="whitespace-nowrap px-3 py-2.5 font-semibold">{children}</th>,
          td: ({ children }) => <td className="px-3 py-2.5 align-top text-slate-700 dark:text-app-body">{children}</td>
        }}
        remarkPlugins={[remarkGfm]}
      >
        {displayMinutes}
      </ReactMarkdown>
    </article>
  );
}
