import json

import pytest

from app.grading.parser import FormatError, SectionStreamParser, build_result
from tests.conftest import ESSAY, valid_answer

SECTIONS = (
    "### TASK_RESPONSE\nTR comment.\n"
    "### COHERENCE_COHESION\nCC comment.\n"
    "### LEXICAL_RESOURCE\nLR comment.\n"
    "### GRAMMATICAL_RANGE_ACCURACY\nGRA comment.\n"
)

GOOD_REWRITES = [{"original": "a", "improved": "b", "explanation": "c"}] * 3


def verdict(**overrides) -> dict:
    data = {
        "bands": {
            "task_response": 7,
            "coherence_cohesion": 7,
            "lexical_resource": 7,
            "grammatical_range_accuracy": 6,
        },
        "errors": [],
        "rewrites": GOOD_REWRITES,
    }
    data.update(overrides)
    return data


def run(text: str, chunk_size: int = 1) -> SectionStreamParser:
    p = SectionStreamParser()
    for i in range(0, len(text), chunk_size):
        p.feed(text[i : i + chunk_size])
    p.finish()
    return p


def test_streams_sections_even_when_markers_are_split_across_chunks():
    p = SectionStreamParser()
    deltas = []
    text = valid_answer()
    for ch in text:  # worst case: one character per chunk
        deltas += p.feed(ch)
    deltas += p.finish()
    streamed = {c for c, _ in deltas}
    assert streamed == {
        "task_response",
        "coherence_cohesion",
        "lexical_resource",
        "grammatical_range_accuracy",
    }
    assert "json" not in streamed  # raw JSON is never sent to the browser
    assert all("###" not in t for _, t in deltas)


def test_happy_path_computes_overall_with_official_rounding():
    result = build_result(run(SECTIONS + "### JSON\n" + json.dumps(verdict())), ESSAY)
    assert result.bands["grammatical_range_accuracy"] == 6
    assert str(result.overall) == "7.0"  # (7+7+7+6)/4 = 6.75 -> 7.0
    assert result.feedback["task_response"]["comment"] == "TR comment."


def test_accepts_heading_variants_preamble_and_code_fence():
    text = (
        "Sure! Here is the assessment.\n"
        "## Task Response\nTR.\n## Coherence and Cohesion\nCC.\n"
        "## Lexical Resource\nLR.\n## Grammatical Range and Accuracy\nGRA.\n"
        "## JSON\n```json\n" + json.dumps(verdict()) + "\n```\n"
    )
    result = build_result(run(text, chunk_size=7), ESSAY)
    assert result.feedback["coherence_cohesion"]["comment"] == "CC."


def test_missing_section_is_a_format_error():
    text = SECTIONS.replace("### LEXICAL_RESOURCE\nLR comment.\n", "")
    with pytest.raises(FormatError, match="lexical_resource"):
        build_result(run(text + "### JSON\n" + json.dumps(verdict())), ESSAY)


@pytest.mark.parametrize(
    "bad_json",
    [
        "not json at all",
        '{"bands": {"task_response": 7}',  # truncated
        json.dumps(
            verdict(
                bands={
                    "task_response": 6.5,
                    "coherence_cohesion": 6,
                    "lexical_resource": 6,
                    "grammatical_range_accuracy": 6,
                }
            )
        ),
        json.dumps(
            verdict(
                bands={
                    "task_response": 10,
                    "coherence_cohesion": 6,
                    "lexical_resource": 6,
                    "grammatical_range_accuracy": 6,
                }
            )
        ),
        json.dumps(
            verdict(
                bands={
                    "task_response": "high",
                    "coherence_cohesion": 6,
                    "lexical_resource": 6,
                    "grammatical_range_accuracy": 6,
                }
            )
        ),
        json.dumps(verdict(rewrites=GOOD_REWRITES[:2])),  # fewer than 3 rewrites
    ],
)
def test_invalid_model_json_is_rejected(bad_json):
    with pytest.raises(FormatError):
        build_result(run(SECTIONS + "### JSON\n" + bad_json), ESSAY)


def test_more_than_five_rewrites_are_trimmed():
    text = SECTIONS + "### JSON\n" + json.dumps(verdict(rewrites=GOOD_REWRITES * 3))
    assert len(build_result(run(text), ESSAY).rewrites) == 5


def test_invented_quotes_are_dropped():
    errors = [
        {
            "criterion": "lexical_resource",
            "quote": "the cost of higher education  has risen",
            "issue": "real quote, extra spaces",
            "correction": None,
        },
        {
            "criterion": "lexical_resource",
            "quote": "this sentence is not in the essay",
            "issue": "invented",
            "correction": None,
        },
    ]
    text = SECTIONS + "### JSON\n" + json.dumps(verdict(errors=errors))
    result = build_result(run(text), ESSAY)
    assert result.dropped_quotes == 1
    assert len(result.feedback["lexical_resource"]["errors"]) == 1
