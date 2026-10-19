import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  artifactDownloadUrl,
  createTask,
  fetchHealth,
  getTaskResult,
  getTaskStatus,
  isTerminal,
  listTaskArtifacts,
  type ArtifactManifest,
  type DataMode,
  type HealthResponse,
  type SubtaskStatusItem,
  type TaskKind,
  type TaskResultResponse,
  type TaskStatus,
} from "./api";

const DEFAULT_QUESTION =
  "Blended RAG hybrid dense sparse vs Naive RAG";

const KIND_OPTIONS: { value: TaskKind; label: string }[] = [
  { value: "research_orchestration", label: "综合科研编排（LangGraph）" },
  { value: "paper_research", label: "论文调研工作流" },
  { value: "repository_analysis", label: "仓库分析工作流" },
  { value: "experiment_design", label: "实验方案工作流" },
  { value: "rag_query", label: "Hybrid RAG 检索（Phase 1）" },
];

export default function Workbench() {
  const [kind, setKind] = useState<TaskKind>("research_orchestration");
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [dataMode, setDataMode] = useState<DataMode>("fixture");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<TaskStatus | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [subtasks, setSubtasks] = useState<SubtaskStatusItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TaskResultResponse | null>(null);
  const [manifest, setManifest] = useState<ArtifactManifest | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchHealth()
      .then((h) => {
        setHealth(h);
        setHealthError(null);
      })
      .catch((e: Error) => setHealthError(e.message));
  }, []);

  const poll = useCallback(async (id: string) => {
    const st = await getTaskStatus(id);
    setStatus(st.status);
    setProgress(st.progress ?? null);
    if (st.subtasks?.length) setSubtasks(st.subtasks);
    if (st.error) setError(st.error);
    if (!isTerminal(st.status)) return false;
    const res = await getTaskResult(id);
    setResult(res);
    if (res.subtasks?.length) setSubtasks(res.subtasks);
    if (res.status === "failed" || res.status === "timed_out") {
      setError(res.error || `Task ${res.status}`);
    }
    try {
      const man = await listTaskArtifacts(id);
      setManifest(man);
    } catch {
      setManifest(res.research?.artifact_manifest ?? null);
    }
    return true;
  }, []);

  useEffect(() => {
    if (!taskId || !status || isTerminal(status)) return;
    const timer = window.setInterval(() => {
      void poll(taskId).catch((e: Error) => setError(e.message));
    }, 800);
    return () => window.clearInterval(timer);
  }, [taskId, status, poll]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);
    setManifest(null);
    setProgress(null);
    setStatus(null);
    setTaskId(null);
    setSubtasks([]);
    try {
      const extras =
        kind === "rag_query"
          ? {}
          : {
              data_mode: dataMode,
              persist_artifacts: true,
              allow_fixture_fallback: false,
            };
      const created = await createTask(kind, question.trim(), extras);
      setTaskId(created.task_id);
      setStatus(created.status);
      setProgress("queued");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || status === "queued" || status === "running";
  const research = result?.research;
  const effMode =
    research?.effective_data_mode || research?.data_mode || dataMode;
  const artifactRows =
    manifest?.artifacts ||
    research?.artifact_manifest?.artifacts ||
    [];

  return (
    <div className="workbench">
      <div className="workbench-health">
        {healthError && (
          <span className="pill bad">API offline: {healthError}</span>
        )}
        {health && (
          <span className={`pill ${health.langgraph_available ? "ok" : "warn"}`}>
            {health.service}
            {health.langgraph_available ? " · LangGraph" : " · no LangGraph"}
            {health.llm_configured ? ` · LLM ${health.llm_model || ""}` : " · LLM off"}
            {" · "}
            {(health.runtimes || [health.runtime]).join(", ")}
          </span>
        )}
      </div>

      <main className="main">
        <section className="panel">
          <h1>科研工作台</h1>
          <p className="lead">
            独立任务提交入口（保留 Phase 1–7）。LangGraph + MCP + 产物落盘。
            默认 fixture；live 失败不会静默伪装成成功。对话请使用 Chat 页。
          </p>

          <form className="form" onSubmit={onSubmit}>
            <label htmlFor="kind">任务类型</label>
            <select
              id="kind"
              value={kind}
              disabled={busy}
              onChange={(ev) => setKind(ev.target.value as TaskKind)}
            >
              {KIND_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            {kind !== "rag_query" && (
              <>
                <label htmlFor="dataMode">数据模式</label>
                <select
                  id="dataMode"
                  value={dataMode}
                  disabled={busy}
                  onChange={(ev) => setDataMode(ev.target.value as DataMode)}
                >
                  <option value="fixture">fixture（离线样本，默认定性测试）</option>
                  <option value="live">live（真实 MCP → arXiv / GitHub）</option>
                </select>
              </>
            )}

            <label htmlFor="q">研究问题</label>
            <textarea
              id="q"
              rows={4}
              value={question}
              onChange={(ev) => setQuestion(ev.target.value)}
              disabled={busy}
              required
            />
            <div className="actions">
              <button type="submit" disabled={busy || !question.trim()}>
                {busy ? "执行中…" : "提交任务"}
              </button>
            </div>
          </form>

          {(taskId || status || error) && (
            <div className="status-box">
              <h2>执行状态</h2>
              {taskId && (
                <p>
                  <span className="k">task_id</span> <code>{taskId}</code>
                </p>
              )}
              {status && (
                <p>
                  <span className="k">status</span>{" "}
                  <span className={`status status-${status}`}>{status}</span>
                </p>
              )}
              {progress && (
                <p>
                  <span className="k">progress</span> {progress}
                </p>
              )}
              {kind !== "rag_query" && (
                <p>
                  <span className="k">data_mode</span>{" "}
                  <span className="tag">{effMode}</span>
                </p>
              )}
              {error && <p className="err">{error}</p>}

              {subtasks.length > 0 && (
                <>
                  <h3>Sub-Agent 状态（后端真实数据）</h3>
                  <ul className="subtasks">
                    {subtasks.map((s) => (
                      <li key={s.subtask_id}>
                        <div className="ev-head">
                          <strong>{s.role}</strong>
                          <span className={`tag status-${s.status}`}>
                            {s.status}
                          </span>
                          {s.duration_ms != null && (
                            <span className="tag">{s.duration_ms} ms</span>
                          )}
                          {s.data_source && (
                            <span className="tag">{s.data_source}</span>
                          )}
                        </div>
                        {s.depends_on?.length > 0 && (
                          <p className="muted">
                            depends_on: {s.depends_on.join(", ")}
                          </p>
                        )}
                        {s.summary && <p className="ev-text">{s.summary}</p>}
                        {s.error && <p className="err">{s.error}</p>}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </section>

        {research && (
          <section className="panel result">
            <h2>编排结果</h2>
            {research.research_plan?.title != null && (
              <p className="meta">
                主题=<strong>{String(research.research_plan.title)}</strong>
              </p>
            )}
            <p className="meta">
              mode=<strong>{research.workflow_mode}</strong>
              {" · "}
              overall=<strong>{research.overall_status}</strong>
              {research.review_decision && (
                <>
                  {" · "}review=<strong>{research.review_decision}</strong>
                </>
              )}
              {" · "}data=<strong>{research.data_mode}</strong>
              {research.effective_data_mode &&
                research.effective_data_mode !== research.data_mode && (
                  <>
                    {" → "}
                    <strong>{research.effective_data_mode}</strong>
                  </>
                )}
              {result?.duration_ms != null && <> · {result.duration_ms} ms</>}
            </p>

            {(research.degradation_events?.length ?? 0) > 0 && (
              <>
                <h3>降级事件</h3>
                <ul className="evidence">
                  {research.degradation_events!.map((d, i) => (
                    <li key={i}>
                      <strong>{String(d.node || "node")}</strong> —{" "}
                      {String(d.action || "")}: {String(d.reason || "")}
                    </li>
                  ))}
                </ul>
              </>
            )}

            {(research.mcp_calls?.length ?? 0) > 0 && (
              <>
                <h3>MCP 调用记录</h3>
                <ul className="evidence">
                  {research.mcp_calls!.map((c, i) => (
                    <li key={i}>
                      <div className="ev-head">
                        <strong>{String(c.tool)}</strong>
                        <span className={`tag ${c.ok ? "status-succeeded" : "status-failed"}`}>
                          {c.ok ? "ok" : "fail"}
                        </span>
                        {c.duration_ms != null && (
                          <span className="tag">{String(c.duration_ms)} ms</span>
                        )}
                      </div>
                      {c.error != null && (
                        <p className="err">{String(c.error)}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}

            {research.report_excerpt && (
              <>
                <h3>报告摘录</h3>
                <pre className="answer">{research.report_excerpt}</pre>
              </>
            )}

            {research.reviews?.length > 0 && (
              <>
                <h3>审查结果</h3>
                <ul className="evidence">
                  {research.reviews.map((r, i) => (
                    <li key={i}>
                      <strong>{String(r.status)}</strong> — {String(r.claim)}
                      <p className="ev-text">{String(r.reason)}</p>
                    </li>
                  ))}
                </ul>
              </>
            )}

            {artifactRows.length > 0 && taskId && (
              <>
                <h3>产物（可下载）</h3>
                <p className="meta">
                  count={artifactRows.length}
                  {manifest?.data_mode && <> · persisted_mode={manifest.data_mode}</>}
                </p>
                <ul className="artifacts">
                  {artifactRows.map((a) => (
                    <li key={a.artifact_id || a.filename}>
                      <div className="ev-head">
                        <strong>{a.filename}</strong>
                        <span className="tag">{a.artifact_type}</span>
                        {a.schema_valid === true && (
                          <span className="tag status-succeeded">schema ok</span>
                        )}
                        {a.schema_valid === false && (
                          <span className="tag status-failed">schema fail</span>
                        )}
                        {a.size_bytes != null && (
                          <span className="tag">{a.size_bytes} B</span>
                        )}
                      </div>
                      <a
                        href={artifactDownloadUrl(taskId, a.filename)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        下载 {a.filename}
                      </a>
                      {a.schema_error && (
                        <p className="err">{a.schema_error}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}

            {!artifactRows.length && research.artifact_summary && (
              <>
                <h3>产物</h3>
                <p className="meta">
                  count={String(research.artifact_summary.artifact_count)} ·{" "}
                  {Array.isArray(research.artifact_summary.artifacts)
                    ? (research.artifact_summary.artifacts as string[]).join(
                        ", ",
                      )
                    : ""}
                </p>
              </>
            )}
          </section>
        )}

        {result?.result && !research && result.status === "succeeded" && (
          <section className="panel result">
            <h2>RAG 检索结果</h2>
            <p className="meta">
              confidence=<strong>{result.result.confidence}</strong>
              {result.duration_ms != null && <> · {result.duration_ms} ms</>}
            </p>
            <pre className="answer">{result.result.answer}</pre>
            <h3>证据列表</h3>
            <ul className="evidence">
              {result.result.evidence.map((ev, i) => (
                <li key={`${ev.evidence_id}-${i}`}>
                  <div className="ev-head">
                    <strong>{ev.evidence_id || "unknown"}</strong>
                    {ev.kind && <span className="tag">{ev.kind}</span>}
                  </div>
                  {ev.title && <p className="ev-title">{ev.title}</p>}
                  {ev.source_url ? (
                    <a href={ev.source_url} target="_blank" rel="noreferrer">
                      {ev.source_url}
                    </a>
                  ) : (
                    <span className="muted">no source_url</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  );
}
