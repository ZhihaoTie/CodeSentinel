# core/qdrant_memory.py
"""
基于 Qdrant 的代码审查历史经验记忆库。

核心功能：
1. 存储：将本次审查结论（问题描述 + 修复建议）向量化后写入 Qdrant
2. 召回：新代码提交时，根据代码摘要语义搜索历史相似问题
3. 过滤：按编程语言、严重程度等字段精确过滤后再做向量搜索

知识点：
- Qdrant 本地文件模式（QdrantClient(path="./qdrant_data")）
- Payload Filter：先按结构化字段筛选，再做向量相似度搜索
- upsert：insert + update 合并操作（有则更新，无则插入）
"""

import os
import uuid
import json
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchRequest,
)
from dotenv import load_dotenv
from core.llm import get_embedding_model

load_dotenv()

# Qdrant 向量维度（text-embedding-v3 输出 1024 维向量）
VECTOR_DIM = 1024


class ReviewMemory:
    """
    代码审查历史经验库。
    每条记录包含：
    - vector: 问题描述的语义向量（用于相似度搜索）
    - payload: 结构化元数据（用于精确过滤）
      {
        "issue_type": "security",      # 问题类型（security/performance/style/architecture/docs）
        "severity": "high",            # 严重程度（high/medium/low）
        "language": "python",          # 编程语言
        "issue_summary": "SQL注入风险", # 问题简述（索引字段）
        "code_snippet": "...",         # 问题代码片段
        "suggestion": "...",           # 修复建议
        "created_at": "2025-04-01",    # 创建时间
      }
    """
    
    def __init__(self):
        qdrant_path = os.getenv("QDRANT_PATH", "./qdrant_data")
        self.collection_name = os.getenv("QDRANT_COLLECTION", "code_review_memory")
        
        # 本地文件模式：数据持久化到磁盘，重启后数据不丢失
        # 注意：这里不用 Docker，不用服务器，就是本地文件夹
        self.client = QdrantClient(path=qdrant_path)
        self.embed = get_embedding_model()
        
        # 初始化 Collection（如果不存在则创建）
        self._ensure_collection()
    
    def _ensure_collection(self):
        """确保 Collection 存在，不存在则创建"""
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=VECTOR_DIM,
                    distance=Distance.COSINE,  # 余弦相似度，NLP 任务的标准选择
                ),
            )
            print(f"✅ 创建 Qdrant Collection: {self.collection_name}")
    
    def store_review_findings(self, findings: list[dict], code_summary: str) -> int:
        """
        将本次审查发现的问题存入记忆库。
        
        findings: 每个元素是一个问题字典，包含 issue_type/severity/issue_summary/code_snippet/suggestion
        code_summary: 被审查代码的结构摘要（用于向量化）
        返回：成功存储的条数
        """
        if not findings:
            return 0
        
        # 构造向量化文本（issue_summary + suggestion 合并，语义更丰富）
        texts_to_embed = [
            f"{f.get('issue_summary', '')} {f.get('suggestion', '')}"
            for f in findings
        ]
        
        # 批量向量化（减少 API 调用次数）
        vectors = self.embed(texts_to_embed)
        
        # 构造 Qdrant Points
        points = []
        for i, (finding, vector) in enumerate(zip(findings, vectors)):
            point = PointStruct(
                id=str(uuid.uuid4()),  # 随机 UUID 作为主键
                vector=vector,
                payload={
                    "issue_type": finding.get("issue_type", "unknown"),
                    "severity": finding.get("severity", "medium"),
                    "language": finding.get("language", "unknown"),
                    "issue_summary": finding.get("issue_summary", ""),
                    "code_snippet": finding.get("code_snippet", "")[:500],  # 限制长度
                    "suggestion": finding.get("suggestion", ""),
                    "created_at": finding.get("created_at", ""),
                }
            )
            points.append(point)
        
        # upsert 批量写入
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        
        return len(points)
    
    def recall_similar_issues(
        self,
        query_text: str,
        language: Optional[str] = None,
        issue_type: Optional[str] = None,
        top_k: int = 5,
    ) -> list[dict]:
        """
        根据当前代码特征，召回历史相似问题。
        
        query_text: 当前代码摘要或问题描述（用于语义搜索）
        language: 可选，按语言过滤（"python"/"javascript" 等）
        issue_type: 可选，按问题类型过滤（"security"/"performance" 等）
        top_k: 返回最相似的 N 条记录
        """
        # 向量化查询文本
        query_vector = self.embed([query_text])[0]
        
        # 构建 Payload Filter（可选）
        # 关键知识点：Qdrant 的 Filter 先过滤再检索，比先检索再过滤效率高
        filter_conditions = []
        if language:
            filter_conditions.append(
                FieldCondition(key="language", match=MatchValue(value=language))
            )
        if issue_type:
            filter_conditions.append(
                FieldCondition(key="issue_type", match=MatchValue(value=issue_type))
            )
        
        query_filter = None
        if filter_conditions:
            query_filter = Filter(must=filter_conditions)  # must = AND 条件
        
        # 执行向量相似度搜索
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=0.65,  # 相似度阈值，低于 0.65 的结果丢弃（避免召回无关内容）
        )
        
        # 格式化返回结果
        recalled = []
        for hit in results:
            recalled.append({
                "similarity_score": round(hit.score, 3),
                **hit.payload,  # 展开 payload 的所有字段
            })
        
        return recalled
    
    def get_stats(self) -> dict:
        """获取记忆库统计信息（用于 Streamlit 展示）"""
        info = self.client.get_collection(self.collection_name)
        return {
            "total_records": info.points_count,
            "collection_name": self.collection_name,
        }


# 全局单例
_memory_instance = None

def get_review_memory() -> ReviewMemory:
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ReviewMemory()
    return _memory_instance