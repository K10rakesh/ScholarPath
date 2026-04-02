# backend/tests/test_parser.py
# Run with: pytest backend/tests/test_parser.py -v

from backend.utils.citation_patterns import (
    find_citation_markers,
    extract_citation_sentences,
    parse_bibliography,
    split_body_and_references
)


def test_single_marker():
    assert find_citation_markers("RNNs perform well [1].") == ["[1]"]


def test_range_expansion():
    assert find_citation_markers("See [1-3] for details.") == ["[1]", "[2]", "[3]"]


def test_comma_expansion():
    assert find_citation_markers("Prior work [1,2] shows this.") == ["[1]", "[2]"]


def test_no_markers():
    assert find_citation_markers("This is a sentence.") == []


def test_citation_sentences_filters_correctly():
    body = "Transformers outperform RNNs [1]. The sky is blue. See also [2] and [3]."
    results = extract_citation_sentences(body)
    # Only the 2 sentences with markers should be returned
    assert len(results) == 2
    assert all(r["citations"] for r in results)


def test_bibliography_parsing():
    ref_text = """
References
[1] Vaswani et al. Attention Is All You Need. NeurIPS 2017.
[2] Gehring et al. Convolutional Sequence to Sequence Learning. 2017.
[3] Bahdanau et al. Neural Machine Translation. 2015.
"""
    refs = parse_bibliography(ref_text)
    assert len(refs) == 3
    ref_ids = [r.ref_id for r in refs]
    assert "[1]" in ref_ids
    assert "[3]" in ref_ids
    # No duplicate ref_ids
    assert len(ref_ids) == len(set(ref_ids))


def test_body_ref_split():
    text = "Some body text here.\n\nReferences\n\n[1] Some paper."
    body, refs = split_body_and_references(text)
    assert "[1]" in refs
    assert "[1]" not in body
def test_citation_integrity_no_violations():
    """
    Ensures every citation marker inside claims[] exists in references[].
    This is the M2 handoff contract — if this fails, M2 breaks silently.
    """
    from backend.schemas import ParsedPaper, Section, Reference, Claim

    paper = ParsedPaper(
        doc_id="test01",
        file_name="test.pdf",
        title="Test",
        authors=[],
        full_text="",
        sections=[Section(section_id="s1", heading="Intro", text="some text")],
        references=[
            Reference(ref_id="[1]", raw_text="Vaswani et al. 2017"),
            Reference(ref_id="[2]", raw_text="Gehring et al. 2017"),
        ],
        claims=[
            Claim(
                claim_id="c1",
                claim_text="Transformers outperform RNNs [1].",
                citations=["[1]"],
                section="Intro",
                section_id="s1",
                priority="high",
                claim_type="result",
                sentence_index=0
            )
        ],
        stats={}
    )

    violations = paper.validate_citation_integrity()
    assert violations == [], f"Citation integrity violations found: {violations}"


def test_citation_integrity_catches_bad_ref():
    """
    A claim citing [99] with no matching reference should produce a violation.
    """
    from backend.schemas import ParsedPaper, Section, Reference, Claim

    paper = ParsedPaper(
        doc_id="test02",
        file_name="test.pdf",
        title="Test",
        authors=[],
        full_text="",
        sections=[Section(section_id="s1", heading="Intro", text="some text")],
        references=[
            Reference(ref_id="[1]", raw_text="Vaswani et al. 2017"),
        ],
        claims=[
            Claim(
                claim_id="c1",
                claim_text="Transformers are fast [99].",
                citations=["[99]"],   # [99] doesn't exist in references
                section="Intro",
                section_id="s1",
                priority="high",
                claim_type="result",
                sentence_index=0
            )
        ],
        stats={}
    )

    violations = paper.validate_citation_integrity()
    assert len(violations) == 1
    assert "[99]" in violations[0]