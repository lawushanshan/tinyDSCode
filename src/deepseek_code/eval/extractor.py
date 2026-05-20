from __future__ import annotations

import re
from typing import Optional


_FENCED_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)```",
    re.DOTALL,
)


class CodeExtractor:
    def extract(self, agent_output: str, entry_point: str) -> str:
        # Strategy 1: markdown code blocks
        blocks = _FENCED_BLOCK_RE.findall(agent_output)
        for block in blocks:
            func = self._find_definition_in_text(block, entry_point)
            if func:
                return self._add_imports_and_dependencies(func, block, entry_point)

        # Strategy 2: search entire output
        func = self._find_definition_in_text(agent_output, entry_point)
        if func:
            return self._add_imports_and_dependencies(func, agent_output, entry_point)

        # Strategy 3: loose line-by-line scan
        func = self._find_definition_loose(agent_output, entry_point)
        if func:
            return self._add_imports_and_dependencies(func, agent_output, entry_point)

        # Strategy 4: find similar function names
        func = self._find_similar_function(agent_output, entry_point)
        if func:
            return self._add_imports_and_dependencies(func, agent_output, entry_point)

        return ""

    def _find_similar_function(self, text: str, name: str) -> Optional[str]:
        blocks = _FENCED_BLOCK_RE.findall(text)
        for block in blocks:
            for keyword in ("def", "async def"):
                pattern = re.compile(
                    rf"(?:^|\n)({keyword}\s+\w+{re.escape(name)}\w*\s*[\(:].*?)(?=\n\S|\Z)",
                    re.DOTALL,
                )
                match = pattern.search(block)
                if match:
                    return self._clean(match.group(1))
        return None

    def _add_imports_and_dependencies(self, code: str, full_text: str, entry_point: str) -> str:
        imports = self._extract_imports(full_text)
        dependencies = self._extract_dependencies(code, full_text, entry_point)
        
        final_code = imports + "\n\n" + dependencies + "\n\n" + code
        return final_code.strip()

    def _extract_imports(self, text: str) -> str:
        import_lines = []
        lines = text.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                import_lines.append(stripped)
        
        if "List[" in text and "from typing import List" not in import_lines:
            import_lines.append("from typing import List")
        
        return "\n".join(import_lines) if import_lines else ""

    def _extract_dependencies(self, code: str, full_text: str, entry_point: str) -> str:
        dependencies = []
        
        class_names = re.findall(r'\b([A-Z][a-zA-Z0-9]*)\b', code)
        class_names = [name for name in class_names if name not in ["List", "Dict", "Set", "Tuple", "Optional", "Any", "int", "str", "bool", "float"]]
        
        for class_name in class_names:
            class_def = self._find_definition_in_text(full_text, class_name)
            if class_def and class_def not in dependencies:
                dependencies.append(class_def)
                continue
            
            blocks = _FENCED_BLOCK_RE.findall(full_text)
            for block in blocks:
                class_def = self._find_definition_in_text(block, class_name)
                if class_def and class_def not in dependencies:
                    dependencies.append(class_def)
                    break
        
        return "\n\n".join(dependencies) if dependencies else ""

    def _find_definition_in_text(self, text: str, name: str) -> Optional[str]:
        # Try def first, then class
        for keyword in ("def", "async def", "class"):
            pattern = re.compile(
                rf"(?:^|\n)({keyword}\s+{re.escape(name)}\s*[\(:].*?)(?=\n\S|\Z)",
                re.DOTALL,
            )
            match = pattern.search(text)
            if match:
                return self._clean(match.group(1))
        return None

    def _find_definition_loose(self, text: str, name: str) -> Optional[str]:
        lines = text.splitlines()
        start_idx = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if any(
                stripped.startswith(f"{kw} {name}")
                for kw in ("def", "async def", "class")
            ):
                start_idx = i
                break
        if start_idx is None:
            return None
        func_lines = [lines[start_idx]]
        for line in lines[start_idx + 1:]:
            if line.strip() == "":
                func_lines.append(line)
                continue
            if line[0] not in (" ", "\t"):
                break
            func_lines.append(line)
        return "\n".join(func_lines)

    @staticmethod
    def _clean(code: str) -> str:
        return "\n".join(code.rstrip().splitlines())
