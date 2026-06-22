import { useState } from "react";
import HistoryPage from "./pages/HistoryPage";
import UploadPage from "./pages/UploadPage";
import "./styles.css";

/**
 * Renders the active frontend page for the meeting summarizer.
 */
function App() {
  const [showHistory, setShowHistory] = useState(false);

  if (showHistory) {
    return <HistoryPage onBack={() => setShowHistory(false)} />;
  }

  return <UploadPage onShowHistory={() => setShowHistory(true)} />;
}

export default App;
