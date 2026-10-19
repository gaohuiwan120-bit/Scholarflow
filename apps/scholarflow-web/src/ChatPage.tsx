import {
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  artifactDownloadUrl,
  cancelTurn,
  createConversation,
  deleteConversation,
  getConversationMessages,
  getTaskResult,
  getTaskStatus,
  isTerminal,
  listConversations,
  listTaskArtifacts,
  streamConversationTurn,
  toolDisplayLabel,
  type ArtifactManifest,
  type ChatMessage,
  type ConversationMeta,
  type SseEvent,
  type TaskResultResponse,
  type TaskStatus,
  type ToolCallTraceItem,
} from "./api";
import { Markdown } from "./markdown";
import type { EvidenceRef } from "./api";

const LS_ACTIVE = "scholarflow.activeConversationId";

type LiveToolRow = {
  tool_call_id: string;
  tool_name: string;
  status: "running" | "succeeded" | "failed";
  arguments_summary?: Record<string, unknown>;
  result_summary?: string | null;
  error?: string | null;
  duration_ms?: number | null;
};

type LiveProgress = {
  message: string;
  task_id?: string | null;
  overall_status?: string | null;
};

type UiMessage = ChatMessage & {
  streaming?: boolean;
  liveTools?: LiveToolRow[];
  liveProgress?: LiveProgress[];
  streamError?: string | null;
};

function paperRefsFromMessage(m: UiMessage): EvidenceRef[] {
  return (m.evidence_refs || []).filter(
    (e) => (e.kind || "paper") === "paper" && (e.title || e.source_url),
  );
}

function ToolRowView({ t }: { t: LiveToolRow }) {
  const summary = t.result_summary || "";
  const countHint = (() => {
    const m = summary.match(/count=(\d+)/);
    return m ? m[1] : null;
  })();
  const looksRawJson = summary.trimStart().startsWith("{");
  const shortLine = looksRawJson
    ? null
    : summary.length > 160
      ? `${summary.slice(0, 157)}…`
      : summary || null;
  return (
    <li className={`tool-row status-${t.status}`}>
      <div className="ev-head">
        <strong>{toolDisplayLabel(t.tool_name)}</strong>
        <span className={`tag status-${t.status}`}>{t.status}</span>
        {countHint && <span className="tag">{countHint} 条结果</span>}
        {t.duration_ms != null && (
          <span className="tag">{t.duration_ms} ms</span>
        )}
      </div>
      {t.error && <p className="err">{t.error}</p>}
      {shortLine && <p className="muted tool-sum">{shortLine}</p>}
      <details className="tool-details">
        <summary>查看工具详情</summary>
        {t.arguments_summary && (
          <pre className="tool-args">
            {JSON.stringify(t.arguments_summary, null, 2)}
          </pre>
        )}
        {summary && (
          <pre className="tool-args tool-raw">{summary}</pre>
        )}
        {!t.arguments_summary && !summary && !t.error && (
          <p className="muted">暂无额外参数或返回摘要。</p>
        )}
      </details>
    </li>
  );
}

function PaperCards({ papers }: { papers: EvidenceRef[] }) {
  if (!papers.length) return null;
  return (
    <div className="paper-cards">
      <h4>论文结果</h4>
      <div className="paper-card-grid">
        {papers.map((p, i) => (
          <article
            key={`${p.evidence_id || p.source_url || "p"}-${i}`}
            className="paper-card"
          >
            <h5 className="paper-title">{p.title || "（无标题）"}</h5>
            <div className="paper-meta">
              {p.year != null && <span className="tag">{p.year}</span>}
              {p.kind_hint === "survey_or_review" && (
                <span className="tag ok">标题含 survey/review</span>
              )}
              {p.relevance_score != null && (
                <span className="tag muted-tag">
                  相关分 {p.relevance_score}
                </span>
              )}
              {p.evidence_id && (
                <code className="paper-eid">{p.evidence_id}</code>
              )}
            </div>
            {p.authors && p.authors.length > 0 ? (
              <p className="paper-authors">{p.authors.join(", ")}</p>
            ) : (
              <p className="muted paper-authors">作者：未知</p>
            )}
            {p.abstract ? (
              <p className="paper-abs">{p.abstract}</p>
            ) : (
              <p className="muted paper-abs">摘要：未知</p>
            )}
            {p.source_url ? (
              <a
                className="paper-link"
                href={p.source_url}
                target="_blank"
                rel="noreferrer"
              >
                打开原文
              </a>
            ) : (
              <span className="muted">原文链接：未知</span>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

function loadActiveId(): string | null {
  try {
    return localStorage.getItem(LS_ACTIVE);
  } catch {
    return null;
  }
}

function saveActiveId(id: string | null) {
  try {
    if (id) localStorage.setItem(LS_ACTIVE, id);
    else localStorage.removeItem(LS_ACTIVE);
  } catch {
    /* ignore */
  }
}

export default function ChatPage() {
  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  const [activeId, setActiveId] = useState<string | null>(loadActiveId);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [sending, setSending] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [msgError, setMsgError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [turnId, setTurnId] = useState<string | null>(null);
  const [taskCards, setTaskCards] = useState<
    Record<
      string,
      {
        status: TaskStatus | string;
        result?: TaskResultResponse | null;
        manifest?: ArtifactManifest | null;
        error?: string | null;
      }
    >
  >({});

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const stickBottom = useRef(true);
  const listRef = useRef<HTMLDivElement | null>(null);

  const refreshList = useCallback(async () => {
    setLoadingList(true);
    try {
      const data = await listConversations();
      setConversations(data.conversations);
      setListError(null);
    } catch (e) {
      setListError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingList(false);
    }
  }, []);

  const loadMessages = useCallback(async (id: string) => {
    setLoadingMsgs(true);
    setMsgError(null);
    try {
      const data = await getConversationMessages(id);
      setMessages(data.messages);
      // Prefetch task cards for related ids
      const tids = new Set<string>();
      for (const m of data.messages) {
        if (m.related_task_id) tids.add(m.related_task_id);
      }
      for (const tid of tids) {
        void hydrateTask(tid);
      }
    } catch (e) {
      setMessages([]);
      setMsgError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingMsgs(false);
    }
  }, []);

  const hydrateTask = useCallback(async (taskId: string) => {
    try {
      const st = await getTaskStatus(taskId);
      let result: TaskResultResponse | null = null;
      let manifest: ArtifactManifest | null = null;
      if (isTerminal(st.status)) {
        try {
          result = await getTaskResult(taskId);
        } catch {
          result = null;
        }
        try {
          manifest = await listTaskArtifacts(taskId);
        } catch {
          manifest = result?.research?.artifact_manifest ?? null;
        }
      }
      setTaskCards((prev) => ({
        ...prev,
        [taskId]: {
          status: st.status,
          result,
          manifest,
          error: st.error,
        },
      }));
    } catch (e) {
      setTaskCards((prev) => ({
        ...prev,
        [taskId]: {
          status: "unknown",
          error: e instanceof Error ? e.message : String(e),
        },
      }));
    }
  }, []);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    saveActiveId(activeId);
    void loadMessages(activeId);
  }, [activeId, loadMessages]);

  useEffect(() => {
    if (stickBottom.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, sending]);

  function onScrollList() {
    const el = listRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickBottom.current = dist < 80;
  }

  async function onNewChat() {
    if (sending) return;
    try {
      const created = await createConversation();
      const id = created.conversation.conversation_id;
      await refreshList();
      setActiveId(id);
      setMessages([]);
      setMsgError(null);
    } catch (e) {
      setListError(e instanceof Error ? e.message : String(e));
    }
  }

  async function ensureConversation(): Promise<string> {
    if (activeId) return activeId;
    const created = await createConversation();
    const id = created.conversation.conversation_id;
    await refreshList();
    setActiveId(id);
    return id;
  }

  async function stopGeneration() {
    const tid = turnId;
    const cid = activeId;
    abortRef.current?.abort();
    abortRef.current = null;
    if (cid && tid) {
      try {
        await cancelTurn(cid, tid);
      } catch {
        /* best effort */
      }
    }
    setSending(false);
    setTurnId(null);
  }

  async function sendMessage(raw: string) {
    const content = raw.trim();
    if (!content || sending) return;

    setSending(true);
    setMsgError(null);
    stickBottom.current = true;

    let cid: string;
    try {
      cid = await ensureConversation();
    } catch (e) {
      setMsgError(e instanceof Error ? e.message : String(e));
      setSending(false);
      return;
    }

    const tempUserId = `local-user-${Date.now()}`;
    const tempAsstId = `local-asst-${Date.now()}`;
    const userMsg: UiMessage = {
      message_id: tempUserId,
      conversation_id: cid,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    const asstMsg: UiMessage = {
      message_id: tempAsstId,
      conversation_id: cid,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
      streaming: true,
      liveTools: [],
      liveProgress: [],
    };
    setMessages((prev) => [...prev, userMsg, asstMsg]);
    setInput("");

    const ac = new AbortController();
    abortRef.current = ac;

    const patchAsst = (fn: (m: UiMessage) => UiMessage) => {
      setMessages((prev) =>
        prev.map((m) => (m.message_id === tempAsstId ? fn(m) : m)),
      );
    };

    try {
      await streamConversationTurn(
        cid,
        content,
        {
          onEvent: (ev: SseEvent) => {
            if (ev.event === "turn_start") {
              setTurnId(ev.turn_id);
              if (ev.user_message_id) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.message_id === tempUserId
                      ? { ...m, message_id: ev.user_message_id! }
                      : m,
                  ),
                );
              }
            } else if (ev.event === "token" && ev.text) {
              patchAsst((m) => ({
                ...m,
                content: (m.content || "") + ev.text,
              }));
            } else if (ev.event === "tool_start") {
              patchAsst((m) => {
                const row: LiveToolRow = {
                  tool_call_id: ev.tool_call_id || `t-${Date.now()}`,
                  tool_name: ev.tool_name || "tool",
                  status: "running",
                  arguments_summary: ev.arguments_summary,
                };
                return {
                  ...m,
                  liveTools: [...(m.liveTools || []), row],
                };
              });
            } else if (ev.event === "tool_end") {
              patchAsst((m) => ({
                ...m,
                liveTools: (m.liveTools || []).map((t) =>
                  t.tool_call_id === ev.tool_call_id ||
                  (ev.tool_name && t.tool_name === ev.tool_name && t.status === "running")
                    ? {
                        ...t,
                        status:
                          ev.status === "succeeded" ? "succeeded" : "failed",
                        result_summary: ev.result_summary,
                        error: ev.error,
                        duration_ms: ev.duration_ms,
                      }
                    : t,
                ),
              }));
            } else if (ev.event === "workflow_progress") {
              patchAsst((m) => ({
                ...m,
                liveProgress: [
                  ...(m.liveProgress || []),
                  {
                    message: ev.message || "progress",
                    task_id: ev.task_id,
                    overall_status: ev.overall_status,
                  },
                ],
              }));
              if (ev.task_id) void hydrateTask(ev.task_id);
            } else if (ev.event === "error") {
              patchAsst((m) => ({
                ...m,
                streamError: ev.message || "stream error",
              }));
            } else if (ev.event === "done") {
              patchAsst((m) => ({
                ...m,
                streaming: false,
                message_id: ev.assistant_message_id || m.message_id,
                related_task_id: ev.related_task_id || m.related_task_id,
                streamError:
                  ev.status === "error" ||
                  ev.status === "cancelled" ||
                  ev.status === "timeout"
                    ? ev.error || ev.status
                    : m.streamError,
              }));
              if (ev.related_task_id) void hydrateTask(ev.related_task_id);
            }
          },
        },
        ac.signal,
      );
      // Reload authoritative history (ids, traces) without inventing content
      await loadMessages(cid);
      await refreshList();
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        const msg = e instanceof Error ? e.message : String(e);
        patchAsst((m) => ({
          ...m,
          streaming: false,
          streamError: m.content
            ? `连接中断：${msg}（已保留已收到内容）`
            : msg,
        }));
        setMsgError(msg);
      } else {
        patchAsst((m) => ({
          ...m,
          streaming: false,
          streamError: m.streamError || "已停止生成",
        }));
      }
    } finally {
      setSending(false);
      setTurnId(null);
      abortRef.current = null;
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void sendMessage(input);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage(input);
    }
  }

  async function onDeleteConversation(c: ConversationMeta) {
    const label = c.title || c.conversation_id;
    const ok = window.confirm(`确定删除会话「${label}」？此操作不可恢复。`);
    if (!ok) return;
    setDeletingId(c.conversation_id);
    setListError(null);
    try {
      await deleteConversation(c.conversation_id);
      setConversations((prev) =>
        prev.filter((x) => x.conversation_id !== c.conversation_id),
      );
      if (activeId === c.conversation_id) {
        setActiveId(null);
        setMessages([]);
        saveActiveId(null);
      }
    } catch (e) {
      setListError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="chat-layout">
      <aside className="chat-sidebar">
        <button type="button" className="btn-primary" onClick={() => void onNewChat()} disabled={sending}>
          新建会话
        </button>
        {loadingList && <p className="muted sidebar-hint">加载会话…</p>}
        {listError && <p className="err sidebar-hint">{listError}</p>}
        {!loadingList && !conversations.length && !listError && (
          <p className="muted sidebar-hint">暂无历史会话</p>
        )}
        <ul className="conv-list">
          {conversations.map((c) => (
            <li key={c.conversation_id} className="conv-row">
              <button
                type="button"
                className={
                  c.conversation_id === activeId ? "conv-item active" : "conv-item"
                }
                disabled={sending || deletingId === c.conversation_id}
                onClick={() => setActiveId(c.conversation_id)}
              >
                <span className="conv-title">{c.title || c.conversation_id}</span>
                <span className="conv-meta">{c.message_count} 条</span>
              </button>
              <button
                type="button"
                className="conv-delete"
                title="删除会话"
                aria-label={`删除会话 ${c.title || c.conversation_id}`}
                disabled={sending || deletingId === c.conversation_id}
                onClick={(e) => {
                  e.stopPropagation();
                  void onDeleteConversation(c);
                }}
              >
                {deletingId === c.conversation_id ? "…" : "删除"}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="chat-main">
        <div className="chat-messages" ref={listRef} onScroll={onScrollList}>
          {!activeId && !messages.length && (
            <div className="welcome">
              <h2>ScholarFlow 科研助手</h2>
              <p>
                多轮对话 · 真实 DeepSeek 推理 · 工具调用 · 科研工作流与产物。
                开始提问，或新建会话。
              </p>
            </div>
          )}
          {loadingMsgs && <p className="muted">加载消息…</p>}
          {msgError && <p className="err">{msgError}</p>}
          {messages.map((m) => (
            <article
              key={m.message_id}
              className={m.role === "user" ? "bubble user" : "bubble assistant"}
            >
              <div className="bubble-role">
                {m.role === "user" ? "你" : "ScholarFlow"}
                {m.streaming ? " · 生成中" : ""}
              </div>
              {m.role === "assistant" ? (
                <Markdown text={m.content || (m.streaming ? "…" : "")} />
              ) : (
                <p className="plain">{m.content}</p>
              )}

              {(() => {
                const papers = paperRefsFromMessage(m);
                return papers.length ? <PaperCards papers={papers} /> : null;
              })()}

              {(m.liveTools?.length || m.tool_call_trace?.length) ? (
                <div className="tool-panel">
                  <h4>工具执行</h4>
                  <ul>
                    {(m.liveTools?.length
                      ? m.liveTools
                      : (m.tool_call_trace || []).map(
                          (t: ToolCallTraceItem): LiveToolRow => ({
                            tool_call_id: t.tool_call_id || t.tool_name,
                            tool_name: t.tool_name,
                            status:
                              t.status === "succeeded"
                                ? "succeeded"
                                : t.status === "failed"
                                  ? "failed"
                                  : "running",
                            arguments_summary: t.arguments,
                            result_summary: t.result_summary,
                            error: t.error,
                            duration_ms: null,
                          }),
                        )
                    ).map((t) => (
                      <ToolRowView key={t.tool_call_id} t={t} />
                    ))}
                  </ul>
                </div>
              ) : null}

              {m.liveProgress?.length ? (
                <div className="progress-panel">
                  <h4>工作流进度</h4>
                  <ul>
                    {m.liveProgress.map((p, i) => (
                      <li key={`${p.message}-${i}`}>
                        {p.message}
                        {p.task_id && (
                          <>
                            {" · "}
                            <code>{p.task_id}</code>
                          </>
                        )}
                        {p.overall_status && (
                          <span className="tag">{p.overall_status}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {(() => {
                // Avoid duplicating the paper list: cards already bind title↔url↔evidence_id.
                const other = (m.evidence_refs || []).filter(
                  (e) => e.kind && e.kind !== "paper",
                );
                if (!other.length) return null;
                return (
                  <div className="evidence-panel">
                    <h4>其他证据</h4>
                    <ul>
                      {other.map((e, i) => (
                        <li key={`${e.evidence_id}-${i}`}>
                          <strong>{e.title || e.evidence_id || "evidence"}</strong>
                          {e.kind && <span className="tag">{e.kind}</span>}
                          {e.source_url && (
                            <div>
                              <a
                                href={e.source_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {e.source_url}
                              </a>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })()}

              {m.related_task_id && (
                <TaskCard
                  taskId={m.related_task_id}
                  card={taskCards[m.related_task_id]}
                  onRefresh={() => void hydrateTask(m.related_task_id!)}
                />
              )}

              {m.streamError && <p className="err">{m.streamError}</p>}
            </article>
          ))}
          <div ref={bottomRef} />
        </div>

        <form className="composer" onSubmit={onSubmit}>
          <textarea
            rows={3}
            value={input}
            placeholder="输入研究问题… Enter 发送，Shift+Enter 换行"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={sending}
          />
          <div className="composer-actions">
            {sending ? (
              <button type="button" className="btn-danger" onClick={() => void stopGeneration()}>
                停止生成
              </button>
            ) : (
              <button type="submit" className="btn-primary" disabled={!input.trim()}>
                发送
              </button>
            )}
            {sending && <span className="muted">正在与后端 SSE 流式对话…</span>}
          </div>
        </form>
      </section>
    </div>
  );
}

function TaskCard({
  taskId,
  card,
  onRefresh,
}: {
  taskId: string;
  card?: {
    status: TaskStatus | string;
    result?: TaskResultResponse | null;
    manifest?: ArtifactManifest | null;
    error?: string | null;
  };
  onRefresh: () => void;
}) {
  const status = card?.status ?? "loading";
  const research = card?.result?.research;
  const mode =
    research?.effective_data_mode || research?.data_mode || "unknown";
  const rows =
    card?.manifest?.artifacts ||
    research?.artifact_manifest?.artifacts ||
    [];
  const running = status === "queued" || status === "running" || status === "loading";

  return (
    <div className="task-card">
      <div className="ev-head">
        <strong>科研任务</strong>
        <code>{taskId}</code>
        <span className={`tag status-${status}`}>{status}</span>
        <span className="tag">mode={mode}</span>
        <button type="button" className="linkish" onClick={onRefresh}>
          刷新
        </button>
      </div>
      {running && (
        <p className="muted">任务仍在运行 — 不会显示为成功，产物待终端状态确认。</p>
      )}
      {mode === "fixture" && !running && (
        <p className="muted">数据模式 fixture：离线样本 / 非 live 外部检索结果。</p>
      )}
      {card?.error && <p className="err">{card.error}</p>}
      {research?.report_excerpt && (
        <pre className="answer excerpt">{research.report_excerpt.slice(0, 600)}</pre>
      )}
      {rows.length > 0 && isTerminal(status as TaskStatus) && (
        <ul className="artifacts">
          {rows.map((a) => (
            <li key={a.filename}>
              <a
                href={artifactDownloadUrl(taskId, a.filename)}
                target="_blank"
                rel="noreferrer"
              >
                下载 {a.filename}
              </a>
              {a.data_mode && <span className="tag">{a.data_mode}</span>}
            </li>
          ))}
        </ul>
      )}
      {!running && !rows.length && status !== "loading" && (
        <p className="muted">暂无已确认产物文件</p>
      )}
    </div>
  );
}
