# ScholarFlow Phase 5 — Sandbox 产品化（轻量、可验证、非绝对安全）

## 阶段 4 指标审计摘要

完整核查见 [`docs/scholarflow-phase4-metrics-audit.md`](scholarflow-phase4-metrics-audit.md)。

要点：
- 忠实度为**子串协议、无 Judge**；简历 **0.62 无原始记录**。
- Top-5 按**题**统计，分母 **37**。
- 引用准确率验证 ID/URL/弱 overlap，**非**强语义蕴含。
- MCP↓ 用 Mock cold→indexed，同主题 **60%**，未达 77%。
- baseline MCP=0 与 full_rag MCP=28 **不宜**直接比调用量。

---

## 现有能力核验

| 组件 | 状态 |
|------|------|
| ScholarFlow `LocalSandbox` | 宿主进程执行；官方亦声明非安全边界（需 `allow_host_bash`） |
| AIO/Boxlite/E2B | 依赖 Docker/K8s/外部服务，默认不适合 8GB 常开 |
| ScholarFlow 专用 | **阶段 5 新增** `scholarflow.scholar.sandbox` |

## 实现

### 调用链

1. **API**：`POST /api/v1/sandbox/execute`
2. **MCP**：`execute_sandbox_python`（stdio 真实协议）
3. **核心**：`scholarflow.scholar.sandbox.execute_sandbox`

### 输入 / 输出

- 输入：`task_id`, `code`, `timeout_seconds`, `memory_mb`, `max_output_bytes`, `allow_network`, `prefer_docker`
- 输出：`status`（succeeded/failed/timed_out/rejected/resource_exhausted）、`backend`、`exit_code`、`duration_ms`、`stdout`/`stderr`、`error_summary`、`limits`、`security_notes`

### 安全控制（已实现）

| 控制 | process_jail | docker（按需） |
|------|--------------|----------------|
| 超时 | ✓ | ✓ |
| 输出大小上限 | ✓ | ✓ |
| 静态拒绝 subprocess/ctypes/eval/网络 import | ✓ | ✓（执行前同样检查） |
| 路径穿越字面量拒绝 | ✓ | ✓ |
| 每 task 独立 workdir | ✓ | ✓ |
| 网络默认关 | import 策略 + 清 proxy（**非 OS 级**） | `--network=none` |
| 内存硬限制 | **未强制（Windows）** | `--memory` |
| 只读根文件系统 | — | `--read-only` + tmpfs |

### 明确不做 / 风险

- **不**把 process_jail 或普通 Docker 描述为绝对安全隔离。
- **不**默认启动整套 ScholarFlow Docker（`scholarflow-dev` / `scholarflow-front` 等）；阶段 5 只需 **Docker Desktop 引擎**，Sandbox 按需 `--rm` 起一次性 `python:3.12-alpine`。
- process_jail 已知缺口：绝对路径可读宿主机文件（无 `../` 字面量时静态策略拦不住）——见下方补充验收。
- Agent 生成代码**禁止**直接 `exec` 于宿主机任意路径；必须经本 API/MCP。

## 测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_scholar_sandbox.py -q

cd ..\apps\scholarflow-api
..\..\backend\.venv\Scripts\python.exe -m pytest tests/test_sandbox_api.py tests/test_mcp_sandbox.py -q

# process_jail 补充脚本
..\..\backend\.venv\Scripts\python.exe ..\..\scripts\verify_scholar_sandbox.py

# Docker 最小实测（需 Desktop 引擎已启动；无需开 scholarflow 容器）
..\..\backend\.venv\Scripts\python.exe ..\..\scripts\verify_scholar_sandbox_docker.py
```

覆盖：正常执行、超时、危险 import 拒绝、路径字面量拒绝、输出截断、task 目录隔离、API/MCP 调用、Docker 按需后端。

## 启动验证

```powershell
# API
cd apps\scholarflow-api
..\..\backend\.venv\Scripts\python.exe -m uvicorn scholarflow_api.app:app --port 8100

# 示例（无害）
curl -X POST http://127.0.0.1:8100/api/v1/sandbox/execute -H "Content-Type: application/json" -d "{\"task_id\":\"sf-demo\",\"code\":\"print(1+1)\\n\",\"prefer_docker\":false}"
```

## 补充验收记录（2026-10-18）

| 检查项 | 结果 | 证据 |
|--------|------|------|
| API `POST /api/v1/sandbox/execute` | **通过** | `tests/test_sandbox_api.py` |
| MCP `execute_sandbox_python` 真实 stdio | **通过** | `tests/test_mcp_sandbox.py`（子进程 `stdin=DEVNULL` 修复嵌套挂起） |
| process_jail：成功/超时/失败/截断/目录隔离 | **通过** | `scripts/verify_scholar_sandbox.py` |
| process_jail：绝对路径读宿主机 | **已知缺口** | 同脚本 `ABS_HOST_READ_GAP` — 非容器级隔离 |
| Docker 后端最小执行 | **通过** | `scripts/verify_scholar_sandbox_docker.py` → `backend=docker`，`in-docker`/`2` |
| ScholarFlow compose 全栈 | **未启动（刻意）** | 阶段 5 不需要 `scholarflow-*` 容器 |

说明：本机默认 `docker pull python:3.12-alpine` 受坏镜像源影响时，可用 DaoCloud 拉取后 `docker tag ... python:3.12-alpine`。

## 状态总表

| 项 | 状态 |
|----|------|
| 受控执行 API/MCP | **已实现且已验证** |
| 超时 / 拒绝危险代码 / 路径策略 | **已实现且已验证** |
| Docker 按需隔离 | **已实现且已最小化实测**（引擎开即可；勿开整栈） |
| process_jail 绝对路径逃逸 | **有风险 / 已记录** |
| 生产级安全 / 内核隔离保证 | **未完成 / 有风险** — 勿对外宣称 |
| ScholarFlow 全量 Sandbox 产品化 | **未做**（刻意避开 8GB 整栈） |
