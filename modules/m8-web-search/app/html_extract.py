from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Optional


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: Optional[str] = None
        self._in_title = False
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title = text if self.title is None else f"{self.title} {text}"
        else:
            self.parts.append(text)


def extract_text(html: str, max_chars: int) -> tuple[Optional[str], str]:
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(parser.parts)
    text = re.sub(r"\s+", " ", text).strip()
    return parser.title, text[:max_chars]
