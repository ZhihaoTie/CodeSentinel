# mcp_server/filesystem_server.py
"""
自实现 MCP Server，暴露三个工具：
  1. read_file       - 读取指定路径的代码文件
  2. git_diff        - 获取仓库最近一次提交的 diff
  3. scan_directory  - 扫描目录，返回代码文件列表

知识点：
  - MCP Server 基于 mcp Python SDK 实现
  - 使用 stdio 传输层（同进程内通信，延迟最低）
  - 每个 Tool 用 @server.call_tool() 装饰器注册
  - Tool 的输入 Schema 用 JSON Schema 描述（类似 OpenAPI）
"""

import asyncio
import os
import json
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ListToolsResult,
)

# ========= 初始化 MCP Server =========
# Server 的 name 是标识符，Client 连接时会看到这个名称
app = Server("codesentinel-filesystem")


# ========= 注册工具列表（Client 调用 list_tools 时返回）=========
@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    告诉 Client 这个 Server 能提供哪些工具。
    每个 Tool 包含：name（工具名）、description（功能描述）、inputSchema（参数 Schema）
    Agent 会读取这个列表决定调用哪个工具。
    """
    return [
        Tool(
            name="read_file",
            description="读取指定路径的代码文件内容。支持 Python/JavaScript/Java/Go 等主流语言。",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "要读取的文件的绝对路径或相对路径",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "最多读取的行数，默认 500，防止超长文件导致 Token 爆炸",
                        "default": 500,
                    }
                },
                "required": ["file_path"],  # file_path 是必填参数
            },
        ),
        Tool(
            name="git_diff",
            description="获取 Git 仓库最近一次提交（或工作区）与上一次提交的差异（diff），用于增量代码审查。",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Git 仓库的根目录路径",
                    },
                    "compare_with": {
                        "type": "string",
                        "description": "比较目标，'HEAD~1'表示与上一次提交比较，'staged'表示暂存区",
                        "default": "HEAD~1",
                    }
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="scan_directory",
            description="扫描目录，递归列出所有代码文件，返回文件路径列表和基础统计信息。",
            inputSchema={
                "type": "object",
                "properties": {
                    "dir_path": {
                        "type": "string",
                        "description": "要扫描的目录路径",
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要扫描的文件扩展名列表，如 ['.py', '.js']，默认扫描常见代码文件",
                        "default": [".py", ".js", ".ts", ".java", ".go", ".cpp", ".c"],
                    },
                    "max_files": {
                        "type": "integer",
                        "description": "最多返回的文件数，避免大型项目返回过多文件",
                        "default": 50,
                    }
                },
                "required": ["dir_path"],
            },
        ),
    ]


# ========= 实现工具调用逻辑 =========
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    MCP Client 调用工具时触发此函数。
    name: 工具名（对应 list_tools 里注册的 name）
    arguments: Client 传入的参数（对应 inputSchema 里定义的字段）
    返回值：TextContent 列表（每个 TextContent 是一段文本输出）
    """
    
    if name == "read_file":
        return await _read_file(
            arguments["file_path"],
            arguments.get("max_lines", 500)
        )
    elif name == "git_diff":
        return await _git_diff(
            arguments["repo_path"],
            arguments.get("compare_with", "HEAD~1")
        )
    elif name == "scan_directory":
        return await _scan_directory(
            arguments["dir_path"],
            arguments.get("extensions", [".py", ".js", ".ts", ".java", ".go"]),
            arguments.get("max_files", 50)
        )
    else:
        # 未知工具名，返回错误信息（MCP 规范要求处理此情况）
        return [TextContent(type="text", text=f"错误：未知工具 '{name}'")]


# ========= 工具实现函数 =========

async def _read_file(file_path: str, max_lines: int) -> list[TextContent]:
    """读取文件内容，处理编码问题和超长文件截断"""
    try:
        path = Path(file_path)
        if not path.exists():
            return [TextContent(type="text", text=f"错误：文件不存在 {file_path}")]
        if not path.is_file():
            return [TextContent(type="text", text=f"错误：{file_path} 不是文件")]
        
        # 检测文件大小，避免读取二进制文件
        file_size = path.stat().st_size
        if file_size > 1_000_000:  # 超过 1MB 的文件拒绝读取
            return [TextContent(type="text", text=f"文件太大 ({file_size/1024:.1f}KB)，请提供更小的代码文件")]
        
        # 读取内容，尝试 UTF-8，失败则用 latin-1（兜底编码）
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")
        
        # 截断超长文件
        lines = content.split('\n')
        if len(lines) > max_lines:
            content = '\n'.join(lines[:max_lines])
            content += f"\n\n... [文件共 {len(lines)} 行，已截取前 {max_lines} 行] ..."
        
        result = {
            "file_path": str(path.absolute()),
            "language": _detect_language(path.suffix),
            "total_lines": len(lines),
            "content": content,
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    
    except Exception as e:
        return [TextContent(type="text", text=f"读取文件失败: {str(e)}")]


async def _git_diff(repo_path: str, compare_with: str) -> list[TextContent]:
    """获取 Git diff，用于增量审查只改动的代码"""
    try:
        import git  # gitpython
        repo = git.Repo(repo_path)
        
        if compare_with == "staged":
            # 获取暂存区 diff
            diff = repo.git.diff("--cached")
        elif compare_with == "HEAD~1":
            # 获取最近一次提交的 diff
            if len(repo.commits) < 2:
                diff = repo.git.diff("HEAD")
            else:
                diff = repo.git.diff("HEAD~1", "HEAD")
        else:
            diff = repo.git.diff(compare_with)
        
        if not diff.strip():
            return [TextContent(type="text", text="没有发现代码变更。")]
        
        # diff 太长时截断
        if len(diff) > 8000:
            diff = diff[:8000] + "\n... [diff 已截断，只显示前 8000 字符] ..."
        
        result = {
            "repo_path": repo_path,
            "compare_with": compare_with,
            "diff": diff,
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    
    except git.InvalidGitRepositoryError:
        return [TextContent(type="text", text=f"错误：{repo_path} 不是一个有效的 Git 仓库")]
    except Exception as e:
        return [TextContent(type="text", text=f"获取 Git diff 失败: {str(e)}")]


async def _scan_directory(dir_path: str, extensions: list, max_files: int) -> list[TextContent]:
    """递归扫描目录，返回代码文件列表"""
    try:
        path = Path(dir_path)
        if not path.exists() or not path.is_dir():
            return [TextContent(type="text", text=f"错误：目录不存在 {dir_path}")]
        
        # 需要排除的目录（不审查依赖包、缓存等）
        EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
                       "dist", "build", ".idea", ".vscode", "vendor"}
        
        found_files = []
        for file in path.rglob("*"):
            # 跳过被排除的目录
            if any(excluded in file.parts for excluded in EXCLUDE_DIRS):
                continue
            if file.is_file() and file.suffix in extensions:
                found_files.append({
                    "path": str(file.relative_to(path)),
                    "size_kb": round(file.stat().st_size / 1024, 2),
                    "language": _detect_language(file.suffix),
                })
                if len(found_files) >= max_files:
                    break
        
        result = {
            "dir_path": dir_path,
            "total_files_found": len(found_files),
            "is_truncated": len(found_files) >= max_files,
            "files": found_files,
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    
    except Exception as e:
        return [TextContent(type="text", text=f"扫描目录失败: {str(e)}")]


def _detect_language(suffix: str) -> str:
    """根据文件扩展名推断编程语言"""
    LANGUAGE_MAP = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".java": "java", ".go": "go", ".cpp": "cpp", ".c": "c",
        ".rs": "rust", ".rb": "ruby", ".php": "php", ".cs": "csharp",
        ".kt": "kotlin", ".swift": "swift", ".sh": "bash",
    }
    return LANGUAGE_MAP.get(suffix.lower(), "unknown")


# ========= 启动入口 =========
async def main():
    """
    以 stdio 模式启动 MCP Server。
    stdio_server() 是 mcp SDK 提供的上下文管理器，
    负责处理 stdin/stdout 的读写和 JSON-RPC 协议解析。
    """
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())