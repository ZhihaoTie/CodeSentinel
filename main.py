# main.py
"""
Streamlit 前端：一键启动的 Web 界面。
命令：streamlit run main.py
"""

import streamlit as st
import tempfile
import os
from pathlib import Path
from review_pipeline import run_code_review
from core.qdrant_memory import get_review_memory

# ===== 页面配置 =====
st.set_page_config(
    page_title="CodeSentinel",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===== 侧边栏：系统状态 =====
with st.sidebar:
    st.title("🛡️ CodeSentinel")
    st.caption("智能代码审查系统 v1.0")
    st.divider()
    
    # 显示 Qdrant 记忆库状态
    try:
        memory = get_review_memory()
        stats = memory.get_stats()
        st.metric("📚 历史经验库", f"{stats['total_records']} 条记录")
    except Exception as e:
        st.error(f"Qdrant 连接失败: {e}")
    
    st.divider()
    st.markdown("""
    **技术栈**
    - 🤖 CrewAI 多 Agent
    - 🔌 MCP 标准协议
    - 🗃️ Qdrant 向量记忆
    - 📊 Langfuse 追踪
    - 🌳 Tree-sitter 解析
    """)

# ===== 主界面 =====
st.title("🛡️ CodeSentinel — 智能代码审查系统")
st.caption("5个专家 Agent 协作审查 | 历史经验召回 | 全链路追踪")

# Tab 布局
tab1, tab2, tab3 = st.tabs(["📁 文件审查", "📊 评测报告", "🔍 历史记录"])

# ===== Tab 1：文件审查 =====
with tab1:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("上传代码文件")
        
        input_method = st.radio(
            "输入方式",
            ["📤 上传文件", "📂 输入本地路径", "✏️ 直接粘贴代码"],
            horizontal=True,
        )
        
        code_content = None
        file_name = "untitled.py"
        
        if input_method == "📤 上传文件":
            uploaded_file = st.file_uploader(
                "选择代码文件",
                type=["py", "js", "ts", "java", "go", "cpp", "c"],
            )
            if uploaded_file:
                code_content = uploaded_file.read().decode("utf-8", errors="replace")
                file_name = uploaded_file.name
                st.success(f"✅ 已上传：{file_name}（{len(code_content.split(chr(10)))} 行）")
        
        elif input_method == "📂 输入本地路径":
            local_path = st.text_input(
                "本地文件路径",
                placeholder="例：C:/Users/xxx/project/main.py",
            )
            if local_path and Path(local_path).exists():
                code_content = Path(local_path).read_text(encoding="utf-8", errors="replace")
                file_name = Path(local_path).name
                st.success(f"✅ 已加载：{file_name}")
            elif local_path:
                st.error("文件不存在，请检查路径")
        
        elif input_method == "✏️ 直接粘贴代码":
            lang = st.selectbox("语言", ["python", "javascript", "java", "go"])
            code_content = st.text_area(
                "粘贴代码",
                height=300,
                placeholder="在此粘贴你的代码...",
            )
            file_name = f"snippet.{lang[:2]}"
        
        # 代码预览
        if code_content:
            with st.expander("👁️ 代码预览", expanded=False):
                ext = Path(file_name).suffix.lstrip(".")
                st.code(code_content[:2000], language=ext or "python")
    
    with col2:
        st.subheader("审查配置")
        
        review_mode = st.selectbox(
            "审查模式",
            ["🔍 全面审查（5个Agent）", "⚡ 快速安全扫描", "🏗️ 仅架构分析"],
        )
        
        show_structure = st.checkbox("显示代码结构分析", value=True)
        show_memory = st.checkbox("显示召回的历史经验", value=True)
        
        st.divider()
        
        # 开始审查按钮
        if st.button("🚀 开始审查", type="primary", disabled=(code_content is None)):
            
            with st.spinner("⏳ 正在审查中，预计需要 1-3 分钟..."):
                
                # 如果是直接粘贴，先写临时文件
                if input_method == "✏️ 直接粘贴代码":
                    with tempfile.NamedTemporaryFile(
                        mode='w', suffix=f'.{lang[:2]}',
                        delete=False, encoding='utf-8'
                    ) as f:
                        f.write(code_content)
                        temp_path = f.name
                    result = run_code_review(temp_path)
                    os.unlink(temp_path)
                elif input_method == "📤 上传文件":
                    with tempfile.NamedTemporaryFile(
                        mode='w', suffix=Path(file_name).suffix,
                        delete=False, encoding='utf-8'
                    ) as f:
                        f.write(code_content)
                        temp_path = f.name
                    result = run_code_review(temp_path)
                    os.unlink(temp_path)
                else:
                    result = run_code_review(local_path)
                
                # 存储结果到 session_state，保持页面刷新不丢失
                st.session_state["last_result"] = result
            
            st.success(f"✅ 审查完成！耗时 {result.get('duration_seconds', 0):.1f}s")
    
    # 显示审查结果
    if "last_result" in st.session_state:
        result = st.session_state["last_result"]
        
        if "error" in result:
            st.error(f"审查失败：{result['error']}")
        else:
            st.divider()
            
            # 指标行
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("⏱️ 审查耗时", f"{result['duration_seconds']}s")
            m2.metric("📚 历史经验召回", f"{result['memory_recalled']} 条")
            m3.metric("💾 新增经验存储", f"{result['memory_stored']} 条")
            m4.metric("🔑 会话 ID", result['session_id'])
            
            if show_structure:
                with st.expander("🌳 代码结构分析（Tree-sitter 解析结果）", expanded=False):
                    st.code(result['code_structure'], language="markdown")
            
            st.subheader("📋 审查报告")
            st.markdown(result['report_markdown'])
            
            # 下载报告
            st.download_button(
                "⬇️ 下载 Markdown 报告",
                data=result['report_markdown'],
                file_name=f"review_{result['session_id']}.md",
                mime="text/markdown",
            )

# ===== Tab 2：RAGAS 评测（后续章节实现）=====
with tab2:
    st.subheader("📊 RAGAS 质量评测")
    st.info("在第五章实现 RAGAS 评测后，此处会显示量化指标。")

# ===== Tab 3：历史审查记录 =====
with tab3:
    st.subheader("🔍 历史审查经验库")
    
    search_query = st.text_input("搜索历史经验（语义搜索）", placeholder="例：SQL注入 Python")
    
    if st.button("搜索") and search_query:
        memory = get_review_memory()
        results = memory.recall_similar_issues(search_query, top_k=10)
        
        if results:
            for r in results:
                with st.expander(f"[{r['issue_type']}] {r['issue_summary'][:60]}... (相似度: {r['similarity_score']})"):
                    st.write(f"**严重度**：{r['severity']}")
                    st.write(f"**语言**：{r['language']}")
                    st.write(f"**建议**：{r['suggestion']}")
        else:
            st.info("未找到相关历史记录")