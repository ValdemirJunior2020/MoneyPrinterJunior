from app.services.query import sanitize_search_query


def test_query_is_short_and_clean():
    raw = '“Abraham left Ur\nand traveled toward Canaan!!!” ' + 'word ' * 30
    value = sanitize_search_query(raw)
    assert '\n' not in value
    assert len(value.split()) <= 18
