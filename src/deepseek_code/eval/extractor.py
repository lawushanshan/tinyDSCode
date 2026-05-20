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
                return func

        # Strategy 2: search entire output
        func = self._find_definition_in_text(agent_output, entry_point)
        if func:
            return func

        # Strategy 3: loose line-by-line scan
        func = self._find_definition_loose(agent_output, entry_point)
        if func:
            return func

        return ""

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
