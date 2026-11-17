"""Providers that never call a real AI service.

- FakeProvider: scripted answers, used by the test suite.
- DemoProvider: LLM_PROVIDER=fake. Builds a deterministic, well-formed answer from the
  essay itself so the whole app can be tried without an API key. Its scores are NOT
  an assessment.
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Sequence

from app.schemas import count_words


def _chunks(text: str, size: int = 24) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, answers: Sequence[str | Exception]) -> None:
        self._answers = list(answers)
        self.calls: list[tuple[str, str]] = []

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        self.calls.append((system, prompt))
        if not self._answers:
            raise AssertionError("FakeProvider ran out of scripted answers")
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        for piece in _chunks(answer):
            yield piece


def _sentences(essay: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", essay.strip())
    return [p.strip() for p in parts if len(p.split()) >= 5]


def build_demo_answer(essay: str, language: str = "en") -> str:
    """A protocol-correct answer built from the essay. Also used by tests."""
    sentences = _sentences(essay) or [essay.strip()[:200]]
    words = count_words(essay)
    paragraphs = len([p for p in essay.split("\n") if p.strip()])
    tr = 6 if words >= 250 else 5
    cc = 6 if paragraphs >= 4 else 5
    vi = language == "vi"

    def say(en: str, vi_text: str) -> str:
        return vi_text if vi else en

    comments = {
        "TASK_RESPONSE": say(
            f"(Demo) The essay has {words} words and addresses the question.",
            f"(Demo) Bài viết có {words} từ và có trả lời câu hỏi.",
        ),
        "COHERENCE_COHESION": say(
            f"(Demo) The essay has {paragraphs} paragraph(s).",
            f"(Demo) Bài viết có {paragraphs} đoạn.",
        ),
        "LEXICAL_RESOURCE": say(
            "(Demo) Vocabulary is adequate for the task.",
            "(Demo) Từ vựng đủ dùng cho đề bài.",
        ),
        "GRAMMATICAL_RANGE_ACCURACY": say(
            "(Demo) A mix of simple and complex sentences.",
            "(Demo) Có kết hợp câu đơn và câu phức.",
        ),
    }
    first = sentences[0]
    picks = (sentences * 3)[:3]
    verdict = {
        "bands": {
            "task_response": tr,
            "coherence_cohesion": cc,
            "lexical_resource": 6,
            "grammatical_range_accuracy": 6,
        },
        "errors": [
            {
                "criterion": "grammatical_range_accuracy",
                "quote": first,
                "issue": say("(Demo) Example quoted sentence.", "(Demo) Câu được trích làm ví dụ."),
                "correction": None,
            }
        ],
        "rewrites": [
            {
                "original": s,
                "improved": s,
                "explanation": say("(Demo) Placeholder rewrite.", "(Demo) Câu viết lại mẫu."),
            }
            for s in picks
        ],
    }
    body = "".join(f"### {name}\n{text}\n" for name, text in comments.items())
    return body + "### JSON\n" + json.dumps(verdict, ensure_ascii=False)


class DemoProvider:
    name = "fake"
    model = "demo (not a real assessment)"

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        essay = re.search(r"<essay>\n(.*)\n</essay>", prompt, re.S)
        language = "vi" if "in Vietnamese" in prompt else "en"
        answer = build_demo_answer(essay.group(1) if essay else "", language)
        for piece in _chunks(answer):
            await asyncio.sleep(0.02)  # make the streaming visible in the demo
            yield piece
