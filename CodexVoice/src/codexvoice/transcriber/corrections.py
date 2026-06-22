"""Conservative phrase-level transcript corrections.

Rules should be long enough to encode context. Avoid global single-character
rewrites and broad grammar guesses; those belong in a future opt-in layer.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PhraseCorrection:
    wrong: str
    correct: str
    note: str = ""


DEFAULT_PHRASE_CORRECTIONS: tuple[PhraseCorrection, ...] = (
    PhraseCorrection("厨房门口难道。你总说", "厨房门口，难道你总说", "Repair punctuation split in story dialogue."),
    PhraseCorrection("小狐猎刚把碗筷塞进洗碗机", "小狐狸刚把碗筷塞进洗碗机", "Story character name with context."),
    PhraseCorrection("傻狐狸甩了甩手上的水渍", "小狐狸甩了甩手上的水渍", "Story character name with action context."),
    PhraseCorrection("会记得熟悉我的陶瓷杯", "会记得洗我的陶瓷杯", "Contextual homophone around ceramic cup."),
    PhraseCorrection("他的耳朵大辣着", "他的耳朵耷拉着", "Contextual ear posture."),
    PhraseCorrection("漏水的散来揭我", "漏雨的伞来接我", "Contextual umbrella phrase."),
    PhraseCorrection("拿笔得上你那位", "哪比得上你那位", "Contextual comparison phrase."),
    PhraseCorrection("手上的水字", "手上的水渍", "Contextual water stain phrase."),
    PhraseCorrection("刻出第三道裂痕", "磕出第三道裂痕", "Cup crack context."),
    PhraseCorrection("眼眶发红的摔门", "眼眶发红地摔门", "Conservative de/di correction with full phrase."),
    PhraseCorrection("端端正正的摆", "端端正正地摆", "Conservative de/di correction with full phrase."),
    PhraseCorrection("安安静静抱着", "安安静静地抱着", "Conservative de/di correction with full phrase."),
    PhraseCorrection("轻轻的拿", "轻轻地拿", "Conservative de/di correction with full phrase."),
    PhraseCorrection("连散都握不稳", "连伞都握不稳", "Umbrella context."),
    PhraseCorrection("漏雨的散", "漏雨的伞", "Umbrella context."),
    PhraseCorrection("口舌之针", "口舌之争", "Fixed idiom."),
    PhraseCorrection("挑三减四", "挑三拣四", "Fixed idiom."),
    PhraseCorrection("小坦子", "小毯子", "Story object."),
    PhraseCorrection("空唠唠", "空落落", "Fixed emotional phrase."),
    PhraseCorrection("难难倒", "难道", "Observed stutter-like recognition artifact."),
    PhraseCorrection("搭拉", "耷拉", "Ear posture."),
    PhraseCorrection("大辣着", "耷拉着", "Ear posture variant."),
    PhraseCorrection("反问到", "反问道", "Speech attribution."),
    PhraseCorrection("全梭", "蜷缩", "Body posture."),
    PhraseCorrection("碗块", "碗筷", "Kitchen object."),
    PhraseCorrection("加半", "加班", "Work overtime phrase."),
    PhraseCorrection("崩职", "绷直", "Ear posture."),
)


def apply_default_phrase_corrections(text: str) -> tuple[str, int]:
    return apply_phrase_corrections(text, DEFAULT_PHRASE_CORRECTIONS)


def apply_phrase_corrections(
    text: str,
    rules: Mapping[str, str] | Iterable[PhraseCorrection],
) -> tuple[str, int]:
    corrected = text
    replacements = 0
    for rule in _ordered_rules(rules):
        if len(rule.wrong) < 2:
            continue
        count = corrected.count(rule.wrong)
        if count == 0:
            continue
        corrected = corrected.replace(rule.wrong, rule.correct)
        replacements += count
    return corrected, replacements


def _ordered_rules(rules: Mapping[str, str] | Iterable[PhraseCorrection]) -> list[PhraseCorrection]:
    if isinstance(rules, Mapping):
        normalized = [PhraseCorrection(wrong, right) for wrong, right in rules.items()]
    else:
        normalized = list(rules)
    return sorted(normalized, key=lambda rule: len(rule.wrong), reverse=True)
