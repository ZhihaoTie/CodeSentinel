# tools/memory_tools.py
"""Qdrant 历史经验召回工具"""
from crewai.tools import tool
from core.qdrant_memory import get_review_memory
import json


@tool("recall_historical_issues")
def recall_historical_issues_tool(query: str, language: str = "", issue_type: str = "") -> str:
    """
    从历史审查记忆库中召回相似问题。
    输入：查询描述（当前代码特征）、语言（可选）、问题类型（可选）
    输出：最相似的历史问题列表（含修复建议）
    
    Agent 在开始审查前应先调用此工具，获取历史经验参考。
    """
    memory = get_review_memory()
    
    stats = memory.get_stats()
    if stats["total_records"] == 0:
        return "历史记忆库暂无记录（这是第一次审查），请直接进行分析。"
    
    results = memory.recall_similar_issues(
        query_text=query,
        language=language if language else None,
        issue_type=issue_type if issue_type else None,
        top_k=3,
    )
    
    if not results:
        return "未找到相似历史问题（相似度低于阈值），请直接进行分析。"
    
    output = f"找到 {len(results)} 条历史相似问题：\n\n"
    for i, r in enumerate(results, 1):
        output += f"**历史案例 {i}** （相似度: {r['similarity_score']}）\n"
        output += f"- 类型：{r.get('issue_type', 'N/A')} | 严重度：{r.get('severity', 'N/A')}\n"
        output += f"- 问题：{r.get('issue_summary', 'N/A')}\n"
        output += f"- 建议：{r.get('suggestion', 'N/A')}\n\n"
    
    return output


def get_memory_tools():
    return [recall_historical_issues_tool]