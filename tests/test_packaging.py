# -*- coding: utf-8 -*-
"""打包元数据测试：校验 pyproject 的声明与实际代码是否自洽。

这里守的是一个容易悄悄失真的承诺：`requires-python` 说支持 3.9，
但若代码里混进 3.10+ 才有的语法，用户装上了却跑不起来。
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"


def _pyproject_text() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


class TestRequiresPython:
    def test_declares_requires_python(self):
        assert "requires-python" in _pyproject_text()

    def test_running_interpreter_satisfies_declaration(self):
        """当前解释器必须满足 pyproject 里声明的最低版本。"""
        text = _pyproject_text()
        m = re.search(r'requires-python\s*=\s*">=\s*([\d.]+)"', text)
        assert m, "requires-python 格式无法解析"
        floor = tuple(int(x) for x in m.group(1).split("."))
        assert sys.version_info[: len(floor)] >= floor, (
            f"当前 Python {sys.version.split()[0]} 低于声明的 >= {m.group(1)}"
        )


class TestNoTooNewSyntax:
    """源码不得出现比声明版本更新的语法。

    用 AST 而非正则：正则会把 docstring 里的 `fmt: txt | json` 之类当成标注。
    """

    @staticmethod
    def _sources():
        return sorted((ROOT / "dabao_ocr").rglob("*.py"))

    def test_no_pep604_union_in_annotations(self):
        """`x: int | None` 在 3.9 运行时求值会 TypeError。"""
        import ast

        bad = []
        for p in self._sources():
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            for node in ast.walk(tree):
                anns = []
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    anns = [a.annotation for a in node.args.args + node.args.kwonlyargs]
                    anns += [node.returns]
                elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
                    anns = [node.annotation]
                for a in anns:
                    if isinstance(a, ast.BinOp) and isinstance(a.op, ast.BitOr):
                        bad.append(f"{p.relative_to(ROOT)}:{a.lineno}")
        assert not bad, f"发现 PEP 604 联合类型标注（需 3.10+）：{bad[:5]}"

    def test_no_match_statement(self):
        """`match` 是 3.10 的软关键字，只能从 token 流判断。

        形如 `match <expr>:` 且行尾是冒号的，就是 `match` 语句；
        普通变量 `match = 1` / `match.group()` 不会以冒号结尾。
        """
        import io
        import tokenize

        bad = []
        for p in self._sources():
            src = p.read_text(encoding="utf-8")
            toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
            for i, tok in enumerate(toks):
                if tok.type != tokenize.NAME or tok.string != "match":
                    continue
                # 取同一逻辑行后续 token，直到 NEWLINE
                rest = []
                for nxt in toks[i + 1:]:
                    if nxt.type in (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER):
                        break
                    if nxt.type not in (tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT):
                        rest.append(nxt)
                if rest and rest[-1].type == tokenize.OP and rest[-1].string == ":":
                    bad.append(f"{p.relative_to(ROOT)}:{tok.start[0]}")
        assert not bad, f"发现 match 语句（需 3.10+）：{bad[:5]}"


class TestLicenseMetadata:
    def test_uses_pep639_expression(self):
        """许可证应为 PEP 639 的字符串表达式，而非旧的表格式。"""
        text = _pyproject_text()
        assert re.search(r'^license\s*=\s*"[^"]+"', text, re.M), "license 应为字符串表达式"

    def test_no_license_classifier_conflict(self):
        """PEP 639 禁止 license 表达式与 License:: classifier 并存。"""
        assert "License ::" not in _pyproject_text()

    def test_license_file_declared_and_exists(self):
        text = _pyproject_text()
        assert re.search(r"license-files\s*=", text)
        for name in re.findall(r'"([^"]+)"', text.split("license-files")[1].split("\n")[0]):
            assert (ROOT / name).exists(), f"声明了但文件不存在：{name}"


class TestPackageShape:
    def test_typed_marker_present(self):
        assert (ROOT / "dabao_ocr" / "py.typed").exists()

    def test_entry_point_declared(self):
        assert 'dabao-ocr = "dabao_ocr.cli:main"' in _pyproject_text()
