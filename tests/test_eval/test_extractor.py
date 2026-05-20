from deepseek_code.eval.extractor import CodeExtractor

extractor = CodeExtractor()

FUNC_CODE = """\
def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True
"""


def test_extract_from_markdown_block() -> None:
    output = f"Here is the solution:\n\n```python\n{FUNC_CODE}```\n\nHope this helps!"
    result = extractor.extract(output, "is_prime")
    assert "def is_prime" in result
    assert "return True" in result


def test_extract_from_raw_text() -> None:
    output = f"The function is:\n{FUNC_CODE}\nThat should work."
    result = extractor.extract(output, "is_prime")
    assert "def is_prime" in result


def test_extract_loose_fallback() -> None:
    lines = ["Some explanation", f"    {FUNC_CODE.strip()}", "More text"]
    output = "\n".join(lines)
    result = extractor.extract(output, "is_prime")
    assert "def is_prime" in result


def test_extract_class_definition() -> None:
    code = """\
class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = {}
"""
    output = f"```python\n{code}```"
    result = extractor.extract(output, "LRUCache")
    assert "class LRUCache" in result
    assert "self.capacity" in result


def test_extract_not_found() -> None:
    result = extractor.extract("No code here, just text.", "missing_func")
    assert result == ""


def test_extract_wrong_function_ignored() -> None:
    output = "```python\ndef other_func(): pass\n```"
    result = extractor.extract(output, "target_func")
    assert result == ""


def test_extract_multiple_blocks_picks_correct() -> None:
    output = (
        "```python\ndef wrong(): pass\n```\n"
        "```python\ndef correct(x): return x + 1\n```"
    )
    result = extractor.extract(output, "correct")
    assert "def correct" in result
    assert "wrong" not in result
