"""
文档分块器 — 将长文档按标题/段落切分为适合向量检索的小块。

分块策略：
1. 按 Markdown 二级标题（## ）切分为段落
2. 段落过长时按空行再细分
3. 每个 chunk 附带元数据（doc_name、chunk_index、heading）
"""

import re


def chunk_document(
    content: str,
    doc_name: str,
    max_chunk_size: int = 500,
) -> list[dict]:
    """将文档内容切分为 chunk 列表。

    Args:
        content: 文档全文（Markdown 格式）
        doc_name: 文档名称（用于元数据标记）
        max_chunk_size: 单个 chunk 的最大字符数

    Returns:
        [{"text": str, "doc_name": str, "chunk_index": int, "heading": str}, ...]
    """
    sections = _split_by_heading(content)
    chunks = []

    for heading, body in sections:
        if not body.strip():
            continue
        sub_chunks = _split_long_text(body.strip(), max_chunk_size)
        for text in sub_chunks:
            if not text.strip():
                continue
            chunks.append({
                "text": text.strip(),
                "doc_name": doc_name,
                "chunk_index": len(chunks),
                "heading": heading,
            })

    return chunks


def _split_by_heading(content: str) -> list[tuple[str, str]]:
    """按 Markdown 二级标题切分，返回 [(heading, body), ...]。

    没有标题的开头部分用 "(intro)" 作为 heading。
    """
    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(content))

    if not matches:
        return [("(全文)", content)]

    sections = []
    if matches[0].start() > 0:
        intro = content[:matches[0].start()]
        if intro.strip():
            sections.append(("(简介)", intro))

    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections.append((heading, content[start:end]))

    return sections


def _split_long_text(text: str, max_size: int) -> list[str]:
    """将过长的文本按空行切分为更小的块。"""
    if len(text) <= max_size:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    current = ""

    for para in paragraphs:
        if current and len(current) + len(para) + 2 > max_size:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        chunks.append(current)

    return chunks
