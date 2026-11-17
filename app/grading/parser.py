import json
import re
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import ValidationError

from app.grading.prompt import MARKERS
from app.schemas import CRITERIA, ModelVerdict
from app.scoring import overall_band

_MARKER_RE = re.compile(r"^#{2,4}\s*([A-Za-z_ &]+?)\s*#*$")


class FormatError(Exception):
    """The model's answer does not follow the protocol. Triggers one retry."""


def _marker_name(line: str) -> str | None:
    m = _MARKER_RE.match(line.strip())
    if not m:
        return None
    name = m.group(1).upper().replace("&", "AND").replace(" ", "_")
    name = name.replace("_AND_", "_")
    return MARKERS.get(name)


@dataclass
class SectionStreamParser:
    """Splits the streamed answer into sections while it is still arriving.

    `feed()` returns (section, text) deltas for the four feedback sections so the
    browser can show them immediately. The JSON section is only buffered.
    """

    sections: dict[str, str] = field(default_factory=dict)
    json_text: str = ""
    _current: str | None = None
    _pending: str = ""
    _at_line_start: bool = True

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        self._pending += chunk
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            self._handle(line + "\n", self._at_line_start, out)
            self._at_line_start = True
        # Emit a partial line early, unless it might still turn into a "###" marker.
        if self._pending:
            head = self._pending.lstrip()
            maybe_marker = self._at_line_start and (head == "" or head.startswith("#"))
            if not maybe_marker:
                self._handle(self._pending, False, out)
                self._pending = ""
                self._at_line_start = False
        return out

    def finish(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if self._pending:
            self._handle(self._pending, self._at_line_start, out)
            self._pending = ""
        return out

    def _handle(self, text: str, at_line_start: bool, out: list[tuple[str, str]]) -> None:
        if at_line_start and (section := _marker_name(text)):
            self._current = section
            if section != "json":
                self.sections.setdefault(section, "")
            return
        if self._current is None:
            return  # preamble before the first marker is ignored
        if self._current == "json":
            self.json_text += text
            return
        self.sections[self._current] += text
        out.append((self._current, text))


@dataclass
class GradingResult:
    bands: dict[str, int]
    overall: Decimal
    feedback: dict
    rewrites: list[dict]
    dropped_quotes: int


def _normalise(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def build_result(parser: SectionStreamParser, essay: str) -> GradingResult:
    for criterion in CRITERIA:
        if not parser.sections.get(criterion, "").strip():
            raise FormatError(f"Missing feedback section: {criterion}")

    raw = parser.json_text
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise FormatError("No JSON block found")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise FormatError(f"Invalid JSON: {exc.msg}") from exc
    try:
        verdict = ModelVerdict.model_validate(data)
    except ValidationError as exc:
        raise FormatError(f"JSON does not match the schema: {exc.error_count()} error(s)") from exc

    # Keep only quotes that really appear in the essay: the model must not invent mistakes.
    essay_norm = _normalise(essay)
    feedback: dict = {c: {"comment": parser.sections[c].strip(), "errors": []} for c in CRITERIA}
    dropped = 0
    for err in verdict.errors:
        if _normalise(err.quote) in essay_norm:
            feedback[err.criterion]["errors"].append(err.model_dump(exclude={"criterion"}))
        else:
            dropped += 1

    bands = verdict.bands.model_dump()
    return GradingResult(
        bands=bands,
        overall=overall_band(bands.values()),
        feedback=feedback,
        rewrites=[r.model_dump() for r in verdict.rewrites],
        dropped_quotes=dropped,
    )
