# core/llm.py
"""
大模型初始化模块，支持通过环境变量切换不同厂商。
知识点: OpenAI 兼容接口（越来越多的厂商支持这个格式）
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm(temperature: float = 0.1) -> ChatOpenAI:
    """
    获取大模型实例。
    
    temperature 参数说明：
    - 0.0：完全确定性输出，适合代码分析（不需要创意，要精准）
    - 0.1~0.3：低随机性，本项目审查用 0.1
    - 0.7~1.0：高创意，适合写作场景
    
    CrewAI 的每个 Agent 都需要传入一个 LLM 实例。
    """
    api_key = os.getenv("ALIYUN_API_KEY")
    if not api_key:
        raise ValueError("未找到 ALIYUN_API_KEY 环境变量，请检查 .env 文件")
    
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "qwen-plus"),
        api_key=api_key,
        base_url=os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        temperature=temperature,
        # max_tokens 设置单次回复上限，防止 LLM 输出超长报告
        max_tokens=4096,
    )


def get_embedding_model():
    """
    获取 Embedding 模型（用于 Qdrant 向量化）。
    返回一个函数：接收文本，返回 float 向量。
    """
    import dashscope
    from http import HTTPStatus
    
    dashscope.api_key = os.getenv("ALIYUN_API_KEY")
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
    
    def embed(texts: list[str]) -> list[list[float]]:
        """批量将文本转为向量"""
        response = dashscope.TextEmbedding.call(
            model=model,
            input=texts,
        )
        if response.status_code != HTTPStatus.OK:
            raise RuntimeError(f"Embedding 失败: {response.message}")
        return [item["embedding"] for item in response.output["embeddings"]]
    
    return embed