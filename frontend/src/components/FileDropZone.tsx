import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { FileAudio, FileText, UploadCloud, X } from "lucide-react";
import ContextHelp from "./ui/ContextHelp";

type FileDropZoneKind = "audio" | "context";

interface FileDropZoneProps {
  accept: string;
  description: string;
  file: File | null;
  helpText?: string;
  kind: FileDropZoneKind;
  label: string;
  optional?: boolean;
  onFileChange: (file: File | null) => void;
}

/**
 * Formats a file size into a short human-readable label.
 */
function formatFileSize(size: number): string {
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }

  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Renders the upload surface for required audio and optional team context files.
 */
export default function FileDropZone({
  accept,
  description,
  file,
  helpText,
  kind,
  label,
  optional = false,
  onFileChange
}: FileDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const Icon = kind === "audio" ? FileAudio : FileText;
  const formatHint = kind === "audio" ? "m4a, mp3, wav 등" : "txt, md";

  /**
   * Opens the hidden file input from the custom drop zone.
   */
  function handleBrowse() {
    inputRef.current?.click();
  }

  /**
   * Stores the selected file from the native file input.
   */
  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    onFileChange(event.target.files?.[0] ?? null);
  }

  /**
   * Highlights the drop zone while a file is dragged over it.
   */
  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(true);
  }

  /**
   * Accepts the first dropped file for this upload slot.
   */
  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    onFileChange(event.dataTransfer.files?.[0] ?? null);
  }

  /**
   * Clears the selected file without opening the file picker.
   */
  function handleClear() {
    onFileChange(null);

    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  return (
    <section className="space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-slate-950">
            {label}
            {helpText ? <ContextHelp text={helpText} /> : null}
          </h2>
          <p className="mt-0.5 text-[11px] leading-4 text-slate-400">{description}</p>
        </div>
        {optional ? (
          <span className="mt-0.5 text-[11px] font-medium text-slate-400">선택</span>
        ) : null}
      </div>

      <div
        className={[
          "rounded-md border border-dashed bg-white px-3 py-2 transition-colors duration-150 ease-out focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:bg-app-surface dark:border-app-line dark:focus-visible:border-app-accent-border dark:focus-visible:ring-app-accent-border",
          isDragging
            ? "border-brand-300 bg-brand-50 dark:border-app-accent-border dark:bg-app-accent-soft"
            : "border-slate-300 hover:border-slate-400 hover:bg-slate-50 active:bg-slate-50 dark:hover:border-app-border dark:hover:bg-app-hover dark:active:bg-app-hover"
        ].join(" ")}
        role="button"
        tabIndex={0}
        onClick={handleBrowse}
        onDragLeave={() => setIsDragging(false)}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            handleBrowse();
          }
        }}
      >
        <input ref={inputRef} accept={accept} className="hidden" type="file" onChange={handleInputChange} />

        {file ? (
          <div className="flex items-center gap-2.5">
            <Icon className="shrink-0 text-slate-400" size={17} strokeWidth={2} />
            <div className="min-w-0 flex-1">
              <p className="break-words text-[13px] font-medium text-slate-950">{file.name}</p>
              <p className="mt-0.5 text-[11px] text-slate-500">{formatFileSize(file.size)}</p>
            </div>
            <button
              aria-label={`${label} 제거`}
              className="grid size-7 shrink-0 place-items-center rounded-md border border-slate-200 bg-white text-slate-500 transition-colors duration-150 ease-out hover:border-slate-300 hover:text-slate-800 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:border-app-line dark:bg-app-surface dark:hover:border-app-border dark:hover:text-app-text dark:focus-visible:border-app-accent-border dark:focus-visible:ring-app-accent-border"
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                handleClear();
              }}
            >
              <X size={15} />
            </button>
          </div>
        ) : (
          <div className="flex min-h-11 flex-col items-center justify-center gap-2.5 text-center sm:flex-row sm:justify-start sm:text-left">
            <UploadCloud className="shrink-0 text-slate-400" size={18} strokeWidth={2} />
            <div className="min-w-0 max-w-full">
              <p className="text-[13px] font-medium text-slate-950">파일 선택 또는 끌어오기</p>
              <p className="mt-0.5 break-words text-xs text-slate-400">{formatHint}</p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
