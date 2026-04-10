# tools/git_tools.py
"""Git 操作工具"""
from crewai.tools import tool


@tool("get_git_diff")
def get_git_diff_tool(repo_path: str) -> str:
    """
    获取 Git 仓库最近一次 commit 的代码变更内容（diff）。
    适用于增量审查：只审查变更的部分，不审查整个代码库。
    输入：Git 仓库目录路径
    输出：diff 文本
    """
    try:
        import git
        repo = git.Repo(repo_path)
        
        if len(list(repo.iter_commits())) < 2:
            return "仓库只有一次提交记录，返回完整暂存区内容。"
        
        diff = repo.git.diff("HEAD~1", "HEAD", "--stat")
        if not diff:
            return "最近一次提交没有代码变更。"
        
        detailed_diff = repo.git.diff("HEAD~1", "HEAD")
        if len(detailed_diff) > 6000:
            detailed_diff = detailed_diff[:6000] + "\n... [diff 已截断]"
        
        return f"变更统计：\n{diff}\n\n详细变更：\n{detailed_diff}"
    
    except Exception as e:
        return f"获取 Git diff 失败: {str(e)}"


def get_git_tools():
    return [get_git_diff_tool]