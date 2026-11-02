"""A reader for skill frontmatter. The standard library has no YAML, and skills use a small subset:
plain and quoted scalars, block scalars (| and >), block and flow lists, and nested maps. Anything
outside that subset raises FrontmatterError naming the line, so one odd skill never stops a scan."""

import re

FENCE = "---"
KEY = re.compile(r"^([A-Za-z0-9_-]+):(?:\s+(.*))?$")
BLOCK_SCALAR = re.compile(r"^([|>])([-+]?)$")


class FrontmatterError(ValueError):
    pass


def parse(text):
    """Split a SKILL.md into (frontmatter, body). Frontmatter is None when the file has none."""
    lines = text.split("\n")
    if lines[0].rstrip() != FENCE:
        return None, text
    for end in range(1, len(lines)):
        if lines[end].rstrip() == FENCE:
            break
    else:
        raise FrontmatterError("frontmatter has no closing ---")
    block = [(number, line) for number, line in enumerate(lines[1:end], start=1)]
    return _Reader(block).read_map(indent=0), "\n".join(lines[end + 1:])


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _is_blank(line):
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


class _Reader:
    def __init__(self, lines):
        self.lines = lines
        self.at = 0

    def _peek(self):
        while self.at < len(self.lines) and _is_blank(self.lines[self.at][1]):
            self.at += 1
        return self.lines[self.at] if self.at < len(self.lines) else None

    def read_map(self, indent):
        result = {}
        while (next_line := self._peek()) is not None:
            number, line = next_line
            if _indent(line) < indent:
                break
            if _indent(line) > indent:
                raise FrontmatterError(f"line {number}: unexpected indentation")
            match = KEY.match(line.strip())
            if not match:
                raise FrontmatterError(f"line {number}: expected 'key: value'")
            self.at += 1
            key, raw = match.group(1), (match.group(2) or "").strip()
            result[key] = self._value(raw, indent, number)
        return result

    def _value(self, raw, indent, number):
        block = BLOCK_SCALAR.match(raw)
        if block:
            return self._block_scalar(block.group(1), block.group(2), indent)
        if raw and not raw.startswith("#"):
            return _scalar_or_flow(raw, number)
        child = self._peek()
        if child is None or _indent(child[1]) <= indent:
            return None
        child_indent = _indent(child[1])
        if child[1].strip().startswith("- "):
            return self._read_list(child_indent)
        return self.read_map(child_indent)

    def _read_list(self, indent):
        items = []
        while (next_line := self._peek()) is not None:
            number, line = next_line
            if _indent(line) != indent or not line.strip().startswith("- "):
                break
            self.at += 1
            items.append(_scalar_or_flow(line.strip()[2:].strip(), number))
        return items

    def _block_scalar(self, style, chomp, indent):
        taken = []
        while self.at < len(self.lines):
            line = self.lines[self.at][1]
            if line.strip() and _indent(line) <= indent:
                break
            taken.append(line)
            self.at += 1
        while taken and not taken[-1].strip():
            taken.pop()
        if not taken:
            return ""
        margin = min(_indent(line) for line in taken if line.strip())
        content = [line[margin:] for line in taken]
        text = "\n".join(content) if style == "|" else _fold(content)
        return text if chomp == "-" else text + "\n"


def _fold(lines):
    paragraphs, current = [], []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        else:
            paragraphs.append(" ".join(current))
            current = []
    paragraphs.append(" ".join(current))
    return "\n".join(paragraphs)


def _scalar_or_flow(raw, number):
    if raw.startswith("["):
        if not raw.rstrip().endswith("]"):
            raise FrontmatterError(f"line {number}: unclosed [")
        return [_scalar(part, number) for part in _split_flow(raw.rstrip()[1:-1], number) if part]
    return _scalar(raw, number)


def _split_flow(inner, number):
    parts, current, quote = [], "", None
    for char in inner:
        if quote:
            current += char
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current += char
        elif char == ",":
            parts.append(current.strip())
            current = ""
        else:
            current += char
    if quote:
        raise FrontmatterError(f"line {number}: unterminated quote")
    parts.append(current.strip())
    return parts


def _scalar(raw, number):
    if raw.startswith('"'):
        end = _closing_double_quote(raw)
        if end is None:
            raise FrontmatterError(f"line {number}: unterminated quote")
        return re.sub(r'\\(["\\/nt])', lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), raw[1:end])
    if raw.startswith("'"):
        match = re.match(r"^'((?:[^']|'')*)'", raw)
        if not match:
            raise FrontmatterError(f"line {number}: unterminated quote")
        return match.group(1).replace("''", "'")
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip() or None


def _closing_double_quote(raw):
    escaped = False
    for at, char in enumerate(raw[1:], start=1):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return at
    return None
