import pytest

from ml.models.reliability import (
    LOW_CONFIDENCE,
    TRACKING,
    UNPROVEN,
    UNRELIABLE,
    VALIDATED,
    VALID_TONES,
    assess_reliability,
)


@pytest.mark.parametrize(
    "n,mape",
    [(0, None), (1, 738.0), (3, 12.0), (4, 40.0)],
)
def test_few_or_no_scores_are_unproven(n, mape):
    result = assess_reliability(n, mape)
    assert result["tier"] == UNPROVEN
    assert result["tone"] == "neutral"


def test_single_huge_error_is_high_error():
    result = assess_reliability(30, 738.0)
    assert result["tier"] == UNRELIABLE
    assert result["tone"] == "crit"
    assert result["label"] == "High error"


def test_barrage_range_100_to_740_is_unreliable():
    for mape in (101.0, 141.0, 738.0):
        assert assess_reliability(20, mape)["tier"] == UNRELIABLE


def test_moderate_mape_is_low_accuracy():
    result = assess_reliability(91, 55.0)
    assert result["tier"] == LOW_CONFIDENCE
    assert result["tone"] == "warn"


def test_exact_100_mape_is_still_low_accuracy():
    assert assess_reliability(20, 100.0)["tier"] == LOW_CONFIDENCE


def test_good_mape_with_few_scores_is_early_tracking():
    result = assess_reliability(6, 20.0)
    assert result["tier"] == TRACKING
    assert result["tone"] == "info"


def test_validated_needs_track_record_and_good_mape():
    result = assess_reliability(90, 25.0)
    assert result["tier"] == VALIDATED
    assert result["tone"] == "ok"
    assert assess_reliability(14, 40.0)["tier"] == VALIDATED
    assert assess_reliability(13, 40.0)["tier"] == TRACKING


def test_every_tone_maps_to_a_badge_tone():
    for n, mape in [(0, None), (30, 150.0), (30, 55.0), (6, 20.0), (90, 25.0)]:
        assert assess_reliability(n, mape)["tone"] in VALID_TONES


def test_labels_always_carry_text():
    for n, mape in [(0, None), (30, 150.0), (30, 55.0), (6, 20.0), (90, 25.0)]:
        assert assess_reliability(n, mape)["label"]
