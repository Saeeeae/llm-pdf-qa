from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedPage:
    page_num: int
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    pages: list[ParsedPage]
    raw_text: str
    total_pages: int = 0
    metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    SUPPORTED_EXTENSIONS: list[str] = []

    @abstractmethod
    def parse(self, file_path: str) -> ParseResult:
        ...

    @classmethod
    def can_handle(cls, file_path: str) -> bool:
        return any(file_path.lower().endswith(ext) for ext in cls.SUPPORTED_EXTENSIONS)
