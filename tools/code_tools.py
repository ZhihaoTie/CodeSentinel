# tools/code_tools.py
"""
供 Agent 使用的代码分析工具。
通过 CrewAI 的 @tool 装饰器或 BaseTool 接入到 Agent。
"""
from crewai.tools import tool
from core.ast_parser import get_code_parser
import json


@tool("analyze_code_structure")
def analyze_code_structure_tool(code: str, language: str = "python") -> str:
    """
    用 Tree-sitter 解析代码，返回结构化摘要。
    输入：代码字符串 + 语言名称
    输出：JSON 格式的代码结构摘要
    
    Agent 在需要理解代码结构时调用此工具，
    可减少直接传入原始代码的 Token 消耗。
    """
    parser = get_code_parser()
    structure = parser.parse(code, language)
    return structure.to_summary_text()


@tool("read_code_file")
def read_code_file_tool(file_path: str) -> str:
    """
    读取本地代码文件内容。
    输入：文件路径（绝对路径或相对路径）
    输出：文件内容字符串
    """
    from pathlib import Path
    try:
        path = Path(file_path)
        if not path.exists():
            return f"错误：文件不存在 {file_path}"
        content = path.read_text(encoding="utf-8", errors="replace")
        # 截断超长文件
        lines = content.split('\n')
        if len(lines) > 300:
            content = '\n'.join(lines[:300]) + f"\n... [共 {len(lines)} 行，已截取前300行]"
        return content
    except Exception as e:
        return f"读取失败: {str(e)}"


def get_code_tools():
    """返回代码分析工具列表"""
    return [analyze_code_structure_tool, read_code_file_tool]