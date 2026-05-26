def hello(name: str = "Codex") -> str:
    """返回问候语"""
    return f"Hello,ds code {name}!"


def print_well_wishes() -> None:
    """打印祝福语"""
    print("身体健康万事如意")


if __name__ == "__main__":
    print(hello())
    print(hello("DeepSeek"))
    print_well_wishes()
