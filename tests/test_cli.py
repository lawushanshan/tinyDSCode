import pytest
from deepseek_code.cli import parse_args


def test_parse_args_run() -> None:
    args = parse_args(["run", "修复 auth.ts"])
    assert args.command == "run"
    assert args.prompt == "修复 auth.ts"


def test_parse_args_repl() -> None:
    args = parse_args(["repl"])
    assert args.command == "repl"
