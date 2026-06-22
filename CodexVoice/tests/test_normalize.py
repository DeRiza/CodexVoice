from codexvoice.transcriber.normalize import normalize_transcript


def test_normalize_converts_traditional_chinese_to_simplified() -> None:
    text = "屋子裡安安靜靜的,誰都沒有先開口"

    assert normalize_transcript(text, "zh") == "屋子里安安静静的，谁都没有先开口。"


def test_normalize_keeps_short_chinese_phrase_without_forced_period() -> None:
    assert normalize_transcript("你好", "zh") == "你好"


def test_normalize_does_not_duplicate_terminal_punctuation() -> None:
    assert normalize_transcript("天色慢慢暗下来。", "zh") == "天色慢慢暗下来。"


def test_normalize_english_spacing_is_preserved() -> None:
    assert normalize_transcript("hello,   world.", "en") == "hello, world."


def test_normalize_preserves_english_spaces_in_mixed_chinese_context() -> None:
    text = "比如 prompt injection 和 over fitting 会改变语境"

    assert normalize_transcript(text, "zh") == "比如 prompt injection 和 over fitting 会改变语境。"


def test_normalize_removes_spaces_between_chinese_characters_only() -> None:
    text = "生活 的 意义 在于 life itself"

    assert normalize_transcript(text, "zh") == "生活的意义在于 life itself。"


def test_normalize_preserves_english_punctuation_inside_english_clause() -> None:
    text = "Life is not an absurd number of life, the meaning of life lives in life itself.生活的意义在于生活本身"

    assert normalize_transcript(text, "zh") == "Life is not an absurd number of life, the meaning of life lives in life itself.生活的意义在于生活本身。"
