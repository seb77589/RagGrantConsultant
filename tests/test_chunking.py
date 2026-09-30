from gcr.chunking import chunk_text, count_tokens, split_sentences


def test_blank_input_yields_nothing():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_is_one_chunk():
    text = "Ethylene is the chemical industry's primary building block."
    assert chunk_text(text) == [text]


def test_abbreviations_do_not_split_sentences():
    # EU funding text is dense with these; splitting here would strand the
    # article number away from the rule it introduces.
    text = "See Art. 3 of the Regulation. It applies from 2024."
    assert len(split_sentences(text)) == 2


def test_chunks_respect_max_tokens():
    para = " ".join(f"Sentence number {i} about eligibility criteria." for i in range(400))
    for chunk in chunk_text(para):
        assert count_tokens(chunk) <= 512


def test_long_single_sentence_is_force_split():
    # No sentence boundary to use, so the splitter must fall back to words
    # rather than emit one oversized chunk.
    sentence = "word " * 3000
    chunks = chunk_text(sentence)
    assert len(chunks) > 1
    for chunk in chunks:
        assert count_tokens(chunk) <= 512


def test_short_tail_is_merged_into_predecessor():
    # A ~450-token document is the common CORDIS objective shape: packing to a
    # 400-token target would emit a full chunk plus a ~50-token fragment, so the
    # merge must keep it whole. Stays under the 512-token ceiling.
    text = " ".join(f"Clause {i} sets out the funding rate." for i in range(45))
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert count_tokens(chunks[0]) <= 512


def test_tail_is_not_merged_when_it_would_breach_the_ceiling():
    # Once the tail is large enough that merging would exceed max_tokens, the
    # split must stand.
    text = " ".join(f"Clause {i} sets out the funding rate." for i in range(50))
    chunks = chunk_text(text)
    assert len(chunks) == 2
    for chunk in chunks:
        assert count_tokens(chunk) <= 512


def test_overlap_repeats_boundary_content():
    # Overlap carries whole trailing sentences back, so chunk 1 restarts part
    # way inside chunk 0 rather than at its final sentence. The property that
    # matters is that the boundary content is present in both.
    text = " ".join(f"Point {i} concerns regional aid intensity." for i in range(200))
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    first_of_next = split_sentences(chunks[1])[0]
    assert first_of_next in chunks[0]


def test_overlap_stays_within_its_budget():
    text = " ".join(f"Point {i} concerns regional aid intensity." for i in range(200))
    chunks = chunk_text(text)
    carried = [s for s in split_sentences(chunks[1]) if s in chunks[0]]
    # OVERLAP_TOKENS is 50 and each sentence here is ~10 tokens.
    assert 0 < count_tokens(" ".join(carried)) <= 60
