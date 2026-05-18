from nara_server.file_extractor import extract_text_from_url
from app.pipeline.section_extractor import compress_document


async def extract_and_compress(file_url: str, filename: str) -> str:
    raw = await extract_text_from_url(file_url, filename)
    return compress_document(raw)
