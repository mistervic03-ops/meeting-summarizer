import { FormEvent, useState } from "react";
import { Loader2, LockKeyhole } from "lucide-react";
import ThemeToggle from "../components/ThemeToggle";

interface LoginPageProps {
  error?: string;
  isSubmitting: boolean;
  onLogin: (password: string) => Promise<void>;
}

export default function LoginPage({ error = "", isSubmitting, onLogin }: LoginPageProps) {
  const [password, setPassword] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onLogin(password);
  }

  return (
    <main className="min-h-screen bg-white px-4 py-6 text-slate-950 dark:bg-app-bg sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-48px)] w-full max-w-sm flex-col justify-center">
        <div className="mb-4 flex items-center justify-between border-b border-slate-300 pb-4">
          <div>
            <p className="text-[10px] font-medium tracking-[0.04em] text-brand-700 dark:text-app-accent">BIGXDATA · 회의록</p>
            <h1 className="mt-1.5 text-[28px] font-semibold leading-tight tracking-normal text-slate-950">로그인</h1>
          </div>
          <ThemeToggle />
        </div>

        <form className="space-y-3" onSubmit={handleSubmit}>
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-semibold text-slate-700">비밀번호</span>
            <input
              autoFocus
              className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none transition-colors duration-150 ease-out placeholder:text-slate-400 focus-visible:border-brand-300 focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-wait disabled:bg-slate-100 dark:bg-app-field"
              disabled={isSubmitting}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          {error ? <p className="break-words text-xs font-medium leading-5 text-red-700">{error}</p> : null}

          <button
            className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-brand-600 px-3 text-sm font-medium text-white transition-colors duration-150 ease-out hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:opacity-80 dark:bg-app-accent-button dark:hover:bg-app-accent-button-hover"
            disabled={isSubmitting || !password}
            type="submit"
          >
            {isSubmitting ? <Loader2 className="animate-spin" size={15} /> : <LockKeyhole size={15} />}
            들어가기
          </button>
        </form>
      </div>
    </main>
  );
}
