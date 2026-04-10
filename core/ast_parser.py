# core/ast_parser.py
"""
基于 Tree-sitter 的多语言代码 AST 解析器。
将原始代码文件转为结构化元数据，供 Agent 高效理解代码结构。

知识点：
- Tree-sitter 是增量语法树解析库，支持 40+ 种编程语言
- AST（抽象语法树）是编译器前端的核心数据结构，比正则表达式更精准
- 圈复杂度（Cyclomatic Complexity）：衡量代码复杂性的指标，值越高越难维护
"""

import json
from dataclasses import dataclass, field
from typing import Optional
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
from tree_sitter import Language, Parser


# ========= 数据类定义（Pydantic 的轻量替代）=========

@dataclass
class FunctionInfo:
    name: str
    start_line: int
    end_line: int
    params: list[str]
    has_docstring: bool
    complexity: int  # 圈复杂度估算（if/for/while/and/or 等分支数 +1）


@dataclass
class ClassInfo:
    name: str
    start_line: int
    methods: list[str]
    inherits: list[str]


@dataclass
class CodeStructure:
    language: str
    total_lines: int
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    max_complexity: int = 0
    avg_complexity: float = 0.0
    todo_count: int = 0
    comment_ratio: float = 0.0  # 注释行占总行数的比例
    
    def to_summary_text(self) -> str:
        """
        将结构化数据转为紧凑的文本摘要，供 LLM 消化。
        这是节省 Token 的关键：把 500 行代码的关键信息压缩到 50 行。
        """
        lines = [
            f"## 代码结构摘要（{self.language}，共 {self.total_lines} 行）",
            f"- 导入模块：{', '.join(self.imports[:15])}{'...' if len(self.imports) > 15 else ''}",
            f"- 圈复杂度：最高={self.max_complexity}，平均={self.avg_complexity:.1f}",
            f"- 注释率：{self.comment_ratio:.1%}，TODO 数量：{self.todo_count}",
            "",
        ]
        
        if self.classes:
            lines.append("### 类定义：")
            for cls in self.classes:
                lines.append(f"  - `{cls.name}`（继承自：{cls.inherits or ['无']}，方法数：{len(cls.methods)}）")
        
        if self.functions:
            lines.append("\n### 函数列表：")
            for fn in self.functions:
                docstr_flag = "✅" if fn.has_docstring else "❌"
                lines.append(
                    f"  - `{fn.name}()`  行{fn.start_line}-{fn.end_line}  "
                    f"参数:{fn.params}  复杂度:{fn.complexity}  文档:{docstr_flag}"
                )
        
        return '\n'.join(lines)


# ========= 解析器主类 =========

class CodeParser:
    
    def __init__(self):
        # 初始化各语言的 Tree-sitter 解析器
        # Language() 需要传入对应语言的 .so 库（由 tree-sitter-xxx 包提供）
        self._parsers = {}
        self._init_parsers()
    
    def _init_parsers(self):
        """懒加载语言解析器，只初始化安装了的语言包"""
        try:
            py_lang = Language(tspython.language())
            self._parsers["python"] = Parser(py_lang)
        except Exception:
            pass
        
        try:
            js_lang = Language(tsjavascript.language())
            self._parsers["javascript"] = Parser(js_lang)
            self._parsers["typescript"] = Parser(js_lang)  # JS 解析器兼容 TS
        except Exception:
            pass
    
    def parse(self, code: str, language: str) -> CodeStructure:
        """
        主入口：解析代码字符串，返回 CodeStructure 对象。
        
        对于未安装 Tree-sitter 语言包的情况，回退到基于正则的轻量解析。
        """
        lines = code.split('\n')
        total_lines = len(lines)
        
        if language in self._parsers:
            return self._parse_with_treesitter(code, language, lines, total_lines)
        else:
            return self._parse_with_regex(code, language, lines, total_lines)
    
    def _parse_with_treesitter(self, code: str, language: str, 
                                 lines: list, total_lines: int) -> CodeStructure:
        """使用 Tree-sitter 精确解析（推荐路径）"""
        parser = self._parsers[language]
        tree = parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        
        structure = CodeStructure(language=language, total_lines=total_lines)
        
        # 统计注释行和 TODO
        comment_lines = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('*'):
                comment_lines += 1
            if 'TODO' in line or 'FIXME' in line or 'HACK' in line:
                structure.todo_count += 1
        structure.comment_ratio = comment_lines / max(total_lines, 1)
        
        # 遍历 AST，提取函数、类、导入信息
        self._traverse(root, code, lines, structure, language)
        
        # 计算平均复杂度
        if structure.functions:
            total_complexity = sum(f.complexity for f in structure.functions)
            structure.max_complexity = max(f.complexity for f in structure.functions)
            structure.avg_complexity = total_complexity / len(structure.functions)
        
        return structure
    
    def _traverse(self, node, code: str, lines: list, 
                  structure: CodeStructure, language: str):
        """递归遍历 AST 节点，提取感兴趣的结构"""
        
        if language == "python":
            if node.type == "function_definition":
                fn_info = self._extract_python_function(node, code)
                if fn_info:
                    structure.functions.append(fn_info)
            
            elif node.type == "class_definition":
                cls_info = self._extract_python_class(node, code)
                if cls_info:
                    structure.classes.append(cls_info)
            
            elif node.type in ("import_statement", "import_from_statement"):
                import_text = code[node.start_byte:node.end_byte].split('\n')[0]
                structure.imports.append(import_text.strip())
        
        # 递归处理子节点（跳过叶节点）
        for child in node.children:
            self._traverse(child, code, lines, structure, language)
    
    def _extract_python_function(self, node, code: str) -> Optional[FunctionInfo]:
        """从 function_definition AST 节点提取函数信息"""
        try:
            # 获取函数名（name 子节点）
            name_node = next((c for c in node.children if c.type == "identifier"), None)
            if not name_node:
                return None
            fn_name = code[name_node.start_byte:name_node.end_byte]
            
            # 获取参数列表（parameters 子节点）
            params_node = next((c for c in node.children if c.type == "parameters"), None)
            params = []
            if params_node:
                for param in params_node.children:
                    if param.type == "identifier":
                        param_name = code[param.start_byte:param.end_byte]
                        if param_name != "self":  # 忽略 self
                            params.append(param_name)
            
            # 判断是否有 docstring（函数体第一条语句是字符串字面量）
            body_node = next((c for c in node.children if c.type == "block"), None)
            has_docstring = False
            if body_node and body_node.children:
                first_stmt = body_node.children[0]
                if first_stmt.type == "expression_statement":
                    first_expr = first_stmt.children[0] if first_stmt.children else None
                    if first_expr and first_expr.type in ("string", "concatenated_string"):
                        has_docstring = True
            
            # 估算圈复杂度（计数分支关键词）
            fn_code = code[node.start_byte:node.end_byte]
            complexity = 1  # 基础复杂度
            BRANCH_KEYWORDS = ["if ", "elif ", "for ", "while ", "except ", " and ", " or "]
            for kw in BRANCH_KEYWORDS:
                complexity += fn_code.count(kw)
            
            return FunctionInfo(
                name=fn_name,
                start_line=node.start_point[0] + 1,  # Tree-sitter 行号从0开始
                end_line=node.end_point[0] + 1,
                params=params,
                has_docstring=has_docstring,
                complexity=complexity,
            )
        except Exception:
            return None
    
    def _extract_python_class(self, node, code: str) -> Optional[ClassInfo]:
        """从 class_definition AST 节点提取类信息"""
        try:
            name_node = next((c for c in node.children if c.type == "identifier"), None)
            if not name_node:
                return None
            
            cls_name = code[name_node.start_byte:name_node.end_byte]
            
            # 提取继承关系
            inherits = []
            arg_list = next((c for c in node.children if c.type == "argument_list"), None)
            if arg_list:
                for arg in arg_list.children:
                    if arg.type == "identifier":
                        inherits.append(code[arg.start_byte:arg.end_byte])
            
            # 提取方法列表
            methods = []
            body_node = next((c for c in node.children if c.type == "block"), None)
            if body_node:
                for stmt in body_node.children:
                    if stmt.type == "function_definition":
                        method_name_node = next((c for c in stmt.children if c.type == "identifier"), None)
                        if method_name_node:
                            methods.append(code[method_name_node.start_byte:method_name_node.end_byte])
            
            return ClassInfo(
                name=cls_name,
                start_line=node.start_point[0] + 1,
                methods=methods,
                inherits=inherits,
            )
        except Exception:
            return None
    
    def _parse_with_regex(self, code: str, language: str, 
                           lines: list, total_lines: int) -> CodeStructure:
        """
        回退方案：用正则表达式做轻量解析（当 Tree-sitter 不支持该语言时）。
        精度低于 Tree-sitter，但覆盖更多语言。
        """
        import re
        structure = CodeStructure(language=language, total_lines=total_lines)
        
        # 统计 TODO
        for line in lines:
            if 'TODO' in line or 'FIXME' in line:
                structure.todo_count += 1
        
        # 提取 Python import（正则方式）
        if language == "python":
            for line in lines:
                if line.strip().startswith(("import ", "from ")):
                    structure.imports.append(line.strip())
        
        # 粗略统计注释率
        comment_count = sum(1 for l in lines if l.strip().startswith(("#", "//", "/*", "*")))
        structure.comment_ratio = comment_count / max(total_lines, 1)
        
        return structure


# 全局单例，避免反复初始化（Tree-sitter 初始化有一定开销）
_parser_instance = None

def get_code_parser() -> CodeParser:
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = CodeParser()
    return _parser_instance