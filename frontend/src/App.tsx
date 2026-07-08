import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { getAuthStatus, loginWithPassword, logoutGateway } from "./api/auth";
import HistoryPage from "./pages/HistoryPage";
import LoginPage from "./pages/LoginPage";
import UploadPage from "./pages/UploadPage";
import "./styles.css";

type AuthState = "authenticated" | "checking" | "anonymous";

/**
 * Renders the active frontend page for the meeting summarizer.
 */
function App() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [authError, setAuthError] = useState("");
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadAuthStatus() {
      const authenticated = await getAuthStatus();
      if (!cancelled) {
        setAuthState(authenticated ? "authenticated" : "anonymous");
      }
    }

    void loadAuthStatus();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleLogin(password: string) {
    setIsLoggingIn(true);
    setAuthError("");

    try {
      await loginWithPassword(password);
      setAuthState("authenticated");
    } catch {
      setAuthError("비밀번호가 틀렸습니다.");
    } finally {
      setIsLoggingIn(false);
    }
  }

  async function handleLogout() {
    await logoutGateway();
    setShowHistory(false);
    setAuthState("anonymous");
  }

  if (authState === "checking") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-white text-slate-500 dark:bg-app-bg dark:text-app-muted">
        <Loader2 className="mr-2 animate-spin" size={16} />
        <span className="text-sm font-medium">인증 상태를 확인하는 중입니다.</span>
      </main>
    );
  }

  if (authState === "anonymous") {
    return <LoginPage error={authError} isSubmitting={isLoggingIn} onLogin={handleLogin} />;
  }

  if (showHistory) {
    return <HistoryPage onBack={() => setShowHistory(false)} onLogout={handleLogout} />;
  }

  return <UploadPage onLogout={handleLogout} onShowHistory={() => setShowHistory(true)} />;
}

export default App;
