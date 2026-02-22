from app.parsers.pdf_parser import PdfParser
from app.parsers.docx_parser import DocxParser
from app.parsers.xlsx_parser import XlsxParser
from app.parsers.pptx_parser import PptxParser
from app.parsers.image_parser import ImageParser

PARSERS = [PdfParser(), DocxParser(), XlsxParser(), PptxParser(), ImageParser()]


def get_parser(file_path: str):
    for parser in PARSERS:
        if parser.can_handle(file_path):
            return parser
    raise ValueError(f"No parser available for file: {file_path}")
