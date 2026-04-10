# evaluation/ragas_eval.py
"""
RAGAS 量化评测模块。
构建标准评测数据集，对系统输出打分。

知识点：
- RAGAS 需要构建 (question, answer, contexts, ground_truth) 四元组数据集
- Faithfulness：用 LLM 判断 answer 中的每个声明是否能从 contexts 中找到依据
- Answer Relevancy：用 LLM 从 answer 反向生成问题，看与原始 question 的语义距离
- Context Precision：判断召回的 contexts 中有多少是真正相关的
"""

import json
from pathlib import Path
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import os
from dotenv import load_dotenv

load_dotenv()


def build_eval_dataset(test_cases: list[dict]) -> Dataset:
    """
    构建 RAGAS 评测数据集。
    
    test_cases 格式：
    [
        {
            "question": "这段代码有什么安全问题？",
            "answer": "（系统生成的审查报告）",
            "contexts": ["（AST摘要）", "（历史经验1）", "（历史经验2）"],
            "ground_truth": "（人工标注的标准答案）"
        },
        ...
    ]
    """
    return Dataset.from_list([
        {
            "question": tc["question"],
            "answer": tc["answer"],
            "contexts": tc["contexts"],
            "ground_truth": tc.get("ground_truth", ""),
        }
        for tc in test_cases
    ])


def run_ragas_evaluation(dataset: Dataset) -> dict:
    """
    运行 RAGAS 评测，返回各维度分数。
    
    注意：RAGAS 评测本身也要调用 LLM（用 LLM-as-Judge），
    所以也会消耗 Token（每条测试数据大约 500-1000 Token）。
    """
    # RAGAS 需要 LangChain 格式的 LLM（不是 CrewAI 格式）
    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL", "qwen-plus"),
        api_key=os.getenv("ALIYUN_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        temperature=0,
    )
    
    # RAGAS 也需要 Embedding 模型（用于 Answer Relevancy 指标）
    embeddings = OpenAIEmbeddings(
        model=os.getenv("EMBEDDING_MODEL", "text-embedding-v3"),
        api_key=os.getenv("ALIYUN_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
    )
    
    # 运行评测
    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=llm,
        embeddings=embeddings,
        raise_exceptions=False,  # 部分失败不影响其他指标
    )
    
    return {
        "faithfulness": round(float(result["faithfulness"]), 4),
        "answer_relevancy": round(float(result["answer_relevancy"]), 4),
        "context_precision": round(float(result["context_precision"]), 4),
        "overall": round(
            (result["faithfulness"] + result["answer_relevancy"] + result["context_precision"]) / 3,
            4
        )
    }


def load_test_dataset() -> list[dict]:
    """加载预置的评测数据集"""
    dataset_path = Path("evaluation/test_dataset.json")
    if not dataset_path.exists():
        # 返回示例数据
        return [
            {
                "question": "这段 Python 代码有什么安全漏洞？",
                "answer": "代码存在 SQL 注入风险，第 23 行使用了字符串拼接构造 SQL 查询。建议使用参数化查询。",
                "contexts": [
                    "函数 get_user() 在第 20-30 行，使用 f-string 拼接 SQL 查询",
                    "历史经验：SQL注入通常出现在用户输入直接拼接到 SQL 语句中的情况"
                ],
                "ground_truth": "存在 SQL 注入漏洞，需要使用参数化查询或 ORM 框架"
            }
        ]
    
    return json.loads(dataset_path.read_text(encoding="utf-8"))