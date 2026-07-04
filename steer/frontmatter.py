"""
SKILL.md frontmatter parsing and emission.

Implements the YAML subset that appears in real skill frontmatter
(scalars, quoted strings, inline and block lists, one level of nested
maps such as ``metadata``, and block scalars ``|`` and ``>``) without a
YAML dependency. Steer stays zero-dependency on purpose.

The parser is deliberately lenient where the spec's client guidance is
lenient (unquoted colons in descriptions are a common authoring
mistake), and reports structural problems instead of raising.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

DELIMITER = "---"


def split_document(content: str) -> Tuple[Optional[str], str]:
    """Split a SKILL.md document into (frontmatter_text, body).

    Returns (None, content) when no frontmatter block is present.
    """
    content = content.lstrip("﻿")  # editors add BOMs invisibly
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != DELIMITER:
        return None, content
    for i in range(1, len(lines)):
        if lines[i].strip() == DELIMITER:
            return "".join(lines[1:i]), "".join(lines[i + 1:])
    return None, content  # Unterminated block: treat the whole file as body


def _parse_scalar(raw: str) -> Any:
    """Parse a scalar value: quoted strings, booleans, inline lists."""
    value = raw.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in _split_inline_list(inner)]
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return _unescape_double_quoted(value[1:-1])
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1].replace("''", "'")
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


_DQ_ESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t"}


def _unescape_double_quoted(text: str) -> str:
    """Undo the escapes a YAML double-quoted scalar can carry (the subset
    emit() writes plus \\n/\\t); unknown escapes pass through literally."""
    out: List[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            mapped = _DQ_ESCAPES.get(text[i + 1])
            if mapped is not None:
                out.append(mapped)
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_inline_list(inner: str) -> List[str]:
    """Split 'a, b, "c, d"' on commas outside quotes."""
    parts = []
    current = []
    quote = None
    for ch in inner:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch == ",":
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def parse(text: str) -> Tuple[Dict[str, Any], List[str]]:
    """Parse frontmatter text into a dict.

    Handles arbitrarily nested maps and lists (including lists of maps,
    as used by Claude Code's `hooks` frontmatter). Returns (data,
    problems); problems describe lines the parser could not make sense
    of, and parsing continues past them.
    """
    problems: List[str] = []
    lines = text.splitlines()
    data, _ = _parse_map(lines, 0, 0, problems)
    return data, problems


def _read_block_scalar(lines: List[str], start: int, style: str,
                       parent_indent: int = 0) -> Tuple[str, int]:
    """Read a ``|`` or ``>`` block scalar starting at `start`.

    Content belongs to the block while it is indented deeper than the
    key that opened it (`parent_indent`); a sibling or dedented key ends
    the block.
    """
    collected = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line.strip() and _indent_of(line) <= parent_indent:
            break
        collected.append(line)
        i += 1
    # Strip the common indentation
    indents = [_indent_of(ln) for ln in collected if ln.strip()]
    base = min(indents) if indents else 0
    body_lines = [ln[base:] if len(ln) >= base else "" for ln in collected]
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    if style.startswith("|"):
        text = "\n".join(body_lines)
    else:  # folded: newlines become spaces, blank lines become newlines
        paragraphs: List[str] = []
        current: List[str] = []
        for ln in body_lines:
            if ln.strip():
                current.append(ln.strip())
            elif current:
                paragraphs.append(" ".join(current))
                current = []
        if current:
            paragraphs.append(" ".join(current))
        text = "\n".join(paragraphs)
    if not style.endswith("-"):
        text += "\n" if text else ""
    return text, i


def _skip_blank(lines: List[str], i: int) -> int:
    while i < len(lines) and (not lines[i].strip()
                              or lines[i].strip().startswith("#")):
        i += 1
    return i


def _parse_map(lines: List[str], i: int, indent: int,
               problems: List[str]) -> Tuple[Dict[str, Any], int]:
    """Parse `key: value` entries at exactly `indent` until dedent."""
    mapping: Dict[str, Any] = {}
    while True:
        i = _skip_blank(lines, i)
        if i >= len(lines) or _indent_of(lines[i]) < indent:
            return mapping, i
        line = lines[i]
        if _indent_of(line) > indent:
            problems.append(
                f"line {i + 1}: unexpected indentation: {line.strip()!r}")
            i += 1
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            return mapping, i  # caller decides; a list at map level is odd
        if ":" not in stripped:
            problems.append(
                f"line {i + 1}: expected 'key: value': {stripped!r}")
            i += 1
            continue
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest.startswith("|") or rest.startswith(">"):
            mapping[key], i = _read_block_scalar(lines, i + 1, style=rest,
                                                 parent_indent=indent)
            continue
        if rest:
            mapping[key] = _parse_scalar(rest)
            i += 1
            continue
        mapping[key], i = _parse_value_block(lines, i + 1, indent, problems)
    return mapping, i


def _parse_value_block(lines: List[str], i: int, parent_indent: int,
                       problems: List[str]) -> Tuple[Any, int]:
    """Parse what follows a `key:` with no inline value: a deeper-indented
    list or map, or nothing (empty string)."""
    i = _skip_blank(lines, i)
    if i >= len(lines) or _indent_of(lines[i]) <= parent_indent:
        return "", i
    child_indent = _indent_of(lines[i])
    if lines[i].lstrip().startswith("- "):
        return _parse_list(lines, i, child_indent, problems)
    return _parse_map(lines, i, child_indent, problems)


def _parse_list(lines: List[str], i: int, indent: int,
                problems: List[str]) -> Tuple[List[Any], int]:
    """Parse `- item` entries at exactly `indent` until dedent.

    A list item may be a scalar, or open a map (`- key: value` with
    continuation lines indented past the dash), or open a nested block.
    """
    items: List[Any] = []
    while True:
        i = _skip_blank(lines, i)
        if i >= len(lines) or _indent_of(lines[i]) < indent:
            return items, i
        line = lines[i]
        if _indent_of(line) > indent or not line.strip().startswith("-"):
            problems.append(
                f"line {i + 1}: expected list item: {line.strip()!r}")
            i += 1
            continue
        content = line.strip()[1:].lstrip()  # text after the dash
        item_indent = indent + 2             # canonical continuation indent
        if not content:
            value, i = _parse_value_block(lines, i + 1, indent, problems)
            items.append(value)
            continue
        if ":" in content and not content.startswith(("'", '"', "[")):
            # `- key: value` opens a map item; rewrite the dash as spaces so
            # the map parser sees a normally indented first entry.
            rewritten = lines[:i] + [" " * item_indent + content] + lines[i + 1:]
            value, i = _parse_map(rewritten, i, item_indent, problems)
            items.append(value)
            continue
        items.append(_parse_scalar(content))
        i += 1
    return items, i


_NEEDS_QUOTING = re.compile(r'(^[\s\-?:,\[\]{}#&*!|>\'"%@`])|(:\s)|(\s#)|(\s$)|(^$)')


def _emit_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if _NEEDS_QUOTING.search(text) or text in ("true", "false", "null"):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _emit_value(key: str, value: Any, indent: int, lines: List[str]) -> None:
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            return
        lines.append(f"{pad}{key}:")
        for k, v in value.items():
            _emit_value(k, v, indent + 2, lines)
    elif isinstance(value, list):
        if not value:
            return
        lines.append(f"{pad}{key}:")
        item_pad = " " * (indent + 2)
        for item in value:
            if isinstance(item, dict) and item:
                # Emit every key at the continuation indent, then fold the
                # first line onto the dash: `- key: ...`
                sub: List[str] = []
                for k, v in item.items():
                    _emit_value(k, v, indent + 4, sub)
                sub[0] = f"{item_pad}- {sub[0].lstrip()}"
                lines.extend(sub)
            else:
                lines.append(f"{item_pad}- {_emit_scalar(item)}")
    elif isinstance(value, str) and "\n" in value:
        lines.append(f"{pad}{key}: |")
        for part in value.rstrip("\n").split("\n"):
            lines.append(f"{pad}  {part}")
    else:
        lines.append(f"{pad}{key}: {_emit_scalar(value)}")


def emit(data: Dict[str, Any]) -> str:
    """Emit a frontmatter block (including the --- delimiters)."""
    lines = [DELIMITER]
    for key, value in data.items():
        if value is None:
            continue
        _emit_value(key, value, 0, lines)
    lines.append(DELIMITER)
    return "\n".join(lines) + "\n"
