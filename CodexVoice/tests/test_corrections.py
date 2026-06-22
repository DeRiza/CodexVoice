from codexvoice.transcriber.corrections import apply_default_phrase_corrections, apply_phrase_corrections
from codexvoice.transcriber.normalize import normalize_transcript


def test_default_phrase_corrections_fix_story_homophones() -> None:
    text = "口舌之针 碗块 手上的水字 加半 挑三减四 崩职"

    corrected, count = apply_default_phrase_corrections(text)

    assert corrected == "口舌之争 碗筷 手上的水渍 加班 挑三拣四 绷直"
    assert count == 6


def test_phrase_corrections_are_phrase_level_not_single_character() -> None:
    corrected, count = apply_default_phrase_corrections("他们一起去散步")

    assert corrected == "他们一起去散步"
    assert count == 0


def test_phrase_corrections_can_fix_contextual_umbrella_errors() -> None:
    text = "这笨蛋居然举着漏雨的散来接我，毕竟我连散都握不稳"

    corrected, count = apply_default_phrase_corrections(text)

    assert corrected == "这笨蛋居然举着漏雨的伞来接我，毕竟我连伞都握不稳"
    assert count == 2


def test_custom_phrase_corrections_skip_single_character_rules() -> None:
    corrected, count = apply_phrase_corrections("散步", {"散": "伞"})

    assert corrected == "散步"
    assert count == 0


def test_default_phrase_corrections_prefer_long_context_rules() -> None:
    text = "小狐猎刚把碗筷塞进洗碗机。傻狐狸甩了甩手上的水渍。"

    corrected, count = apply_default_phrase_corrections(text)

    assert corrected == "小狐狸刚把碗筷塞进洗碗机。小狐狸甩了甩手上的水渍。"
    assert count == 2


def test_default_phrase_corrections_avoid_broad_character_rewrites() -> None:
    text = "傻笑的小狐狸在散步，水字旁这个字没有被乱改。"

    corrected, count = apply_default_phrase_corrections(text)

    assert corrected == text
    assert count == 0


def test_default_phrase_corrections_fix_long_context_residuals() -> None:
    text = "厨房门口难道。你总说会记得熟悉我的陶瓷杯，他的耳朵大辣着。漏水的散来揭我，拿笔得上你那位前任。"

    corrected, count = apply_default_phrase_corrections(text)

    assert corrected == "厨房门口，难道你总说会记得洗我的陶瓷杯，他的耳朵耷拉着。漏雨的伞来接我，哪比得上你那位前任。"
    assert count == 5


def test_normalize_applies_phrase_corrections_after_punctuation() -> None:
    text = "小狐狸甩了甩手上的水字,每天加半到九点回来还要做家务怎么还挑三减四啊"

    assert normalize_transcript(text, "zh") == "小狐狸甩了甩手上的水渍，每天加班到九点回来还要做家务怎么还挑三拣四啊。"


def test_normalize_applies_conservative_de_di_correction() -> None:
    text = "于是便眼眶发红的摔门进了卧室"

    assert normalize_transcript(text, "zh") == "于是便眼眶发红地摔门进了卧室。"
