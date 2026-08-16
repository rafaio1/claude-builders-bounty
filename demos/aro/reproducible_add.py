"""Demo própria da oferta «bug reproduzível». Sem dados de terceiros."""


def add(left: int, right: int) -> int:
    return left + right


if __name__ == "__main__":
    assert add(2, 3) == 5
    print("ok")
