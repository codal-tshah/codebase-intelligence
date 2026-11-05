from __future__ import annotations

from pathlib import Path


# Language-aware separators inspired by LangChain RecursiveCharacterTextSplitter.fromLanguage()
_LANGUAGE_SPLITS: dict[str, list[str]] = {
    ".py": ["\nclass ", "\ndef ", "\nasync def ", "\n\n", "\n", " "],
    ".js": ["\nfunction ", "\nconst ", "\nclass ", "\n\n", "\n", " "],
    ".jsx": ["\nfunction ", "\nconst ", "\nclass ", "\n\n", "\n", " "],
    ".ts": ["\nfunction ", "\nconst ", "\nclass ", "\ninterface ", "\n\n", "\n", " "],
    ".tsx": ["\nfunction ", "\nconst ", "\nclass ", "\ninterface ", "\n\n", "\n", " "],
    ".go": ["\nfunc ", "\ntype ", "\n\n", "\n", " "],
    ".rs": ["\nfn ", "\nimpl ", "\nstruct ", "\n\n", "\n", " "],
    ".java": ["\nclass ", "\ninterface ", "\npublic ", "\n\n", "\n", " "],
}

_DEFAULT_SPLITS = ["\n\n", "\n", " ", ""]


def split_text(text: str, suffix: str, *, chunk_size: int = 1200, chunk_overlap: int = 120) -> list[str]:
    separators = _LANGUAGE_SPLITS.get(suffix, _DEFAULT_SPLITS)
    return _recursive_split(text, separators, chunk_size, chunk_overlap)


def _recursive_split(
    text: str,
    separators: list[str],
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    if not separators:
        return _hard_split(text, chunk_size, chunk_overlap)

    sep = separators[0]
    rest = separators[1:]
    parts = text.split(sep) if sep else list(text)
    chunks: list[str] = []
    current = ""
    for i, part in enumerate(parts):
        piece = (sep + part) if i > 0 and sep else part
        if len(current) + len(piece) <= chunk_size:
            current += piece
        else:
            if current.strip():
                if len(current) > chunk_size:
                    chunks.extend(_recursive_split(current, rest, chunk_size, chunk_overlap))
                else:
                    chunks.append(current)
            current = piece
    if current.strip():
        if len(current) > chunk_size:
            chunks.extend(_recursive_split(current, rest, chunk_size, chunk_overlap))
        else:
            chunks.append(current)
    return _merge_overlap(chunks, chunk_overlap)


def _hard_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


def _merge_overlap(chunks: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(chunks) < 2:
        return chunks
    merged = [chunks[0]]
    for chunk in chunks[1:]:
        prev = merged[-1]
        tail = prev[-overlap:] if len(prev) > overlap else prev
        merged.append(tail + chunk)
    return merged


def language_from_path(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    mapping = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".rb": "Ruby",
        ".php": "PHP",
    }
    return mapping.get(ext)
