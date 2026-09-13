"""Analysis-only Copilot CLI adapter and structured RCA model contracts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from shutil import which
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from .evidence import EvidencePackage
from .knowledge_base import KBPassage


class ModelRunnerError(RuntimeError):
    """Raised when a Model Runner is unavailable or returns invalid RCA output."""


@dataclass(frozen=True)
class Hypothesis:
    title: str
    supporting_evidence: tuple[str, ...]
    contradicting_evidence: tuple[str, ...]
    unknowns: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class RcaDraft:
    hypotheses: tuple[Hypothesis, ...]
    most_likely_explanation: str | None
    unknowns: tuple[str, ...]
    recommended_actions: tuple[str, ...]


@dataclass(frozen=True)
class Evaluation:
    result: str
    citation_gaps: tuple[str, ...]
    contradictions: tuple[str, ...]
    unknowns: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class ModelInvocation:
    model: str
    prompt: str
    raw_output: str


class ModelRunner(Protocol):
    def preflight(self) -> None: ...

    def run_analyst(
        self,
        evidence: EvidencePackage,
        passages: tuple[KBPassage, ...],
        product_version: str | None,
        kb_version_applicability: str,
    ) -> ModelInvocation: ...

    def run_evaluator(
        self,
        draft: RcaDraft,
        evidence: EvidencePackage,
        passages: tuple[KBPassage, ...],
        product_version: str | None,
        kb_version_applicability: str,
    ) -> ModelInvocation: ...


class CopilotCliRunner:
    """Runs two isolated, non-interactive Copilot CLI invocations."""

    def __init__(self, executable: str = "copilot", model: str | None = None) -> None:
        self._executable = executable
        self._model = model

    def preflight(self) -> None:
        if which(self._executable) is None:
            raise ModelRunnerError("Copilot CLI is unavailable. Install it, run `copilot login`, and retry.")
        result = self._run("Return exactly READY.")
        if result.strip() != "READY":
            raise ModelRunnerError("Copilot CLI preflight failed. Run `copilot login` and retry.")

    def run_analyst(self, evidence: EvidencePackage, passages: tuple[KBPassage, ...], product_version: str | None,
                    kb_version_applicability: str) -> ModelInvocation:
        prompt = _analyst_prompt(evidence, passages, product_version, kb_version_applicability)
        return ModelInvocation(self._model or "copilot-cli-default", prompt, self._run(prompt))

    def run_evaluator(self, draft: RcaDraft, evidence: EvidencePackage, passages: tuple[KBPassage, ...],
                      product_version: str | None, kb_version_applicability: str) -> ModelInvocation:
        prompt = _evaluator_prompt(draft, evidence, passages, product_version, kb_version_applicability)
        return ModelInvocation(self._model or "copilot-cli-default", prompt, self._run(prompt))

    def _run(self, prompt: str) -> str:
        command = [
            self._executable,
            "--silent",
            "--no-ask-user",
            "--available-tools=",
            "--disable-builtin-mcps",
            "--no-custom-instructions",
            "--no-remote",
            "--no-remote-export",
        ]
        if self._model:
            command.append(f"--model={self._model}")
        try:
            with TemporaryDirectory(prefix="rca-copilot-") as directory:
                completed = subprocess.run(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=120,
                    cwd=directory,
                    env=_copilot_environment(),
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ModelRunnerError(f"Copilot CLI could not run: {error}. Run `copilot login` and retry.") from error
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise ModelRunnerError(f"Copilot CLI failed: {detail or 'unknown error'}. Run `copilot login` and retry.")
        return completed.stdout.strip()


def parse_analyst_output(raw_output: str, evidence: EvidencePackage, passages: tuple[KBPassage, ...]) -> RcaDraft:
    payload = _json_object(raw_output, "Analyst")
    hypotheses = payload.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        raise ModelRunnerError("Analyst output must contain at least one Hypothesis.")
    allowed_references = _evidence_references(evidence, passages)
    parsed_hypotheses: list[Hypothesis] = []
    for item in hypotheses:
        if not isinstance(item, dict):
            raise ModelRunnerError("Analyst Hypotheses must be objects.")
        supporting = _string_tuple(item.get("supporting_evidence"), "supporting_evidence")
        if not supporting:
            raise ModelRunnerError("Each Hypothesis requires supporting_evidence.")
        for reference in (*supporting, *_string_tuple(item.get("contradicting_evidence"), "contradicting_evidence")):
            if reference not in allowed_references:
                raise ModelRunnerError(f"Analyst output has unknown evidence reference: {reference}")
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise ModelRunnerError("Each Hypothesis confidence must be a number from 0 to 1.")
        parsed_hypotheses.append(Hypothesis(
            title=_required_text(item.get("title"), "Hypothesis title"),
            supporting_evidence=supporting,
            contradicting_evidence=_string_tuple(item.get("contradicting_evidence"), "contradicting_evidence"),
            unknowns=_string_tuple(item.get("unknowns"), "unknowns"),
            confidence=float(confidence),
        ))
    explanation = payload.get("most_likely_explanation")
    if explanation is not None and (not isinstance(explanation, str) or not explanation.strip()):
        raise ModelRunnerError("most_likely_explanation must be a non-empty string or null.")
    return RcaDraft(
        hypotheses=tuple(parsed_hypotheses),
        most_likely_explanation=explanation.strip() if isinstance(explanation, str) else None,
        unknowns=_string_tuple(payload.get("unknowns"), "unknowns"),
        recommended_actions=_string_tuple(payload.get("recommended_actions"), "recommended_actions"),
    )


def parse_evaluator_output(raw_output: str) -> Evaluation:
    payload = _json_object(raw_output, "Evaluator")
    result = payload.get("result")
    if result not in {"passed", "needs_evidence", "escalated"}:
        raise ModelRunnerError("Evaluator result must be passed, needs_evidence, or escalated.")
    evaluation = Evaluation(
        result=result,
        citation_gaps=_string_tuple(payload.get("citation_gaps"), "citation_gaps"),
        contradictions=_string_tuple(payload.get("contradictions"), "contradictions"),
        unknowns=_string_tuple(payload.get("unknowns"), "unknowns"),
        rationale=_required_text(payload.get("rationale"), "Evaluator rationale"),
    )
    if evaluation.result == "passed" and (evaluation.citation_gaps or evaluation.contradictions):
        raise ModelRunnerError("Evaluator cannot pass a draft with citation gaps or contradictions.")
    return evaluation


def _analyst_prompt(evidence: EvidencePackage, passages: tuple[KBPassage, ...], product_version: str | None,
                    applicability: str) -> str:
    return _prompt("RCA Analyst", {
        "evidence": _evidence_payload(evidence), "kb_passages": _passage_payload(passages),
        "product_version": product_version, "kb_version_applicability": applicability,
        "output": {"hypotheses": [{"title": "string", "supporting_evidence": ["citation"],
        "contradicting_evidence": ["citation"], "unknowns": ["string"], "confidence": 0.0}],
        "most_likely_explanation": "string or null", "unknowns": ["string"], "recommended_actions": ["string"]},
    })


def _evaluator_prompt(draft: RcaDraft, evidence: EvidencePackage, passages: tuple[KBPassage, ...], product_version: str | None,
                      applicability: str) -> str:
    return _prompt("RCA Evaluator", {
        "draft": _draft_payload(draft), "evidence": _evidence_payload(evidence), "kb_passages": _passage_payload(passages),
        "product_version": product_version, "kb_version_applicability": applicability,
        "output": {"result": "passed | needs_evidence | escalated", "citation_gaps": ["string"],
        "contradictions": ["string"], "unknowns": ["string"], "rationale": "string"},
    })


def _prompt(role: str, payload: dict[str, object]) -> str:
    return f"You are the {role}. Analyze only the supplied JSON. Do not use tools, files, URLs, or shell commands. Return only valid JSON matching output.\n" + json.dumps(payload)


def _evidence_payload(evidence: EvidencePackage) -> dict[str, object]:
    return {"observations": list(evidence.confirmed_observations), "reported_claims": list(evidence.reported_claims),
            "missing_evidence": list(evidence.missing_evidence), "attachments": [{"reference": item.reference, "filename": item.filename, "text": item.text} for item in evidence.attachments]}


def _passage_payload(passages: tuple[KBPassage, ...]) -> list[dict[str, str]]:
    return [{"citation_id": item.citation_id, "text": item.text} for item in passages]


def _draft_payload(draft: RcaDraft) -> dict[str, object]:
    return {"hypotheses": [{"title": item.title, "supporting_evidence": list(item.supporting_evidence), "contradicting_evidence": list(item.contradicting_evidence), "unknowns": list(item.unknowns), "confidence": item.confidence} for item in draft.hypotheses], "most_likely_explanation": draft.most_likely_explanation, "unknowns": list(draft.unknowns), "recommended_actions": list(draft.recommended_actions)}


def _evidence_references(evidence: EvidencePackage, passages: tuple[KBPassage, ...]) -> frozenset[str]:
    return frozenset((*[f"jira:observation:{index}" for index, _ in enumerate(evidence.confirmed_observations, 1)],
                      *[f"jira:claim:{index}" for index, _ in enumerate(evidence.reported_claims, 1)],
                      *[f"attachment:{item.reference}" for item in evidence.attachments if item.reference],
                      *(item.citation_id for item in passages)))


def _json_object(raw_output: str, role: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as error:
        raise ModelRunnerError(f"{role} output is not valid JSON.") from error
    if not isinstance(payload, dict):
        raise ModelRunnerError(f"{role} output must be a JSON object.")
    return payload


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelRunnerError(f"{name} must be a non-empty string.")
    return value.strip()


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ModelRunnerError(f"{name} must be a list of non-empty strings.")
    return tuple(item.strip() for item in value)


def _copilot_environment() -> dict[str, str]:
    keys = ("PATH", "HOME", "USERPROFILE", "COPILOT_HOME", "COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
    return {key: os.environ[key] for key in keys if key in os.environ}
