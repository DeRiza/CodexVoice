"""Low-risk transcript normalization."""

from __future__ import annotations

from functools import lru_cache
import logging
import re

from codexvoice.transcriber.corrections import apply_default_phrase_corrections

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_CJK_CHAR = r"\u3400-\u9fff"
_TERMINAL_PUNCTUATION = "。！？!?…"
_COMMON_T2S = str.maketrans(
    {
        "裡": "里",
        "裏": "里",
        "靜": "静",
        "誰": "谁",
        "沒": "没",
        "開": "开",
        "說": "说",
        "話": "话",
        "風": "风",
        "腳": "脚",
        "與": "与",
        "這": "这",
        "個": "个",
        "麼": "么",
        "為": "为",
        "會": "会",
        "過": "过",
        "點": "点",
        "條": "条",
        "輕": "轻",
        "讓": "让",
        "遠": "远",
        "離": "离",
        "誰": "谁",
    }
)


def normalize_transcript(text: str, language: str | None = "zh") -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if language and language.startswith("zh"):
        cleaned = _to_simplified(cleaned)
        cleaned = _normalize_chinese_punctuation(cleaned)
        cleaned = _remove_chinese_internal_spaces(cleaned)
        cleaned = _append_terminal_punctuation_for_long_sentence(cleaned)
        cleaned, correction_count = apply_default_phrase_corrections(cleaned)
        if correction_count:
            logger.info("Phrase corrections applied: count=%d", correction_count)
    return cleaned


def _to_simplified(text: str) -> str:
    try:
        converter = _opencc_t2s()
    except Exception:
        return text.translate(_COMMON_T2S)
    return converter.convert(text)


@lru_cache(maxsize=1)
def _opencc_t2s():
    from opencc import OpenCC  # type: ignore

    return OpenCC("t2s")


def _normalize_chinese_punctuation(text: str) -> str:
    if not _CJK_RE.search(text):
        return text
    replacements = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}
    for source, target in replacements.items():
        text = re.sub(fr"(?<=[{_CJK_CHAR}])\{source}|\{source}(?=[{_CJK_CHAR}])", target, text)
    text = re.sub(r"\.{3,}", "…", text)
    text = re.sub(fr"(?<=[{_CJK_CHAR}])\.(?!\d)", "。", text)
    return text


def _remove_chinese_internal_spaces(text: str) -> str:
    return re.sub(fr"(?<=[{_CJK_CHAR}])\s+(?=[{_CJK_CHAR}])", "", text)


def _append_terminal_punctuation_for_long_sentence(text: str) -> str:
    if not text or text.endswith(tuple(_TERMINAL_PUNCTUATION)):
        return text
    if not _CJK_RE.search(text):
        return text
    # Avoid turning short commands or names like “你好” into full sentences.
    if len(text) < 12:
        return text
    return f"{text}。"
