# 🛡️ CodeSentinel

> **基于 CrewAI + MCP + Qdrant + Langfuse 的智能代码审查系统**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CrewAI](https://img.shields.io/badge/CrewAI-Multi--Agent-orange)](https://github.com/joaomdmoura/crewAI)
[![MCP](https://img.shields.io/badge/MCP-Protocol-green)](https://modelcontextprotocol.io/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20DB-red)](https://qdrant.tech/)

CodeSentinel 针对企业代码审查效率低、经验难沉淀、质量无法量化等痛点，独立设计并开发了一套基于声明式多智能体与标准化工具协议的智能代码审查系统。它通过五位虚拟专家 Agent 的协作，提供涵盖架构、安全、性能和规范的全方位代码审查。

---

## ✨ 核心特性与创新点

与传统的单次 LLM 调用审查工具不同，CodeSentinel 具备以下核心优势：

1. **自实现 MCP Server (跨框架解耦)**：参照 Anthropic MCP 协议规范，基于 `stdio` 传输模式实现文件系统 MCP Server，暴露 `read_file` / `git_diff` / `scan_directory` 标准化工具端点，实现工具与 Agent 框架的完全解耦。
2. **Tree-sitter AST 结构化解析**：在代码送入 LLM 前提取函数列表、类继承关系、圈复杂度等结构化元数据，将原始代码 Token 消耗压缩约 90%，并提升代码理解精准度。
3. **CrewAI 声明式多 Agent 编排**：基于 Sequential Process 构建五大专家 Agent（架构、安全、性能、规范、总结）协作流水线，通过 `Task.context` 实现跨 Agent 的隐式状态传递。
4. **Qdrant 向量记忆库**：利用 Payload Filter 实现“先精确过滤、再向量搜索”的混合检索策略，从历史审查记录中精准召回相似问题的处理建议。
5. **Langfuse 全链路可观测性**：实现 Trace/Span/Generation 三级链路追踪，实时监控各步骤耗时、Token 消耗和完整 Prompt。
6. **RAGAS 量化评测**：基于 LLM-as-Judge 方式运行 RAGAS 评测，系统忠实度（Faithfulness）0.87，回答相关性（Answer Relevancy）0.91。

---

## 🏗️ 系统架构

```text
┌─────────────────────────────────────────────────────┐
│               用户界面 (Streamlit main.py)           │
└─────────────────────┬───────────────────────────────┘
                       │ HTTP
┌─────────────────────▼───────────────────────────────┐
│              MCP Server (filesystem_server.py)       │
│  Tool 1: read_file    Tool 2: git_diff    Tool 3: scan_dir │
└──────────────┬──────────────────────────┬───────────┘
               │                          │
┌──────────────▼──────┐      ┌────────────▼───────────┐
│  Tree-sitter AST    │      │  Qdrant 历史记忆库       │
│  结构化代码元数据    │      │  相似问题召回检索        │
└──────────────┬──────┘      └────────────┬───────────┘
               │                          │
┌──────────────▼──────────────────────────▼───────────┐
│             CrewAI 多 Agent 审查 Crew                │
│  🔍 架构分析  🔒 安全审计  ⚡ 性能工程  📐 规范检查  📝 总结报告 │
└──────────────────────────┬──────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────┐
│                Langfuse 全链路追踪                    │
└──────────────────────────┬──────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────┐
│         Markdown 审查报告 + RAGAS 质量评分            │
└──────────────────────────────────────────────────────┘
```

---

## 🛠️ 技术栈选型

| 模块 | 技术 | 选型说明 |
| :--- | :--- | :--- |
| **多 Agent 框架** | **CrewAI** | 声明式角色分配，流水线任务编排比图状态机更直观 |
| **工具接入协议** | **MCP (自实现)** | 标准化通信协议，让工具服务化并可被任意框架复用 |
| **代码解析** | **Tree-sitter** | 增量语法树解析，支持多语言 (Python/JS/Java/Go) |
| **向量数据库** | **Qdrant** | 本地模式，支持强大的 Payload 嵌套条件过滤 |
| **可观测性** | **Langfuse** | OpenTelemetry 标准，专为 LLM 打造的链路追踪 |
| **大模型** | **Qwen-Plus / DeepSeek** | 兼容 OpenAI 协议接口，高性价比 |
| **评测体系** | **RAGAS** | Faithfulness / Answer Relevancy / Context Precision 量化 |

---

## 🚀 快速开始

### 1. 环境准备

建议使用 Python 3.10 或 3.11（兼容 Tree-sitter）。

```bash
# 克隆仓库
https://github.com/ZhihaoTie/CodeSentinel.git
cd CodeSentinel

# 创建并激活虚拟环境
python -m venv codesential_env
source codesential_env/bin/activate  # Windows: codesential_env\Scripts\activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

在项目根目录创建 `.env` 文件并填入以下配置：

```env
# 大模型配置
ALIYUN_API_KEY=your_api_key_here
LLM_MODEL=qwen-plus
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# Embedding 模型
EMBEDDING_MODEL=text-embedding-v3

# Langfuse 监控配置 (前往 cloud.langfuse.com 获取)
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com

# Qdrant 本地存储配置
QDRANT_PATH=./qdrant_data
QDRANT_COLLECTION=code_review_memory
```

### 4. 运行系统

```bash
streamlit run main.py
```
启动后，浏览器会自动打开 `http://localhost:8501` 进入交互界面。

---

## 📊 RAGAS 质量评测

系统内置了 RAGAS 评测模块，通过 `LLM-as-Judge` 方式对审查结果进行量化评估，确保 Agent 输出的可靠性。

运行评测验证：
```bash
python -c "
from evaluation.ragas_eval import run_ragas_evaluation, build_eval_dataset, load_test_dataset
test_cases = load_test_dataset()
dataset = build_eval_dataset(test_cases)
scores = run_ragas_evaluation(dataset)
print('评测结果:', scores)
"
```

**基线数据参考**:
* Faithfulness（忠实度）: `~0.87`
* Answer Relevancy（相关性）: `~0.91`
* Context Precision（经验召回精度）: `~0.84`

---

## 📂 核心目录结构

```text
CodeSentinel/
├── .env                          # 密钥配置
├── main.py                       # Streamlit 前端交互入口
├── mcp_server/                   # 核心：自实现 MCP 服务端
│   └── filesystem_server.py      # 提供读文件/Git diff/目录扫描能力
├── core/                         # 基础核心模块
│   ├── ast_parser.py             # Tree-sitter 语法树解析
│   ├── qdrant_memory.py          # Qdrant 经验记忆库
│   └── langfuse_tracer.py        # 监控指标采集
├── agents/                       # 智能体逻辑
│   ├── prompts.py                # 五大专家角色 Prompt 设计
│   └── crew.py                   # CrewAI 编排逻辑
├── tools/                        # 暴露给 Agent 的工具集
├── evaluation/                   # RAGAS 评测流水线
└── outputs/reports/              # 生成的 Markdown 审查报告
```
