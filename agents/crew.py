## CrewAI Crew 定义（agents/crew.py）
# agents/crew.py
"""
CrewAI 核心：定义 Agent、Task 和 Crew。

关键知识点：
- Agent 是"能力主体"，Task 是"工作单"，Crew 是"编排者"
- context 参数让 Task 之间传递中间结果（不需要手动管理状态）
- Process.sequential：task1 完成 → task2 开始，task2 能看到 task1 的输出
"""

from crewai import Agent, Task, Crew, Process
from core.llm import get_llm
from tools.code_tools import get_code_tools
from tools.memory_tools import get_memory_tools
from tools.git_tools import get_git_tools
from agents.prompts import (
    ARCHITECTURE_AGENT_ROLE, ARCHITECTURE_AGENT_GOAL, ARCHITECTURE_AGENT_BACKSTORY,
    ARCHITECTURE_TASK_DESC,
    SECURITY_AGENT_ROLE, SECURITY_AGENT_GOAL, SECURITY_AGENT_BACKSTORY,
    SECURITY_TASK_DESC,
    PERFORMANCE_AGENT_ROLE, PERFORMANCE_AGENT_GOAL, PERFORMANCE_AGENT_BACKSTORY,
    PERFORMANCE_TASK_DESC,
    STYLE_AGENT_ROLE, STYLE_AGENT_GOAL, STYLE_AGENT_BACKSTORY,
    STYLE_TASK_DESC,
    WRITER_AGENT_ROLE, WRITER_AGENT_GOAL, WRITER_AGENT_BACKSTORY,
    WRITER_TASK_DESC,
)


def build_review_crew(
    code_structure: str,
    code_snippet: str,
    memory_context: str,
    file_name: str,
) -> Crew:
    """
    构建并返回代码审查 Crew。
    
    设计思路：
    - 前四个 Agent 并行分析不同维度（但 Sequential 模式下仍顺序执行）
    - Writer Agent 在最后，context 参数接收前四个 Task 的输出
    - 每个 Agent 都有相同的 LLM，但 Prompt 不同（专职专干）
    
    可选优化（面试加分点）：
    - 前三个 Task（架构/安全/性能）可以用 Process.hierarchical + manager_llm 并行执行
    - 但并行会增加 Manager LLM 的 Token 开销，Sequential 在资源有限时更合适
    """
    llm = get_llm(temperature=0.1)
    code_tools = get_code_tools()
    memory_tools = get_memory_tools()
    
    # ===== 定义五个专家 Agent =====
    
    architecture_agent = Agent(
        role=ARCHITECTURE_AGENT_ROLE,
        goal=ARCHITECTURE_AGENT_GOAL,
        backstory=ARCHITECTURE_AGENT_BACKSTORY,
        llm=llm,
        tools=code_tools + memory_tools,
        verbose=True,        # 打印执行过程（调试用）
        allow_delegation=False,  # 禁止将任务委派给其他 Agent（保持专职）
        max_iter=3,          # 最多迭代 3 次（ReAct 循环上限，防止死循环）
    )
    
    security_agent = Agent(
        role=SECURITY_AGENT_ROLE,
        goal=SECURITY_AGENT_GOAL,
        backstory=SECURITY_AGENT_BACKSTORY,
        llm=llm,
        tools=code_tools + memory_tools,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )
    
    performance_agent = Agent(
        role=PERFORMANCE_AGENT_ROLE,
        goal=PERFORMANCE_AGENT_GOAL,
        backstory=PERFORMANCE_AGENT_BACKSTORY,
        llm=llm,
        tools=code_tools,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )
    
    style_agent = Agent(
        role=STYLE_AGENT_ROLE,
        goal=STYLE_AGENT_GOAL,
        backstory=STYLE_AGENT_BACKSTORY,
        llm=llm,
        tools=code_tools,
        verbose=True,
        allow_delegation=False,
        max_iter=2,  # 规范检查迭代次数少，节省 Token
    )
    
    writer_agent = Agent(
        role=WRITER_AGENT_ROLE,
        goal=WRITER_AGENT_GOAL,
        backstory=WRITER_AGENT_BACKSTORY,
        llm=llm,              # Writer 不需要工具，只负责汇总整合
        tools=[],
        verbose=True,
        allow_delegation=False,
        max_iter=2,
    )
    
    # ===== 定义 Task（工作单）=====
    # Task 的 description 中 {} 占位符由 Python format() 填充
    
    architecture_task = Task(
        description=ARCHITECTURE_TASK_DESC.format(
            code_structure=code_structure,
            code_snippet=code_snippet[:3000],  # 限制长度避免超 Token
            memory_context=memory_context,
        ),
        expected_output="一份包含架构问题列表和改进建议的 Markdown 分析报告",
        agent=architecture_agent,
    )
    
    security_task = Task(
        description=SECURITY_TASK_DESC.format(
            code_structure=code_structure,
            code_snippet=code_snippet[:3000],
            memory_context=memory_context,
        ),
        expected_output="一份包含安全漏洞（附严重等级和修复方案）的 Markdown 安全报告",
        agent=security_agent,
    )
    
    performance_task = Task(
        description=PERFORMANCE_TASK_DESC.format(
            code_structure=code_structure,
            code_snippet=code_snippet[:3000],
            memory_context=memory_context,
        ),
        expected_output="一份包含性能瓶颈分析和优化方案的 Markdown 性能报告",
        agent=performance_agent,
    )
    
    style_task = Task(
        description=STYLE_TASK_DESC.format(
            code_structure=code_structure,
            code_snippet=code_snippet[:3000],
        ),
        expected_output="一份包含规范问题清单的 Markdown 规范报告",
        agent=style_agent,
    )
    
    # Writer Task：context 参数传入前四个 Task，Writer 能看到它们的输出
    # 这是 CrewAI 中任务间数据传递的核心机制
    writer_task = Task(
        description=WRITER_TASK_DESC.format(
            all_analysis_results="（由前四个专家的分析结果自动填充）",
            file_name=file_name,
        ),
        expected_output="一份完整的代码审查报告，包含评分表、优先级清单和详细分析",
        agent=writer_agent,
        context=[architecture_task, security_task, performance_task, style_task],
        # context 的作用：CrewAI 会把这四个 Task 的输出拼接后传给 Writer Agent
    )
    
    # ===== 组建 Crew =====
    crew = Crew(
        agents=[architecture_agent, security_agent, performance_agent, 
                style_agent, writer_agent],
        tasks=[architecture_task, security_task, performance_task, 
               style_task, writer_task],
        process=Process.sequential,  # 顺序执行：前一个完成才开始下一个
        verbose=True,
        # memory=True,  # 可选：开启 CrewAI 内置的跨任务记忆（会增加 Token 消耗）
    )
    
    return crew