import { useEffect, useState } from "react";
import { ArrowLeft, FileText, Loader2, RotateCcw } from "lucide-react";
import MinutesTab from "../components/MinutesTab";
import ThemeToggle from "../components/ThemeToggle";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

interface HistoryPageProps {
  onBack: () => void;
}

interface MeetingListItem {
  id: string;
  title: string;
  status: string;
  created_at: string;
  expires_at?: string | null;
  transcript_path?: string | null;
  summary_path?: string | null;
  error?: string | null;
}

interface MeetingDetail extends MeetingListItem {
  transcript: string;
  summary: string;
}

type LoadState = "idle" | "loading" | "failed";

/**
 * Shows saved meeting transcripts and summaries for the current browser session.
 */
export default function HistoryPage({ onBack }: HistoryPageProps) {
  const [meetings, setMeetings] = useState<MeetingListItem[]>([]);
  const [selectedMeeting, setSelectedMeeting] = useState<MeetingDetail | null>(null);
  const [listState, setListState] = useState<LoadState>("idle");
  const [detailState, setDetailState] = useState<LoadState>("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    void loadMeetings();
  }, []);

  async function loadMeetings() {
    setListState("loading");
    setError("");
    setSelectedMeeting(null);

    try {
      const response = await fetch(`${API_BASE_URL}/meetings`, {
        credentials: "include"
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      const nextMeetings = (await response.json()) as MeetingListItem[];
      setMeetings(nextMeetings);
      setListState("idle");
    } catch (caughtError) {
      setListState("failed");
      setError(caughtError instanceof Error ? caughtError.message : "지난 회의록을 불러오지 못했습니다.");
    }
  }

  async function loadMeetingDetail(meetingId: string) {
    setDetailState("loading");
    setError("");

    try {
      const response = await fetch(`${API_BASE_URL}/meetings/${meetingId}`, {
        credentials: "include"
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      const meeting = (await response.json()) as MeetingDetail;
      setSelectedMeeting(meeting);
      setDetailState("idle");
    } catch (caughtError) {
      setDetailState("failed");
      setError(caughtError instanceof Error ? caughtError.message : "회의록 내용을 불러오지 못했습니다.");
    }
  }

  function handleBackToList() {
    setSelectedMeeting(null);
    setDetailState("idle");
    setError("");
  }

  if (selectedMeeting) {
    return (
      <main className="min-h-screen bg-white px-4 py-6 text-slate-950 dark:bg-app-bg sm:px-6 lg:px-8">
        <div className="mx-auto w-full max-w-5xl">
          <header className="flex flex-col gap-3.5 border-b border-slate-300 pb-5 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <p className="text-[10px] font-medium tracking-[0.04em] text-brand-700 dark:text-app-accent">BIGXDATA · 지난 회의록</p>
              <h1 className="mt-1.5 break-words text-[30px] font-semibold leading-[1.12] tracking-normal text-slate-950">
                {selectedMeeting.title || "회의록"}
              </h1>
              <p className="mt-2 text-[11px] font-medium text-slate-500">
                {formatDateTime(selectedMeeting.created_at)} · {getStatusLabel(selectedMeeting.status)}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 sm:pt-1">
              <button
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:bg-app-surface"
                type="button"
                onClick={handleBackToList}
              >
                <ArrowLeft size={15} />
                목록
              </button>
              <ThemeToggle />
            </div>
          </header>

          {error ? <p className="mt-4 break-words text-xs font-medium leading-5 text-red-700">{error}</p> : null}

          <section className="grid gap-5 py-5 lg:grid-cols-2">
            <article className="space-y-2">
              <h2 className="text-[13px] font-semibold text-slate-950">Transcript</h2>
              <pre className="max-h-[560px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-slate-200 bg-slate-50 px-3 py-2.5 font-sans text-[12px] leading-5 text-slate-700 dark:bg-app-surface">
                {selectedMeeting.transcript.trim() || "저장된 transcript가 없습니다."}
              </pre>
            </article>
            <article className="space-y-2">
              <h2 className="text-[13px] font-semibold text-slate-950">회의록</h2>
              <MinutesTab isEditing={false} minutes={selectedMeeting.summary.trim()} onChange={() => {}} />
            </article>
          </section>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-white px-4 py-6 text-slate-950 dark:bg-app-bg sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-48px)] w-full max-w-5xl flex-col">
        <header className="flex flex-col gap-3.5 border-b border-slate-300 pb-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-[10px] font-medium tracking-[0.04em] text-brand-700 dark:text-app-accent">BIGXDATA · 저장된 회의</p>
            <h1 className="mt-1.5 text-[30px] font-semibold leading-[1.12] tracking-normal text-slate-950">지난 회의록</h1>
            <p className="mt-1.5 max-w-2xl text-[12px] leading-5 text-slate-500">
              같은 브라우저에서 처리한 회의록을 7일간 보관합니다.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:pt-1">
            <button
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:bg-app-surface"
              type="button"
              onClick={onBack}
            >
              <ArrowLeft size={15} />
              업로드
            </button>
            <ThemeToggle />
          </div>
        </header>

        <section className="flex-1 py-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-[13px] font-semibold text-slate-950">목록</h2>
            <button
              className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-600 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:text-slate-300 disabled:opacity-80 dark:bg-app-surface"
              disabled={listState === "loading"}
              type="button"
              onClick={() => void loadMeetings()}
            >
              {listState === "loading" ? <Loader2 className="animate-spin" size={14} /> : <RotateCcw size={14} />}
              새로고침
            </button>
          </div>

          {error ? <p className="mb-3 break-words text-xs font-medium leading-5 text-red-700">{error}</p> : null}

          {listState === "loading" ? (
            <div className="flex min-h-40 items-center justify-center border-y border-slate-300 text-[12px] font-medium text-slate-500">
              <Loader2 className="mr-2 animate-spin" size={16} />
              지난 회의록을 불러오는 중입니다.
            </div>
          ) : meetings.length === 0 ? (
            <div className="flex min-h-40 flex-col items-center justify-center gap-2 border-y border-slate-300 text-center">
              <FileText className="text-slate-300" size={28} />
              <p className="text-[13px] font-semibold text-slate-950">저장된 회의록이 없습니다.</p>
              <p className="text-[11px] leading-4 text-slate-500">회의를 처리하면 이곳에서 다시 확인할 수 있습니다.</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-200 border-y border-slate-300">
              {meetings.map((meeting) => (
                <button
                  key={meeting.id}
                  className="grid w-full gap-1 px-1 py-3 text-left transition-colors duration-150 ease-out hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-wait disabled:opacity-70 dark:hover:bg-app-hover"
                  disabled={detailState === "loading"}
                  type="button"
                  onClick={() => void loadMeetingDetail(meeting.id)}
                >
                  <span className="break-words text-[13px] font-semibold text-slate-950">{meeting.title || "회의록"}</span>
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-medium text-slate-500">
                    <span>{getStatusLabel(meeting.status)}</span>
                    <span aria-hidden="true">·</span>
                    <span>{formatDateTime(meeting.created_at)}</span>
                  </span>
                  {getDeletionLabel(meeting.expires_at) ? (
                    <span className="text-[11px] font-medium text-slate-400">{getDeletionLabel(meeting.expires_at)}</span>
                  ) : null}
                  {meeting.error ? <span className="break-words text-[11px] font-medium text-red-700">{meeting.error}</span> : null}
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

async function readErrorMessage(response: Response): Promise<string> {
  const errorBody = await response.json().catch(() => null);
  return errorBody?.detail || "요청을 완료하지 못했습니다.";
}

function formatDateTime(value: string): string {
  if (!value) {
    return "날짜 없음";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function getStatusLabel(status: string): string {
  if (status === "completed") {
    return "완료";
  }
  if (status === "transcript_ready") {
    return "Transcript 준비 완료";
  }
  if (status === "failed") {
    return "실패";
  }
  if (status === "pending") {
    return "대기 중";
  }
  return status || "상태 없음";
}

function getDeletionLabel(expiresAt: string | null | undefined): string {
  if (!expiresAt) {
    return "";
  }

  const expiresAtDate = new Date(expiresAt);
  if (Number.isNaN(expiresAtDate.getTime())) {
    return "";
  }

  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  const daysRemaining = Math.max(0, Math.floor((expiresAtDate.getTime() - Date.now()) / millisecondsPerDay));
  return daysRemaining === 0 ? "오늘 삭제 예정" : `${daysRemaining}일 후 삭제`;
}
