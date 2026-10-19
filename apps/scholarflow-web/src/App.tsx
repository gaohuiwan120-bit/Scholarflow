import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "./api";
import ChatPage from "./ChatPage";
import Workbench from "./Workbench";

type Tab = "chat" | "workbench";

const LS_TAB = "scholarflow.activeTab";

function loadTab(): Tab {
  try {
    const v = localStorage.getItem(LS_TAB);
    if (v === "workbench" || v === "chat") return v;
  } catch {
    /* ignore */
  }
  return "chat";
}

export default function App() {
  const [tab, setTab] = useState<Tab>(loadTab);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth()
      .then((h) => {
        setHealth(h);
        setHealthError(null);
      })
      .catch((e: Error) => setHealthError(e.message));
  }, []);

  function switchTab(next: Tab) {
    setTab(next);
    try {
      localStorage.setItem(LS_TAB, next);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="app-shell">
      <header className="app-top">
        <div className="brand">
          <span className="mark" aria-hidden />
          <div>
            <p className="brand-name">ScholarFlow</p>
            <p className="brand-sub">对话式科研智能体</p>
          </div>
        </div>
        <nav className="tabs" aria-label="主导航">
          <button
            type="button"
            className={tab === "chat" ? "tab active" : "tab"}
            onClick={() => switchTab("chat")}
          >
            Chat
          </button>
          <button
            type="button"
            className={tab === "workbench" ? "tab active" : "tab"}
            onClick={() => switchTab("workbench")}
          >
            科研工作台
          </button>
        </nav>
        <div className="health">
          {healthError && (
            <span className="pill bad">API offline: {healthError}</span>
          )}
          {health && (
            <span className={`pill ${health.llm_configured ? "ok" : "warn"}`}>
              {health.service}
              {health.llm_configured
                ? ` · ${health.llm_provider || "llm"}/${health.llm_model || "?"}`
                : " · LLM 未配置"}
              {health.langgraph_available ? " · LangGraph" : ""}
            </span>
          )}
        </div>
      </header>

      <div className="app-body">
        {tab === "chat" ? <ChatPage /> : <Workbench />}
      </div>

      <footer className="foot">
        ScholarFlow · Chat 默认 · 工作台保留 · Vite + FastAPI · 8GB-friendly
      </footer>
    </div>
  );
}
