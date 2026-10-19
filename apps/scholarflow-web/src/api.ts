/** ScholarFlow API client — all backend calls go through here. */

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export type TaskStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "partial_succeeded"
  | "failed"
  | "timed_out";

export type TaskKind =
  | "rag_query"
  | "research_orchestration"
  | "paper_research"
  | "repository_analysis"
  | "experiment_design";

export type DataMode = "fixture" | "live";

export interface EvidenceItem {
  evidence_id?: string | null;
  kind?: string | null;
  title?: string | null;
  text?: string | null;
  source_url?: string | null;
  score?: number | null;
  verification_status?: string | null;
}

export interface SubtaskStatusItem {
  subtask_id: string;
  role: string;
  status: string;
  depends_on: string[];
  started_at?: number | null;
  ended_at?: number | null;
  duration_ms?: number | null;
  error?: string | null;
  summary?: string | null;
  data_source?: string | null;
}

export interface ArtifactMeta {
  artifact_id: string;
  artifact_type: string;
  filename: string;
  path: string;
  created_at: string;
  data_mode: string;
  schema_valid?: boolean | null;
  schema_error?: string | null;
  size_bytes?: number;
  evidence_refs?: string[];
}

export interface ArtifactManifest {
  task_id: string;
  created_at: string;
  data_mode: string;
  overwrite_policy?: string;
  artifacts: ArtifactMeta[];
}

export interface TaskCreateResponse {
  task_id: string;
  status: TaskStatus;
  kind: string;
  created_at: string;
  message: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: TaskStatus;
  kind: string;
  question: string;
  created_at: string;
  updated_at: string;
  runtime: string;
  error?: string | null;
  progress?: string | null;
  subtasks?: SubtaskStatusItem[];
}

export interface TaskResultResponse {
  task_id: string;
  status: TaskStatus;
  kind: string;
  question: string;
  runtime: string;
  result?: {
    question: string;
    answer: string;
    confidence: string;
    evidence: EvidenceItem[];
    need_mcp_fallback: boolean;
    retrieval: Record<string, unknown>;
  } | null;
  research?: {
    workflow_mode: string;
    overall_status: string;
    review_decision?: string | null;
    research_plan?: Record<string, unknown> | null;
    papers: Record<string, unknown>[];
    repositories: Record<string, unknown>[];
    experiment: Record<string, unknown>;
    reviews: Record<string, unknown>[];
    subtasks: SubtaskStatusItem[];
    events: Record<string, unknown>[];
    mcp_calls?: Record<string, unknown>[];
    degradation_events?: Record<string, unknown>[];
    artifact_summary?: Record<string, unknown> | null;
    artifact_manifest?: ArtifactManifest | null;
    report_excerpt?: string | null;
    data_mode: string;
    effective_data_mode?: string | null;
  } | null;
  artifacts?: { label: string; path: string; kind: string }[];
  index_info?: Record<string, unknown> | null;
  error?: string | null;
  duration_ms?: number | null;
  subtasks?: SubtaskStatusItem[];
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  runtime: string;
  runtimes?: string[];
  harness_importable: boolean;
  artifacts_dir_exists: boolean;
  langgraph_available?: boolean;
  llm_configured?: boolean;
  llm_model?: string | null;
  llm_provider?: string | null;
}

/* ---------- Chat / conversations (Phase 8.1–8.4) ---------- */

export type MessageRole = "user" | "assistant" | "system" | "tool";

export interface ToolCallTraceItem {
  tool_name: string;
  tool_call_id?: string | null;
  arguments?: Record<string, unknown>;
  status: "pending" | "running" | "succeeded" | "failed";
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  result_summary?: string | null;
}

export interface EvidenceRef {
  evidence_id?: string | null;
  source_url?: string | null;
  title?: string | null;
  kind?: string | null;
  authors?: string[];
  year?: number | null;
  abstract?: string | null;
  kind_hint?: string | null;
  relevance_score?: number | null;
}

export interface ChatMessage {
  message_id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  created_at: string;
  tool_call_trace?: ToolCallTraceItem[];
  related_task_id?: string | null;
  evidence_refs?: EvidenceRef[];
}

export interface ConversationMeta {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  metadata?: Record<string, unknown>;
}

export type SseEventType =
  | "turn_start"
  | "token"
  | "tool_start"
  | "tool_end"
  | "workflow_progress"
  | "error"
  | "done";

export interface SseEvent {
  event: SseEventType;
  turn_id: string;
  conversation_id: string;
  ts?: string;
  user_message_id?: string;
  model?: string | null;
  text?: string;
  iteration?: number;
  tool_name?: string;
  tool_call_id?: string;
  arguments_summary?: Record<string, unknown>;
  status?: string;
  duration_ms?: number | null;
  result_summary?: string | null;
  error?: string | null;
  message?: string;
  task_id?: string | null;
  overall_status?: string | null;
  stage?: string | null;
  assistant_message_id?: string | null;
  related_task_id?: string | null;
  iterations?: number;
  latency_ms?: number | null;
}

async function parseError(resp: Response): Promise<string> {
  try {
    const data = await resp.json();
    if (typeof data.detail === "string") return data.detail;
    return JSON.stringify(data.detail ?? data);
  } catch {
    return resp.statusText || `HTTP ${resp.status}`;
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  const resp = await fetch(`${API_BASE}/health`);
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

export async function createTask(
  kind: TaskKind,
  question: string,
  extras: Record<string, unknown> = {},
): Promise<TaskCreateResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kind,
      question,
      top_k: 5,
      ensure_index: true,
      force_reindex: false,
      verified_only: false,
      data_mode: "fixture",
      persist_artifacts: true,
      ...extras,
    }),
  });
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

/** @deprecated use createTask */
export async function createRagTask(question: string): Promise<TaskCreateResponse> {
  return createTask("rag_query", question);
}

export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/tasks/${taskId}`);
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

export async function getTaskResult(taskId: string): Promise<TaskResultResponse> {
  const resp = await fetch(`${API_BASE}/api/v1/tasks/${taskId}/result`);
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

export async function listTaskArtifacts(taskId: string): Promise<ArtifactManifest> {
  const resp = await fetch(`${API_BASE}/api/v1/tasks/${taskId}/artifacts`);
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

export function artifactDownloadUrl(taskId: string, filename: string): string {
  return `${API_BASE}/api/v1/tasks/${taskId}/artifacts/${encodeURIComponent(filename)}`;
}

export function isTerminal(status: TaskStatus): boolean {
  return (
    status === "succeeded" ||
    status === "partial_succeeded" ||
    status === "failed" ||
    status === "timed_out"
  );
}

export async function listConversations(): Promise<{
  conversations: ConversationMeta[];
  total: number;
}> {
  const resp = await fetch(`${API_BASE}/api/v1/conversations`);
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

export async function createConversation(
  title?: string,
): Promise<{ conversation: ConversationMeta; message: string }> {
  const resp = await fetch(`${API_BASE}/api/v1/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(title ? { title } : {}),
  });
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

export async function getConversation(id: string): Promise<ConversationMeta> {
  const resp = await fetch(`${API_BASE}/api/v1/conversations/${id}`);
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

export async function deleteConversation(
  id: string,
): Promise<{ conversation_id: string; status: string }> {
  const resp = await fetch(`${API_BASE}/api/v1/conversations/${id}`, {
    method: "DELETE",
  });
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

export async function getConversationMessages(id: string): Promise<{
  conversation_id: string;
  messages: ChatMessage[];
  total: number;
}> {
  const resp = await fetch(`${API_BASE}/api/v1/conversations/${id}/messages`);
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

export async function cancelTurn(
  conversationId: string,
  turnId: string,
): Promise<{ turn_id: string; cancelled: boolean; message: string }> {
  const resp = await fetch(
    `${API_BASE}/api/v1/conversations/${conversationId}/turns/${turnId}/cancel`,
    { method: "POST" },
  );
  if (!resp.ok) throw new Error(await parseError(resp));
  return resp.json();
}

function parseSseBlock(block: string): SseEvent | null {
  const lines = block.split(/\r?\n/);
  let eventName: string | null = null;
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    const payload = JSON.parse(dataLines.join("\n")) as SseEvent;
    if (eventName && !payload.event) payload.event = eventName as SseEventType;
    return payload;
  } catch {
    return null;
  }
}

export type StreamHandlers = {
  onEvent: (ev: SseEvent) => void;
  onError?: (err: Error) => void;
};

/** Real SSE via fetch streaming (POST body). Not EventSource. */
export async function streamConversationTurn(
  conversationId: string,
  content: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(
    `${API_BASE}/api/v1/conversations/${conversationId}/turns/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ content }),
      signal,
    },
  );
  if (!resp.ok) {
    throw new Error(await parseError(resp));
  }
  if (!resp.body) {
    throw new Error("No response body for SSE stream");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const trimmed = part.trim();
        if (!trimmed) continue;
        const ev = parseSseBlock(trimmed);
        if (ev) handlers.onEvent(ev);
      }
    }
    if (buffer.trim()) {
      const ev = parseSseBlock(buffer.trim());
      if (ev) handlers.onEvent(ev);
    }
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    handlers.onError?.(err instanceof Error ? err : new Error(String(err)));
    throw err;
  }
}

export function toolDisplayLabel(name: string): string {
  switch (name) {
    case "search_papers":
      return "正在检索论文";
    case "scholar_rag_query":
      return "正在查询科研知识库";
    case "run_research_workflow":
      return "正在执行综合科研工作流";
    case "get_research_task":
      return "正在查询科研任务状态";
    case "list_research_artifacts":
      return "正在列出科研产物";
    default:
      return `正在执行工具：${name}`;
  }
}
