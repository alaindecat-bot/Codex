from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import math
import re

from .parser import Message

QUESTION_PATTERNS = (
    re.compile(r"\?$"),
    re.compile(r"\b(est-ce|qu'est-ce|pourquoi|comment|quand|combien|qui|quel|quelle|quels|quelles)\b"),
    re.compile(r"\btu peux\b"),
    re.compile(r"\btu vas bien\b"),
    re.compile(r"\bet toi\b"),
    re.compile(r"\bça va\b|\bca va\b"),
)
STOPWORDS = {
    "a", "alors", "au", "aux", "avec", "ce", "ces", "dans", "de", "des", "du", "elle",
    "en", "et", "est", "il", "ils", "je", "j", "la", "le", "les", "mais", "me", "moi",
    "ne", "nous", "on", "ou", "pas", "pour", "que", "qui", "se", "si", "te", "toi",
    "tu", "un", "une", "vous", "y", "ça", "ca",
}
WEAK_OVERLAP_TOKENS = {
    "bien", "beaucoup", "bon", "bonne", "bonnes", "bons", "oui", "non", "ok", "hello",
    "salut", "merci", "temps", "soir", "jour", "année", "annee", "cool", "chouette",
    "vraiment", "tres", "très", "plus", "moins", "tout", "toute", "toutes", "tous",
    "suis", "suffisamment", "aussi", "maintenant", "mon", "ma", "mes",
}
SYSTEM_MESSAGE_PATTERNS = (
    re.compile(r"^\u200e?voice call\b", re.IGNORECASE),
    re.compile(r"^\u200e?video call\b", re.IGNORECASE),
    re.compile(r"\bno answer\b", re.IGNORECASE),
    re.compile(r"\bmissed voice call\b", re.IGNORECASE),
    re.compile(r"\bmissed video call\b", re.IGNORECASE),
)


@dataclass
class ReplyCandidate:
    response_index: int
    prompt_index: int
    score: float
    method: str
    rationale: str
    overlap: float = 0.0
    intervening_count: int = 0


def simple_local_candidates(messages: list[Message]) -> list[ReplyCandidate]:
    candidates: list[ReplyCandidate] = []
    for index, message in enumerate(messages):
        if not _is_textual_message(message):
            continue
        for candidate_index in range(index - 1, -1, -1):
            prompt = messages[candidate_index]
            if prompt.author == message.author:
                continue
            if not _is_textual_anchor(prompt):
                continue
            shared_tokens = _shared_content_tokens(prompt.body, message.body)
            if not shared_tokens:
                continue
            if not _looks_like_question(prompt.body) and len(shared_tokens) < 2:
                continue
            if len(shared_tokens) == 1 and len(prompt.body.strip()) > 120:
                continue
            gap = message.timestamp - prompt.timestamp
            if gap > timedelta(days=3):
                break
            candidates.append(
                ReplyCandidate(
                    response_index=index,
                    prompt_index=candidate_index,
                    score=max(0.0, 1.0 - gap.total_seconds() / (48 * 3600)),
                    method="heuristique_locale_simple",
                    rationale="Dernier message textuel precedent de l'autre personne.",
                    overlap=_token_overlap(prompt.body, message.body),
                    intervening_count=_intervening_textual_count(messages, candidate_index, index),
                )
            )
            break
    return candidates


def semantic_scoring_candidates(messages: list[Message]) -> list[ReplyCandidate]:
    links: list[ReplyCandidate] = []
    for index, message in enumerate(messages):
        if not _is_textual_message(message):
            continue
        best: ReplyCandidate | None = None
        for candidate_index in range(index - 1, -1, -1):
            prompt = messages[candidate_index]
            if prompt.author == message.author:
                continue
            if not _is_textual_anchor(prompt):
                continue
            shared_tokens = _shared_content_tokens(prompt.body, message.body)
            if not shared_tokens:
                continue
            if not _looks_like_question(prompt.body) and len(shared_tokens) < 2:
                continue
            if len(shared_tokens) == 1 and len(prompt.body.strip()) > 120:
                continue
            gap = message.timestamp - prompt.timestamp
            if gap > timedelta(days=7):
                break
            score, rationale, overlap = _semantic_score(messages, candidate_index, index, gap)
            if overlap <= 0.0:
                continue
            if score < 1.6:
                continue
            if best is None or score > best.score:
                best = ReplyCandidate(
                    response_index=index,
                    prompt_index=candidate_index,
                    score=score,
                    method="scoring_semantique",
                    rationale=rationale,
                    overlap=overlap,
                    intervening_count=_intervening_textual_count(messages, candidate_index, index),
                )
        if best is not None:
            links.append(best)
    return links


def render_candidates_markdown(
    messages: list[Message],
    candidates: list[ReplyCandidate],
    title: str,
) -> str:
    lines = [f"# {title}", ""]
    for candidate in candidates:
        prompt = messages[candidate.prompt_index]
        response = messages[candidate.response_index]
        lines.append(f"## [{response.timestamp:%d/%m %H:%M}] {response.author}")
        lines.append(f"- Reponse: {_single_line(response.body)}")
        lines.append(f"- Associe a: [{prompt.timestamp:%d/%m %H:%M}] {prompt.author}")
        lines.append(f"- Message source: {_single_line(prompt.body)}")
        lines.append(f"- Score: {candidate.score:.2f}")
        lines.append(f"- Chevauchement lexical: {candidate.overlap:.2f}")
        lines.append(f"- Messages intercalaires: {candidate.intervening_count}")
        lines.append(f"- Raison: {candidate.rationale}")
        lines.append("")
    return "\n".join(lines)


def _semantic_score(
    messages: list[Message],
    prompt_index: int,
    response_index: int,
    gap: timedelta,
) -> tuple[float, str, float]:
    score = 0.0
    reasons: list[str] = []

    prompt = messages[prompt_index]
    response = messages[response_index]
    prompt_text = prompt.body.strip()
    response_text = response.body.strip()
    prompt_lower = prompt_text.casefold()
    response_lower = response_text.casefold()

    if _looks_like_question(prompt_text):
        score += 1.6
        reasons.append("Message source de type question.")

    overlap = _token_overlap(prompt_text, response_text)
    if overlap > 0:
        score += overlap * 3.2
        reasons.append(f"Chevauchement lexical {overlap:.2f}.")

    if len(response_text) <= 140:
        score += 0.4
        reasons.append("Reponse concise.")

    if any(response_lower.startswith(prefix) for prefix in ("oui", "non", "ok", "très bien", "tres bien", "je ", "on ", "ça ", "ca ")):
        score += 0.6
        reasons.append("Debut compatible avec une reponse.")

    intervening = _intervening_textual_count(messages, prompt_index, response_index)
    if intervening <= 2:
        score += 0.7
        reasons.append("Peu d'echanges textuels intercalaires.")
    elif intervening >= 6:
        score -= 0.6
        reasons.append("Beaucoup d'echanges intercalaires.")

    hours = max(gap.total_seconds() / 3600, 0.0)
    decay = min(1.8, math.log1p(hours) * 0.45)
    score -= decay
    reasons.append(f"Penalite temporelle {decay:.2f}.")

    if len(prompt_text) > 220:
        score -= 0.4
        reasons.append("Message source long, moins susceptible d'etre le bon ancrage.")

    return score, " ".join(reasons), overlap


def _intervening_textual_count(messages: list[Message], prompt_index: int, response_index: int) -> int:
    count = 0
    for message in messages[prompt_index + 1 : response_index]:
        if _is_textual_message(message):
            count += 1
    return count


def _looks_like_question(text: str) -> bool:
    lowered = text.casefold()
    return any(pattern.search(lowered) for pattern in QUESTION_PATTERNS)


def _is_textual_message(message: Message) -> bool:
    body = message.body.strip()
    return (
        bool(body)
        and not _is_url_only(body)
        and not _is_system_message(body)
        and bool(re.search(r"[A-Za-zÀ-ÿ0-9]", body))
    )


def _is_textual_anchor(message: Message) -> bool:
    return _is_textual_message(message)


def _is_url_only(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("http://") or stripped.startswith("https://")


def _token_overlap(left: str, right: str) -> float:
    left_tokens = _content_tokens(left)
    right_tokens = _content_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    if not intersection:
        return 0.0
    return len(intersection) / min(len(left_tokens), len(right_tokens))


def _shared_content_tokens(left: str, right: str) -> set[str]:
    left_tokens = _content_tokens(left)
    right_tokens = _content_tokens(right)
    return left_tokens & right_tokens


def _content_tokens(text: str) -> set[str]:
    tokens = {token for token in re.findall(r"[A-Za-zÀ-ÿ']+", text.casefold()) if len(token) > 1}
    return {token for token in tokens if token not in STOPWORDS and token not in WEAK_OVERLAP_TOKENS}


def _is_system_message(text: str) -> bool:
    stripped = text.strip()
    return any(pattern.search(stripped) for pattern in SYSTEM_MESSAGE_PATTERNS)


def _single_line(text: str) -> str:
    return " ".join(part.strip() for part in text.splitlines() if part.strip())
