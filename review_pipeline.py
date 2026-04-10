# review_pipeline.py
"""
代码审查主流程。
将 MCP、AST解析、Qdrant记忆、CrewAI、Langfuse 整合为完整流水线。
"""

import uuid
import json
import time
from pathlib import Path
from datetime import datetime
from core.ast_parser import get_code_parser
from core.qdrant_memory import get_review_memory
from core.langfuse_tracer import ReviewTrace
from agents.crew import build_review_crew


def run_code_review(
    file_path: str,
    session_id: str = None,
) -> dict:
    """
    执行一次完整的代码审查。
    
    返回字典包含：
    - report_markdown: 最终审查报告
    - code_structure: 代码结构摘要
    - memory_recalled: 召回的历史经验数量
    - duration_seconds: 总耗时
    - session_id: 本次会话 ID（用于 Langfuse 追踪）
    """
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
    
    path = Path(file_path)
    if not path.exists():
        return {"error": f"文件不存在: {file_path}"}
    
    # 读取代码
    try:
        code_content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"读取文件失败: {e}"}
    
    # 识别语言
    LANG_MAP = {".py": "python", ".js": "javascript", ".ts": "typescript",
                ".java": "java", ".go": "go"}
    language = LANG_MAP.get(path.suffix.lower(), "unknown")
    
    start_time = time.time()
    
    # 全程使用 Langfuse 追踪
    with ReviewTrace(session_id=session_id, file_name=path.name, language=language) as trace:
        
        # ===== Step 1: AST 解析 =====
        with trace.span("ast_parsing", {"file": path.name, "language": language}):
            parser = get_code_parser()
            code_structure = parser.parse(code_content, language)
            structure_text = code_structure.to_summary_text()
        
        # ===== Step 2: 历史经验召回 =====
        memory = get_review_memory()
        memory_results = []
        
        with trace.span("memory_recall", {"collection": "code_review_memory"}):
            memory_results = memory.recall_similar_issues(
                query_text=structure_text,
                language=language,
                top_k=5,
            )
        
        # 格式化历史经验文本，供 Agent Prompt 使用
        if memory_results:
            memory_context = "\n".join([
                f"- [{r['issue_type']}] {r['issue_summary']}: {r['suggestion']}"
                for r in memory_results
            ])
        else:
            memory_context = "（暂无历史相似问题记录）"
        
        # ===== Step 3: CrewAI 多 Agent 审查 =====
        with trace.span("crew_execution"):
            crew = build_review_crew(
                code_structure=structure_text,
                code_snippet=code_content,
                memory_context=memory_context,
                file_name=path.name,
            )
            # kickoff() 是触发 Crew 执行的方法
            # inputs 字典会被注入到每个 Task 的 description 中的 {变量名}
            result = crew.kickoff(inputs={
                "file_name": path.name,
                "language": language,
            })
        
        report = str(result)
        
        # ===== Step 4: 将本次审查结论存入 Qdrant =====
        with trace.span("memory_storage"):
            # 从报告中提取结构化的问题列表（简化处理）
            # 实际项目中可以再调一次 LLM 做结构化提取
            new_findings = _extract_findings_from_report(
                report=report,
                language=language,
            )
            stored_count = memory.store_review_findings(
                findings=new_findings,
                code_summary=structure_text,
            )
        
        # ===== Step 5: 保存报告到文件 =====
        output_dir = Path("outputs/reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"{path.stem}_review_{session_id}.md"
        report_path.write_text(report, encoding="utf-8")
    
    duration = time.time() - start_time
    
    return {
        "report_markdown": report,
        "report_path": str(report_path),
        "code_structure": structure_text,
        "memory_recalled": len(memory_results),
        "memory_stored": stored_count,
        "duration_seconds": round(duration, 2),
        "session_id": session_id,
    }


def _extract_findings_from_report(report: str, language: str) -> list[dict]:
    """
    从审查报告中提取结构化问题列表，存入 Qdrant。
    简化实现：根据 Markdown 标题和关键词提取。
    生产版本：再调一次 LLM 做结构化输出（成本 vs 精度 tradeoff）。
    """
    findings = []
    now = datetime.now().strftime("%Y-%m-%d")
    
    # 简单规则：提取 P0/P1 优先级问题
    lines = report.split('\n')
    current_section = "unknown"
    
    for line in lines:
        if "## 安全" in line:
            current_section = "security"
        elif "## 架构" in line:
            current_section = "architecture"
        elif "## 性能" in line:
            current_section = "performance"
        elif "## 规范" in line:
            current_section = "style"
        
        # 找问题描述行（以 - [ ] 开头的行）
        if line.strip().startswith("- [ ]") or line.strip().startswith("- [x]"):
            issue_text = line.strip().lstrip("- [ ]").lstrip("- [x]").strip()
            if len(issue_text) > 10:
                severity = "high" if "P0" in line or "高危" in line else \
                           "medium" if "P1" in line or "中危" in line else "low"
                findings.append({
                    "issue_type": current_section,
                    "severity": severity,
                    "language": language,
                    "issue_summary": issue_text[:200],
                    "suggestion": "见完整报告",
                    "created_at": now,
                })
    
    return findings[:10]  # 每次最多存 10 条，避免噪音数据污染记忆库