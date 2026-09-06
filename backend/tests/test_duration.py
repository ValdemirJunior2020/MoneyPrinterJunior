import pytest
from app.services.duration import duration_target, rebalance_scene_seconds


def test_duration_selector_contract_is_exactly_1_to_10():
    values = [duration_target(i).minutes for i in range(1, 11)]
    assert values == list(range(1, 11))
    with pytest.raises(ValueError):
        duration_target(0)
    with pytest.raises(ValueError):
        duration_target(11)


def test_scene_rebalance_matches_actual_audio_duration():
    durations = rebalance_scene_seconds([10, 20, 30], 123.456)
    assert len(durations) == 3
    assert sum(durations) == pytest.approx(123.456, abs=0.002)


def test_style_aware_word_targets():
    sermon = duration_target(5, "Sermon")
    documentary = duration_target(5, "Documentary")
    assert sermon.target_words == 625
    assert documentary.target_words == 750
    assert sermon.target_words < documentary.target_words
