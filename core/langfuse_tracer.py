# core/langfuse_tracer.py
"""
Langfuse 可观测性集成模块。
提供装饰器和上下文管理器，让所有关键操作自动记录追踪数据。

知识点：
- Langfuse SDK 的 Trace/Span/Generation 三级层次
- Python contextmanager 上下文管理器的 yield 用法
- with 语句的本质（__enter__ / __exit__）
"""

import os
import time
import functools
from contextlib import contextmanager
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Langfuse 初始化
# 注意：如果 .env 里没有填 Langfuse Key，使用 disabled=True 静默禁用，不报错
_langfuse_enabled = bool(
    os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
)

if _langfuse_enabled:
    from langfuse import Langfuse
    _lf_client = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    )
else:
    _lf_client = None
    print("⚠️  Langfuse 未配置，追踪功能已禁用。如需启用，请在 .env 填写 Langfuse Keys。")


class ReviewTrace:
    """
    代表一次完整审查任务的追踪对象。
    用法（with 语句）：
    
        with ReviewTrace(session_id="xxx", file_name="main.py") as trace:
            trace.add_span("ast_parsing", lambda: parse_code(code))
            trace.add_span("memory_recall", lambda: recall_memory(summary))
    """
    
    def __init__(self, session_id: str, file_name: str, language: str = "unknown"):
        self.session_id = session_id
        self.file_name = file_name
        self.language = language
        self._trace = None
        self._start_time = None
    
    def __enter__(self):
        self._start_time = time.time()
        if _lf_client:
            # 创建 Trace（对应一次完整的代码审查请求）
            self._trace = _lf_client.trace(
                name="code_review",
                session_id=self.session_id,
                metadata={
                    "file_name": self.file_name,
                    "language": self.language,
                },
            )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """with 块结束时自动调用，记录总耗时"""
        total_time = time.time() - self._start_time
        if self._trace:
            # 更新 Trace 状态（成功或失败）
            status = "ERROR" if exc_type else "SUCCESS"
            self._trace.update(
                status=status,
                metadata={"total_seconds": round(total_time, 2)},
            )
            # flush 确保数据发送（异步批量发送，flush 强制同步）
            _lf_client.flush()
        return False  # 不吞掉异常
    
    @contextmanager
    def span(self, name: str, metadata: dict = None):
        """
        记录一个步骤的耗时（Span）。
        
        用法：
            with trace.span("ast_parsing", {"lines": 200}):
                result = parse_code(code)  # 这里的耗时会被自动记录
        
        contextmanager 装饰器知识点：
        - yield 之前的代码 = __enter__
        - yield 之后的代码 = __exit__
        - try/finally 确保 __exit__ 一定执行（即使出现异常）
        """
        start = time.time()
        span_obj = None
        
        if self._trace:
            span_obj = self._trace.span(name=name, metadata=metadata or {})
        
        try:
            yield  # 这里执行 with 块内的代码
        finally:
            elapsed = time.time() - start
            if span_obj:
                span_obj.end(metadata={"duration_seconds": round(elapsed, 3)})
            else:
                print(f"  [{name}] 耗时: {elapsed:.2f}s")  # 没有 Langfuse 时退化到 print
    
    def log_generation(self, name: str, model: str, prompt: str, 
                        response: str, input_tokens: int = 0, output_tokens: int = 0):
        """
        记录一次 LLM 调用的详细信息（Generation）。
        CrewAI 的每次 Agent 调用后手动调用此函数记录。
        """
        if self._trace:
            self._trace.generation(
                name=name,
                model=model,
                input=prompt[:1000],  # 截断，避免存储过多数据
                output=response[:2000],
                usage={
                    "input": input_tokens,
                    "output": output_tokens,
                    "unit": "TOKENS",
                }
            )