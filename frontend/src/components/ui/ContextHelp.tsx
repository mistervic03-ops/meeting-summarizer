import { Info } from "lucide-react";

interface ContextHelpProps {
  stopPropagation?: boolean;
  text: string;
}

/**
 * Renders a compact hover and focus help tooltip.
 */
export default function ContextHelp({ stopPropagation = false, text }: ContextHelpProps) {
  return (
    <span className="group/help relative inline-flex align-middle">
      <button
        aria-label="도움말"
        className="inline-grid size-4 place-items-center rounded-sm text-slate-400 transition-colors duration-150 ease-out hover:text-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100"
        type="button"
        onClick={(event) => {
          if (stopPropagation) {
            event.stopPropagation();
          }
        }}
      >
        <Info size={13} strokeWidth={2} />
      </button>
      <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-1.5 hidden w-56 -translate-x-1/2 whitespace-pre-line rounded-md border border-slate-200 bg-white px-2.5 py-2 text-left text-[11px] font-normal leading-4 text-slate-600 shadow-sm group-focus-within/help:block group-hover/help:block dark:bg-app-popover">
        {text}
      </span>
    </span>
  );
}
