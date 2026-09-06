from app.services.media.scoring import relevance_score


def test_relevant_historical_result_beats_unrelated_result():
    good = relevance_score('ancient Mesopotamia map Ur Canaan', 'Map of ancient Mesopotamia and Canaan', 'Historical map of Ur', 'wikimedia')
    bad = relevance_score('ancient Mesopotamia map Ur Canaan', 'Celebrity football trailer', 'sports gaming highlights', 'pexels')
    assert good > bad
