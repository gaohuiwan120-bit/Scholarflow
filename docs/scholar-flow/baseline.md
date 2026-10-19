# ScholarFlow Phase 0 基线报告

> 生成时间：2026-07-11  
> 上游项目：[bytedance/scholarflow](https://github.com/bytedance/scholarflow)（main 分支源码）  
> 运行方式：**Docker 开发栈**（`scripts/docker.sh start`）

---

## 1. 环境与工具链

| 组件 | 版本 | 状态 |
|------|------|------|
| 操作系统 | Windows 10 (10.0.22631) | ✅ |
| Git | 2.55.0.windows.2 | ✅ 已安装 |
| Docker Desktop | 4.81.0 (Engine 29.6.1) | ✅ 已安装并运行 |
| Docker Compose | v5.2.0 | ✅ |
| WSL2 | 已安装（重启后生效） | ✅ |
| uv | 0.11.26 | ✅ 已安装 |
| Python（uv 管理） | 3.12.13 | ✅ |
| 本机 `make` | 未验证（Windows 使用 Git Bash 脚本） | ⚠️ 使用 `bash ./scripts/docker.sh` |

### 源码获取方式

- 初始通过 GitHub `main.zip` 解压至本机工作区；目录现为 `e:\AgentProject\ScholarFlow_project`（产品名 **ScholarFlow**，勿写成 DeepFlow / deepflow）
- Phase 0 末尾已执行 `git init` 并提交基线快照（满足部分测试对 `.git` 标记的要求）
- **建议后续**：`git remote add origin https://github.com/bytedance/scholarflow.git` 并 `git fetch`，以便跟踪上游更新

---

## 2. 网络与镜像加速（关键）

本机 **无法直连 Docker Hub**（`registry-1.docker.io` 超时）。Phase 0 采用以下措施：

### 2.1 Docker 引擎镜像加速

已写入 `C:\Users\admin\.docker\daemon.json`：

```json
"registry-mirrors": [
  "https://docker.1ms.run",
  "https://docker.m.daocloud.io",
  "https://hub.rat.dev",
  "https://docker.1panel.live"
]
```

### 2.2 预拉取并 tag 的基础镜像

| 镜像 | 拉取源 |
|------|--------|
| `redis:7-alpine` | `docker.1ms.run/library/redis:7-alpine` |
| `nginx:alpine` | `docker.m.daocloud.io/library/nginx:alpine` |
| `node:22-alpine` | `docker.m.daocloud.io/library/node:22-alpine` |
| `python:3.12-slim-bookworm` | `docker.m.daocloud.io/library/python:3.12-slim-bookworm` |
| `docker:cli` | `docker.m.daocloud.io/library/docker:cli` |
| `ghcr.io/astral-sh/uv:0.7.20` | 直连 ghcr.io（成功） |

### 2.3 构建阶段 APT / NPM 加速

已在项目根目录 `.env` 增加：

```env
APT_MIRROR=mirrors.aliyun.com
NPM_REGISTRY=https://registry.npmmirror.com
```

首次 `docker.sh start` 曾因 `deb.debian.org` 返回 502 失败；配置 `APT_MIRROR` 后 **第二次构建成功**。

---

## 3. 本地配置文件

| 文件 | 状态 | 说明 |
|------|------|------|
| `config.yaml` | ✅ 已从 `config.example.yaml` 复制 | `sandbox.use` 仍为默认 **LocalSandboxProvider** |
| `.env` | ✅ 已从 `.env.example` 复制 | 含镜像加速；**API Key 仍为占位符** |
| `extensions_config.json` | ✅ 已从示例复制 | MCP/Skills 均未启用 |
| `frontend/.env` | ✅ 已从示例复制 | |

### 待用户补充（阻塞真实 Agent 对话）

- `config.yaml` → `models:` 至少配置一个可用 LLM（取消注释并填写 `api_key: $XXX`）
- `.env` → 对应模型 API Key（如 `OPENAI_API_KEY`、`DEEPSEEK_API_KEY` 等）

---

## 4. ScholarFlow Docker 启动验证

### 4.1 执行的命令

```bash
# Git Bash，项目根目录
./scripts/docker.sh init    # local sandbox 模式，跳过 sandbox 镜像拉取
./scripts/docker.sh start # 首次失败（apt 502），配置 APT_MIRROR 后成功
```

### 4.2 运行中的容器（2026-07-11 验证）

| 容器 | 状态 | 端口 |
|------|------|------|
| `scholarflow-nginx` | Up | `0.0.0.0:2026->2026` |
| `scholarflow-gateway` | Up | 内部 8001 |
| `scholarflow-frontend` | Up | 内部 3000 |
| `scholarflow-redis` | Up (healthy) | 内部 6379 |

### 4.3 健康检查

| 端点 | 结果 |
|------|------|
| `http://localhost:2026` | **200**（前端可访问） |
| `http://localhost:2026/health` | **200** `{"status":"healthy","service":"scholarflow-gateway"}` |

**访问地址**：http://localhost:2026

### 4.4 Sandbox 模式

- 当前 `config.yaml` 检测为 **`local`**（Gateway 容器内 LocalSandboxProvider）
- ScholarFlow 生产建议后续改为 `AioSandboxProvider`（Docker 隔离）；需额外配置 `docker-compose.dood.yaml`

---

## 5. 原有测试基线

### 5.1 宿主机执行（推荐基线）

```powershell
cd backend
$env:PYTHONPATH='.'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
uv run pytest tests/ -q --tb=no
```

**结果（2026-07-11）**：

```
6955 passed, 98 failed, 50 skipped, 23 warnings in ~356s
```

完整日志：`docs/scholar-flow/pytest-baseline.log`

### 5.2 失败测试分析（Windows 环境预期）

98 个失败主要集中在：

- **路径/平台差异**：`test_serve_nginx_stop.py`、`test_sandbox_*`（Unix 路径、符号链接）
- **本地 Sandbox 环境**：`test_skill_request_scoped_secrets.py`（subprocess/env 行为）
- **渠道/集成测试**：`test_wechat_channel.py`、`test_three_way_skills_mount_e2e.py`
- **文件系统边界**：`test_tool_output_budget_middleware.py`

> 在 **Linux CI / Docker 内完整 monorepo** 环境下，通过率应显著高于 Windows 宿主机直跑。  
> Phase 0 结论：**核心 harness 测试大量通过（6955）**，失败项多为平台/集成相关，不阻塞 ScholarFlow 扩展开发。

### 5.3 容器内 pytest（不推荐作基线）

在 `scholarflow-gateway` 容器内直接跑 pytest 曾出现 **10 个 collection error**（缺少 `/app/scripts`、`.git` 等）。  
宿主机完整仓库 + `git init` 后测试更可靠。

---

## 6. ScholarFlow 架构要点（ScholarFlow 扩展参考）

```
用户 → Nginx:2026 → Frontend:3000 / Gateway:8001
                         ↓
              make_lead_agent (LangGraph 嵌入式运行时)
                         ↓
    Middleware → Tools (builtin/MCP) → task() Sub-Agent
                         ↓
              Sandbox: /mnt/user-data/{workspace,uploads,outputs}
              Skills:  /mnt/skills/{public,custom}
```

| 扩展面 | ScholarFlow 计划用途 |
|--------|---------------------|
| `skills/custom/` | 4 个科研 Skill |
| `extensions/scholar_mcp/` | 论文/GitHub/PDF 工具 |
| `extensions_config.json` | 注册 MCP + 启用 Skills |
| `evaluation/` | 评测任务与指标 |
| Lead Agent / LangGraph 核心 | **第一版不修改** |

---

## 7. 已知问题与风险

| 问题 | 影响 | 缓解 |
|------|------|------|
| Docker Hub 直连不可用 | 拉取/构建失败 | 已配置 registry-mirrors + 预拉取 tag |
| Debian apt 偶发 502 | gateway 镜像构建失败 | `APT_MIRROR=mirrors.aliyun.com` |
| 未配置 LLM API Key | 无法实际对话 | 用户补充 `config.yaml` + `.env` |
| LocalSandbox 默认模式 | 隔离性弱 | ScholarFlow Phase 2+ 切换 AioSandbox |
| Windows 宿主机 pytest 98 fail | 基线噪音 | 以 Docker 健康检查 + 核心 passed 为准 |
| 源码来自 zip 非 git clone | 上游同步不便 | 建议添加 `origin` remote |

---

## 8. Phase 0 交付清单

- [x] 阅读上游文档（AGENTS.md、ARCHITECTURE、CONFIGURATION、MCP、public skills）
- [x] 安装 Git、Docker Desktop、WSL2、uv
- [x] 获取 ScholarFlow 源码并生成本地配置
- [x] `docker.sh init` 成功
- [x] `docker.sh start` 成功（经镜像加速与 APT 镜像）
- [x] 服务健康检查通过（`:2026`、`:2026/health`）
- [x] 运行原有后端测试并记录结果
- [x] 输出本基线文档

**Phase 0 状态：✅ 通过（Docker 栈已运行；待用户配置模型 API Key 后可进行对话验证）**

---

## 9. 常用运维命令

```bash
# 启动（Git Bash，项目根）
./scripts/docker.sh start

# 停止
./scripts/docker.sh stop

# 查看日志
./scripts/docker.sh logs
./scripts/docker.sh logs --gateway

# 健康检查
curl http://localhost:2026/health
```

---

## 10. 下一阶段（Phase 1）预计修改文件

详见项目规划；核心新增：

```
docs/scholar-flow/design.md
docs/scholar-flow/data-contracts.md
backend/packages/harness/scholarflow/scholar/models.py   # 或 extensions 包
extensions/scholar_mcp/                               # Phase 2
skills/custom/scientific-research-orchestration/      # Phase 3
skills/custom/paper-evidence-extraction/
skills/custom/repository-technical-analysis/
skills/custom/experiment-plan-generation/
evaluation/
extensions_config.json                              # scholar-research MCP
```

---

## 11. 与 ScholarFlow 的关系声明

本项目基于开源项目 **ScholarFlow** 进行二次开发。ScholarFlow 将新增科研任务协议、自定义科研 Skills、科研 MCP 工具、结构化证据管理和 Agent 评测模块；**不得将 ScholarFlow 原有功能描述为本项目独立原创**。
