"""Radon（.rdn）文件格式解析器。"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, TextIO


class rdnParseError(ValueError):
    """当 rdn 文档不符合格式时抛出。"""

    def __init__(self, message: str, line_number: int | None = None) -> None:
        self.line_number = line_number
        detail = f"line {line_number}: {message}" if line_number else message
        super().__init__(detail)


_SECTION_RE = re.compile(r"^\[([A-Za-z_][A-Za-z0-9_]*)\]$")
_INTEGER_RE = re.compile(r"^[+-]?[0-9]+$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|"
    r"[0-9]+[eE][+-]?[0-9]+)$"
)


def _decode_string(token: str, line_number: int, kind: str) -> str:
    if len(token) < 2 or token[0] not in "\"'" or token[-1] != token[0]:
        raise rdnParseError(f"{kind} must be enclosed in single or double quotes", line_number)
    quote = token[0]
    escaped = False
    for index, character in enumerate(token[1:], 1):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == quote:
            if index != len(token) - 1:
                raise rdnParseError(f"invalid {kind} string", line_number)
            break
    try:
        value = ast.literal_eval(token)
    except (SyntaxError, ValueError) as exc:
        raise rdnParseError(f"invalid {kind} string", line_number) from exc
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        raise rdnParseError(f"invalid {kind} string", line_number)
    return value


def _find_separator(line: str) -> int:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
        elif character == "\\" and quote:
            escaped = True
        elif quote:
            if character == quote:
                quote = None
        elif character in "\"'":
            quote = character
        elif character == ":":
            return index
    return -1


def _parse_scalar(token: str, line_number: int) -> Any:
    if token.startswith(("'", '"')):
        return _decode_string(token, line_number, "value")
    if token in ("true", "false"):
        return token == "true"
    if _INTEGER_RE.fullmatch(token):
        return int(token)
    if _FLOAT_RE.fullmatch(token):
        return float(token)
    raise rdnParseError(
        "value must be a quoted string, integer, float, true, or false",
        line_number,
    )


def _parse_value(token: str, line_number: int) -> Any:
    """Parse a scalar or recursively nested parenthesized list."""
    token = token.strip()
    if not token.startswith("("):
        return _parse_scalar(token, line_number)

    index = 1

    def skip_whitespace() -> None:
        nonlocal index
        while index < len(token) and token[index].isspace():
            index += 1

    def parse_item() -> Any:
        nonlocal index
        skip_whitespace()
        if index >= len(token):
            raise rdnParseError("unterminated list", line_number)
        if token[index] == "(":
            return parse_list()

        start = index
        if token[index] in "\"'":
            quote = token[index]
            index += 1
            escaped = False
            while index < len(token):
                character = token[index]
                index += 1
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    return _parse_scalar(token[start:index], line_number)
            raise rdnParseError("unterminated string in list", line_number)

        while index < len(token) and not token[index].isspace() and token[index] not in ",)":
            index += 1
        return _parse_scalar(token[start:index].strip(), line_number)

    def parse_list() -> list[Any]:
        nonlocal index
        if index >= len(token) or token[index] != "(":
            raise rdnParseError("invalid list", line_number)
        index += 1
        values: list[Any] = []
        skip_whitespace()
        if index < len(token) and token[index] == ")":
            index += 1
            return values
        while True:
            values.append(parse_item())
            skip_whitespace()
            if index >= len(token):
                raise rdnParseError("unterminated list", line_number)
            if token[index] == ")":
                index += 1
                return values
            if token[index] != ",":
                raise rdnParseError("list elements must be separated by commas", line_number)
            index += 1
            skip_whitespace()
            if index < len(token) and token[index] == ")":
                raise rdnParseError("trailing comma is not allowed in a list", line_number)

    index = 0
    result = parse_list()
    if token[index:].strip():
        raise rdnParseError("unexpected content after list", line_number)
    return result


def parse(text: str) -> dict[str, Any]:
    """将 rdn 文本解析为节名称或键到值的映射。"""
    sections: dict[str, dict[str, Any]] = {}
    root: dict[str, Any] = {}
    current: dict[str, Any] = root
    has_section = False

    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if raw_line.startswith(";"):
            continue
        if line.startswith(";"):
            raise rdnParseError("comments must start at the beginning of the line", line_number)

        section_match = _SECTION_RE.fullmatch(line)
        if section_match:
            name = section_match.group(1)
            if name in sections:
                raise rdnParseError(f"duplicate section {name!r}", line_number)
            if root:
                raise rdnParseError("section declarations must precede key/value pairs", line_number)
            has_section = True
            current = {}
            sections[name] = current
            continue

        if line.startswith("[") or line.endswith("]"):
            raise rdnParseError("invalid section declaration", line_number)

        separator = _find_separator(line)
        if separator < 0:
            raise rdnParseError("key/value pair must contain ':'", line_number)
        key_token = line[:separator].strip()
        value_token = line[separator + 1 :].strip()
        key = _decode_string(key_token, line_number, "key")
        if not key:
            raise rdnParseError("key cannot be empty", line_number)
        if key in current:
            raise rdnParseError(f"duplicate key {key!r}", line_number)
        if not value_token:
            raise rdnParseError("value cannot be empty", line_number)
        current[key] = _parse_value(value_token, line_number)

    return sections if has_section else root


def load(
    source: str | Path | TextIO,
    *,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    """读取并解析 rdn 文件路径或已打开的文本文件对象。"""
    if isinstance(source, (str, Path)):
        text = Path(source).read_text(encoding=encoding)
    else:
        text = source.read()
        if not isinstance(text, str):
            raise TypeError("rdn input must be a text file opened in read mode")
    return parse(text)


class rdnParser:
    """面向对象的封装，供偏好使用解析器实例的调用方使用。"""

    def parse(self, text: str) -> dict[str, Any]:
        return parse(text)

    def load(
        self,
        source: str | Path | TextIO,
        *,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        return load(source, encoding=encoding)


__all__ = ["rdnParseError", "rdnParser", "load", "parse"]
