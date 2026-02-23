#!/usr/bin/env python3
"""
OpenReview review downloader (robust across many venues)

Main features
-------------
- Parses common OpenReview URLs and extracts an id.
- Resolves root forum id if user pastes a review/comment note URL.
- Tries OpenReview API v2 first, then falls back to API v1.
- Fetches forum replies broadly, then classifies notes heuristically.
- Exports raw text/Markdown/LaTeX content to md/txt/json.

This script is designed for rebuttal/review workflows where web copy-paste
can break math and formatting.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import traceback
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import openreview


DEFAULT_BASEURL_V2 = "https://api2.openreview.net"
DEFAULT_BASEURL_V1 = "https://api.openreview.net"

VALID_INCLUDE_TYPES = {
    "review",
    "meta_review",
    "decision",
    "comment",
    "response",
    "other",
    "all",
}

ATTACHMENT_LIKE_KEYS = {
    "pdf",
    "supplementary_material",
    "supplementary",
    "video",
    "presentation",
    "slides",
    "code",
    "dataset",
    "software",
    "appendix",
    "zip",
    "tar",
    "tgz",
}

REVIEW_SIGNAL_KEYS = {
    "review",
    "main_review",
    "summary",
    "strengths",
    "weaknesses",
    "questions",
    "limitations",
    "rating",
    "confidence",
    "soundness",
    "presentation",
    "contribution",
    "correctness",
    "ethics_review",
    "technical_novelty_and_significance",
    "empirical_novelty_and_significance",
}

META_REVIEW_SIGNAL_KEYS = {
    "metareview",
    "meta_review",
    "recommendation",
    "committee_comment",
    "area_chair_comment",
    "senior_area_chair_comment",
}

DECISION_SIGNAL_KEYS = {
    "decision",
    "decision_comment",
    "final_decision",
}

RESPONSE_SIGNAL_KEYS = {
    "response",
    "author_response",
    "rebuttal",
}

COMMENT_SIGNAL_KEYS = {
    "comment",
    "public_comment",
}

COMMON_REVIEW_INVITATION_SUFFIXES = [
    "Official_Review",
    "Review",
    "Ethics_Review",
    "Paper_Review",
]

TEXT_FIRST_KEY_ORDER = [
    "summary",
    "main_review",
    "review",
    "strengths",
    "weaknesses",
    "questions",
    "limitations",
    "ethics_review",
    "soundness",
    "presentation",
    "contribution",
    "rating",
    "confidence",
    "comment",
    "response",
    "decision",
    "decision_comment",
]


@dataclass
class ParsedURL:
    raw_url: str
    id_value: Optional[str]
    venue_id_hint: Optional[str]
    query: Dict[str, List[str]]


@dataclass
class ClassifiedNote:
    note: Any
    note_id: str
    forum: Optional[str]
    replyto: Optional[str]
    invitation: Optional[str]
    invitation_suffix: Optional[str]
    category: str
    subtype: Optional[str]
    score: int
    direct_reply_to_forum: bool
    signature_label: Optional[str]
    signatures: List[str]
    content: Dict[str, Any]
    content_text_blocks: List[Tuple[str, str]]
    cdate: Optional[int]
    mdate: Optional[int]


def debug_print(enabled: bool, msg: str) -> None:
    if enabled:
        print(f"[debug] {msg}")


def strip_quotes(s: str) -> str:
    return s.strip().strip("“”\"'")


def sanitize_filename(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[^\w.\-]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s[:200]


def norm_token(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def timestamp_ms_to_iso(ms: Optional[int]) -> Optional[str]:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()
    except Exception:
        return None


def get_note_attr(note: Any, attr: str, default: Any = None) -> Any:
    return getattr(note, attr, default)


def note_to_json_dict(note: Any) -> Dict[str, Any]:
    if note is None:
        return {}
    if isinstance(note, dict):
        return note
    if hasattr(note, "to_json"):
        try:
            out = note.to_json()
            if isinstance(out, dict):
                return out
        except Exception:
            pass
    try:
        return dict(note.__dict__)
    except Exception:
        return {"repr": repr(note)}


def clean_pasted_url(raw: str) -> str:
    """
    Handle cases where users paste:
    - plain URL
    - <URL>
    - markdown link: [label](URL)
    """
    s = raw.strip()

    # Markdown link form: [text](url)
    md_match = re.match(r"^\[[^\]]+\]\((https?://[^)]+)\)$", s)
    if md_match:
        return md_match.group(1)

    # Angle-bracket URL
    if s.startswith("<") and s.endswith(">"):
        return s[1:-1].strip()

    return s


def parse_openreview_url(url: str) -> ParsedURL:
    url = clean_pasted_url(url)

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    # Some OpenReview links may carry useful params in fragments
    if not query and parsed.fragment and "=" in parsed.fragment:
        frag_query = parse_qs(parsed.fragment)
        if frag_query:
            query = frag_query

    id_value = None
    for key in ("id", "noteId", "forum", "paperId"):
        if key in query and query[key]:
            id_value = query[key][0]
            break

    venue_id_hint = None
    referrer_vals = query.get("referrer", [])
    if referrer_vals:
        referrer = unquote(referrer_vals[0])
        # weak parse only; do not assume one format
        m = re.search(r"[?&]id=([A-Za-z0-9._/\-]+)", referrer)
        if m:
            venue_id_hint = m.group(1)

    return ParsedURL(raw_url=url, id_value=id_value, venue_id_hint=venue_id_hint, query=query)


def recursive_extract_text(value: Any) -> Optional[str]:
    """
    Extract text from common OpenReview content encodings:
    - "string"
    - {"value": "string"}
    - {"value": 8}
    - {"value": ["a", "b"]}
    - nested dict/list structures
    """
    if value is None:
        return None

    if isinstance(value, str):
        t = value.strip()
        return t if t else None

    if isinstance(value, (int, float, bool)):
        return str(value)

    if isinstance(value, list):
        parts = []
        for item in value:
            t = recursive_extract_text(item)
            if t:
                parts.append(t)
        return ", ".join(parts) if parts else None

    if isinstance(value, dict):
        for wrapper_key in ("value", "values"):
            if wrapper_key in value:
                return recursive_extract_text(value[wrapper_key])

        parts = []
        for k, v in value.items():
            t = recursive_extract_text(v)
            if t:
                parts.append(f"{k}: {t}")
        return "\n".join(parts) if parts else None

    return str(value)


def normalize_content_dict(note: Any) -> Dict[str, Any]:
    content = get_note_attr(note, "content", None)
    if content is None:
        note_json = note_to_json_dict(note)
        maybe = note_json.get("content")
        return maybe if isinstance(maybe, dict) else {}

    if isinstance(content, dict):
        return content

    if hasattr(content, "to_json"):
        try:
            out = content.to_json()
            if isinstance(out, dict):
                return out
        except Exception:
            pass

    try:
        return dict(content)
    except Exception:
        return {}


def is_probable_attachment_field(key: str, extracted_text: Optional[str]) -> bool:
    key_l = key.lower().strip()
    if key_l in ATTACHMENT_LIKE_KEYS:
        return True

    if extracted_text and key_l in ATTACHMENT_LIKE_KEYS:
        t = extracted_text.strip()
        if len(t) < 500 and ("http://" in t or "https://" in t):
            return True

    return False


def ordered_content_blocks(content: Dict[str, Any], skip_attachment_fields: bool = True) -> List[Tuple[str, str]]:
    if not content:
        return []

    original_keys = list(content.keys())

    def key_rank(k: str) -> Tuple[int, int]:
        k_l = k.lower()
        if k_l in TEXT_FIRST_KEY_ORDER:
            return (0, TEXT_FIRST_KEY_ORDER.index(k_l))
        if any(x in k_l for x in ("review", "summary", "strength", "weak", "question", "comment", "response", "decision")):
            return (1, 0)
        if any(x in k_l for x in ("rating", "confidence", "score")):
            return (2, 0)
        return (3, original_keys.index(k))

    keys_sorted = sorted(original_keys, key=key_rank)

    blocks: List[Tuple[str, str]] = []
    for key in keys_sorted:
        text = recursive_extract_text(content.get(key))
        if not text:
            continue
        if skip_attachment_fields and is_probable_attachment_field(key, text):
            continue
        blocks.append((key, text))
    return blocks


def normalize_invitation_suffix(invitation: Optional[str]) -> Optional[str]:
    if not invitation:
        return None
    if "/-/" in invitation:
        return invitation.split("/-/", 1)[1]
    return invitation.rsplit("/", 1)[-1]


def extract_signature_label(signatures: Sequence[str]) -> Optional[str]:
    if not signatures:
        return None

    raw = str(signatures[0])
    tail = raw.split("/")[-1]

    # Common normalisations
    tail = tail.replace("_", " ").strip()
    tail_l = tail.lower()

    if "reviewer" in tail_l:
        return tail.title()
    if "area chair" in tail_l:
        return tail.title()
    if "senior area chair" in tail_l:
        return tail.title()
    if "program chair" in tail_l:
        return tail.title()
    if "author" in tail_l:
        return tail.title()

    return tail or raw


def classify_note(note: Any, forum_id: str, skip_attachment_fields: bool = True) -> ClassifiedNote:
    note_id = str(get_note_attr(note, "id", "") or "")
    forum = get_note_attr(note, "forum", None)
    replyto = get_note_attr(note, "replyto", None)
    invitation = get_note_attr(note, "invitation", None)
    invitation_suffix = normalize_invitation_suffix(invitation)
    invitation_token = norm_token(invitation_suffix or "")

    signatures = list(get_note_attr(note, "signatures", []) or [])
    sig_join = " ".join(map(str, signatures)).lower()

    content = normalize_content_dict(note)
    content_blocks = ordered_content_blocks(content, skip_attachment_fields=skip_attachment_fields)
    content_keys = {norm_token(k) for k in content.keys()}

    category = "other"
    subtype = None
    score = 0

    direct_reply_to_forum = (str(replyto) == str(forum_id))
    if direct_reply_to_forum:
        score += 2

    # Invitation signals (strongest)
    if invitation_token:
        if "decision" in invitation_token:
            category = "decision"
            score += 6
        elif "meta" in invitation_token and "review" in invitation_token:
            category = "meta_review"
            score += 6
        elif "review" in invitation_token:
            category = "review"
            score += 6
        elif "response" in invitation_token or "rebuttal" in invitation_token:
            category = "response"
            score += 5
        elif "comment" in invitation_token:
            category = "comment"
            score += 4

        if "ethics" in invitation_token and "review" in invitation_token:
            subtype = "ethics_review"
        elif "official" in invitation_token and "review" in invitation_token:
            subtype = "official_review"

    # Signature signals (score bump, not hard rule)
    if "reviewer" in sig_join:
        score += 2
        if category == "other":
            category = "review"
    if "area_chair" in sig_join or "senior_area_chair" in sig_join or "/ac" in sig_join:
        score += 2
        if category == "other":
            category = "meta_review"
    if "program_chair" in sig_join:
        score += 2
    if "author" in sig_join:
        score += 1
        if category == "other":
            category = "response"

    # Content signals
    review_hits = len(content_keys & REVIEW_SIGNAL_KEYS)
    meta_hits = len(content_keys & META_REVIEW_SIGNAL_KEYS)
    decision_hits = len(content_keys & DECISION_SIGNAL_KEYS)
    response_hits = len(content_keys & RESPONSE_SIGNAL_KEYS)
    comment_hits = len(content_keys & COMMENT_SIGNAL_KEYS)

    if category == "other":
        if decision_hits > 0:
            category = "decision"
            score += 4
        elif meta_hits > 0:
            category = "meta_review"
            score += 4
        elif review_hits > 0:
            category = "review"
            score += 4
        elif response_hits > 0:
            category = "response"
            score += 3
        elif comment_hits > 0:
            category = "comment"
            score += 2

    # Extra review hints
    if category in {"comment", "other"} and ("rating" in content_keys or "confidence" in content_keys):
        category = "review"
        score += 3

    cdate = get_note_attr(note, "cdate", None)
    mdate = get_note_attr(note, "mdate", None)

    return ClassifiedNote(
        note=note,
        note_id=note_id,
        forum=forum,
        replyto=replyto,
        invitation=invitation,
        invitation_suffix=invitation_suffix,
        category=category,
        subtype=subtype,
        score=score,
        direct_reply_to_forum=direct_reply_to_forum,
        signature_label=extract_signature_label(signatures),
        signatures=signatures,
        content=content,
        content_text_blocks=content_blocks,
        cdate=cdate,
        mdate=mdate,
    )


def include_category(category: str, include_set: set[str]) -> bool:
    return "all" in include_set or category in include_set


def parse_csv_set(raw: Optional[str], valid: Optional[set[str]] = None) -> set[str]:
    if not raw:
        return set()
    items = {x.strip() for x in raw.split(",") if x.strip()}
    if valid is not None:
        bad = items - valid
        if bad:
            raise ValueError(f"Invalid value(s): {sorted(bad)}; valid: {sorted(valid)}")
    return items


def try_login_clients(email: str, password: str, baseurl: str, debug: bool = False):
    errors = []

    # v2 first
    try:
        client = openreview.api.OpenReviewClient(
            baseurl=baseurl,
            username=email,
            password=password,
        )
        # lightweight validation (if available)
        try:
            _ = client.get_profiles(ids=[email])
        except Exception as e:
            debug_print(debug, f"v2 validation call warning: {e}")
        return client, "v2", baseurl
    except Exception as e:
        errors.append(("v2", baseurl, str(e)))
        debug_print(debug, f"v2 login failed @ {baseurl}: {e}")

    # v1 fallback
    if hasattr(openreview, "Client"):
        tried_v1 = []
        for b in [DEFAULT_BASEURL_V1, baseurl]:
            if b in tried_v1:
                continue
            tried_v1.append(b)
            try:
                client = openreview.Client(
                    baseurl=b,
                    username=email,
                    password=password,
                )
                # lightweight validation call may vary; tolerate failure
                try:
                    _ = client.get_profile(email)
                except Exception as e:
                    debug_print(debug, f"v1 validation call warning @ {b}: {e}")
                return client, "v1", b
            except Exception as e:
                errors.append(("v1", b, str(e)))
                debug_print(debug, f"v1 login failed @ {b}: {e}")

    lines = ["Login failed for all attempted clients:"]
    for kind, b, msg in errors:
        lines.append(f"  - {kind} @ {b}: {msg}")
    raise RuntimeError("\n".join(lines))


def get_note(client: Any, note_id: str):
    return client.get_note(id=note_id)


def get_all_notes_safe(client: Any, **kwargs):
    return client.get_all_notes(**kwargs)


def resolve_forum_id_from_id(client: Any, id_value: str, debug: bool = False) -> Tuple[str, Optional[Any]]:
    """
    If the given id points to a reply note, resolve the root forum id.
    """
    try:
        note = get_note(client, id_value)
    except Exception as e:
        debug_print(debug, f"Could not fetch id '{id_value}' as note: {e}")
        return id_value, None

    forum = get_note_attr(note, "forum", None)
    if forum:
        return str(forum), note
    return id_value, note


def infer_venue_id_from_submission_note(submission_note: Any) -> Optional[str]:
    if submission_note is None:
        return None
    invitation = get_note_attr(submission_note, "invitation", None)
    if invitation and "/-/" in invitation:
        return invitation.split("/-/", 1)[0]
    return None


def fetch_replies_robust(client: Any, forum_id: str, venue_id: Optional[str], debug: bool = False) -> List[Any]:
    """
    Retrieval strategy:
    1) broad fetch by forum id
    2) fallback by replyto
    3) fallback by common invitation names if venue id is known
    """
    collected: List[Any] = []
    seen: set[str] = set()

    def add_notes(notes: Iterable[Any], source: str) -> None:
        before = len(seen)
        for n in notes or []:
            nid = str(get_note_attr(n, "id", "") or "")
            if not nid:
                continue
            if nid not in seen:
                seen.add(nid)
                collected.append(n)
        debug_print(debug, f"{source}: +{len(seen)-before}, total={len(seen)}")

    # Main path
    try:
        add_notes(get_all_notes_safe(client, forum=forum_id), "get_all_notes(forum=...)")
    except Exception as e:
        debug_print(debug, f"forum fetch failed: {e}")

    # Fallback: direct replies only
    if not collected:
        try:
            add_notes(get_all_notes_safe(client, replyto=forum_id), "get_all_notes(replyto=...)")
        except Exception as e:
            debug_print(debug, f"replyto fetch failed: {e}")

    # Fallback: common invitation names
    if not collected and venue_id:
        for suffix in COMMON_REVIEW_INVITATION_SUFFIXES:
            invitation = f"{venue_id}/-/{suffix}"
            try:
                add_notes(
                    get_all_notes_safe(client, forum=forum_id, invitation=invitation),
                    f"get_all_notes(forum=..., invitation={invitation})",
                )
            except Exception as e:
                debug_print(debug, f"invitation fallback failed ({invitation}): {e}")

    # Remove root submission note if included
    out = []
    for n in collected:
        if str(get_note_attr(n, "id", "") or "") == str(forum_id):
            continue
        out.append(n)

    out.sort(key=lambda n: ((get_note_attr(n, "cdate", None) or 0), str(get_note_attr(n, "id", ""))))
    return out


def format_field_title(key: str) -> str:
    return key.replace("_", " ").strip().title()


def make_markdown_block(cn: ClassifiedNote, index: int) -> str:
    category_display = cn.category if not cn.subtype else f"{cn.category} / {cn.subtype}"
    label = cn.signature_label or f"Item {index}"

    lines: List[str] = []
    lines.append(f"## {label}")
    lines.append("")
    lines.append(f"- **Category:** `{category_display}`")
    lines.append(f"- **Note ID:** `{cn.note_id}`")
    if cn.invitation:
        lines.append(f"- **Invitation:** `{cn.invitation}`")
    if cn.replyto:
        lines.append(f"- **Reply-To:** `{cn.replyto}`")
    lines.append(f"- **Direct reply to forum:** `{cn.direct_reply_to_forum}`")

    if cn.signatures:
        sig_text = ", ".join(cn.signatures)
        if len(sig_text) > 400:
            sig_text = sig_text[:397] + "..."
        lines.append(f"- **Signatures:** `{sig_text}`")

    cdate_iso = timestamp_ms_to_iso(cn.cdate)
    mdate_iso = timestamp_ms_to_iso(cn.mdate)
    if cdate_iso:
        lines.append(f"- **Created (UTC):** {cdate_iso}")
    if mdate_iso and mdate_iso != cdate_iso:
        lines.append(f"- **Modified (UTC):** {mdate_iso}")

    lines.append("")

    for key, text in cn.content_text_blocks:
        token = norm_token(key)
        if token in {"review", "comment", "text", "response", "author_response", "rebuttal"}:
            lines.append(text)
            lines.append("")
        else:
            lines.append(f"### {format_fieldTitle(key)}")
            lines.append("")
            lines.append(text)
            lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def format_fieldTitle(key: str) -> str:
    # separate helper to avoid accidental shadowing; keep same formatting
    return key.replace("_", " ").strip().title()


def make_text_block(cn: ClassifiedNote, index: int) -> str:
    category_display = cn.category if not cn.subtype else f"{cn.category} / {cn.subtype}"
    label = cn.signature_label or f"Item {index}"

    lines: List[str] = []
    lines.append(f"--- {label} ---")
    lines.append(f"Category: {category_display}")
    lines.append(f"Note ID: {cn.note_id}")
    if cn.invitation:
        lines.append(f"Invitation: {cn.invitation}")
    if cn.replyto:
        lines.append(f"Reply-To: {cn.replyto}")
    lines.append(f"Direct reply to forum: {cn.direct_reply_to_forum}")
    if cn.signatures:
        lines.append(f"Signatures: {', '.join(cn.signatures)}")

    cdate_iso = timestamp_ms_to_iso(cn.cdate)
    mdate_iso = timestamp_ms_to_iso(cn.mdate)
    if cdate_iso:
        lines.append(f"Created (UTC): {cdate_iso}")
    if mdate_iso and mdate_iso != cdate_iso:
        lines.append(f"Modified (UTC): {mdate_iso}")
    lines.append("")

    for key, text in cn.content_text_blocks:
        token = norm_token(key)
        if token in {"review", "comment", "text", "response", "author_response", "rebuttal"}:
            lines.append(text)
        else:
            lines.append(f"[{format_field_title(key)}]")
            lines.append(text)
        lines.append("")

    lines.append("=" * 80)
    lines.append("")
    return "\n".join(lines)


def classified_note_to_json(cn: ClassifiedNote) -> Dict[str, Any]:
    return {
        "note_id": cn.note_id,
        "forum": cn.forum,
        "replyto": cn.replyto,
        "invitation": cn.invitation,
        "invitation_suffix": cn.invitation_suffix,
        "category": cn.category,
        "subtype": cn.subtype,
        "score": cn.score,
        "direct_reply_to_forum": cn.direct_reply_to_forum,
        "signature_label": cn.signature_label,
        "signatures": cn.signatures,
        "cdate": cn.cdate,
        "mdate": cn.mdate,
        "cdate_iso_utc": timestamp_ms_to_iso(cn.cdate),
        "mdate_iso_utc": timestamp_ms_to_iso(cn.mdate),
        "readers": get_note_attr(cn.note, "readers", None),
        "writers": get_note_attr(cn.note, "writers", None),
        "content": cn.content,
        "content_text_blocks": [{"field": k, "text": t} for k, t in cn.content_text_blocks],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download OpenReview forum replies (reviews/meta-reviews/decisions/comments/responses) as raw Markdown/text/JSON."
    )
    parser.add_argument("--email", type=str, required=True, help="Your OpenReview login email.")
    parser.add_argument("--url", type=str, help="OpenReview URL for the paper/forum/review.")
    parser.add_argument("--forum_id", type=str, help="Manual override for root forum ID.")
    parser.add_argument("--venue_id", type=str, help="Optional manual venue ID (fallback only).")
    parser.add_argument("--baseurl", type=str, default=DEFAULT_BASEURL_V2, help=f"API baseurl (default: {DEFAULT_BASEURL_V2})")

    parser.add_argument(
        "--include",
        type=str,
        default="review",
        help="Comma-separated categories: review,meta_review,decision,comment,response,other,all (default: review)",
    )
    parser.add_argument(
        "--formats",
        type=str,
        default="md,txt",
        help="Comma-separated formats: md,txt,json (default: md,txt)",
    )
    parser.add_argument("--output-dir", type=str, default="reviews", help="Output directory (default: reviews)")
    parser.add_argument(
        "--password-env-var",
        type=str,
        default="OPENREVIEW_PASSWORD",
        help="Environment variable for password (default: OPENREVIEW_PASSWORD)",
    )

    parser.add_argument(
        "--direct-only",
        action="store_true",
        help="Export only notes that are direct replies to the root forum (useful for many venues).",
    )
    parser.add_argument(
        "--keep-attachment-fields",
        action="store_true",
        help="Keep attachment-like fields (pdf/supplementary/video/etc.) in exported content.",
    )
    parser.add_argument("--debug", action="store_true", help="Print debug output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        include_set = parse_csv_set(args.include, VALID_INCLUDE_TYPES) or {"review"}
        formats = parse_csv_set(args.formats, {"md", "txt", "json"}) or {"md", "txt"}
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(2)

    forum_id = args.forum_id.strip() if args.forum_id else None
    venue_id = args.venue_id.strip() if args.venue_id else None

    if args.url:
        print(f"Parsing URL: {args.url}")
        parsed = parse_openreview_url(args.url)
        if not parsed.id_value:
            print("Warning: Could not parse an id from the URL.")
        else:
            print(f"Parsed id from URL: {parsed.id_value}")
        if not forum_id and parsed.id_value:
            forum_id = parsed.id_value
        if not venue_id and parsed.venue_id_hint:
            venue_id = parsed.venue_id_hint
            print(f"Parsed venue_id hint from referrer: {venue_id}")

    if not forum_id:
        print("Error: Could not determine root forum ID. Please provide --url or --forum_id.")
        sys.exit(1)

    email_to_use = strip_quotes(args.email)

    password = os.environ.get(args.password_env_var, "")
    if password:
        print(f"Using password from environment variable: {args.password_env_var}")
    else:
        password = getpass.getpass(prompt=f"Enter OpenReview password for {email_to_use}: ")

    try:
        client, client_kind, baseurl_used = try_login_clients(
            email=email_to_use,
            password=password,
            baseurl=args.baseurl,
            debug=args.debug,
        )
        print(f"Successfully logged in as {email_to_use} using {client_kind} client @ {baseurl_used}")
    except Exception as e:
        print(f"Login failed:\n{e}")
        sys.exit(1)

    # Resolve root forum id if user pasted a review/comment URL
    forum_id_resolved, _ = resolve_forum_id_from_id(client, forum_id, debug=args.debug)
    if forum_id_resolved != forum_id:
        print(f"Resolved root forum ID: {forum_id_resolved} (from input id: {forum_id})")
        forum_id = forum_id_resolved

    # Attempt venue inference from the root submission note
    submission_note = None
    try:
        submission_note = get_note(client, forum_id)
    except Exception as e:
        debug_print(args.debug, f"Could not fetch root submission note {forum_id}: {e}")

    if not venue_id and submission_note is not None:
        venue_id = infer_venue_id_from_submission_note(submission_note)
        if venue_id:
            print(f"Auto-detected venue_id from submission invitation: {venue_id}")

    replies = fetch_replies_robust(client, forum_id=forum_id, venue_id=venue_id, debug=args.debug)

    if not replies:
        print("No replies were found in this forum.")
        print("Possible reasons:")
        print("- reviews are not released yet")
        print("- the logged-in account does not have permission")
        print("- venue visibility differs from the expected OpenReview setup")
        sys.exit(0)

    print(f"Fetched {len(replies)} reply note(s). Classifying...")

    classified: List[ClassifiedNote] = []
    counts = Counter()

    for note in replies:
        cn = classify_note(
            note,
            forum_id=forum_id,
            skip_attachment_fields=not args.keep_attachment_fields,
        )
        classified.append(cn)
        counts[cn.category] += 1

    print("Detected categories:")
    for k in ["review", "meta_review", "decision", "comment", "response", "other"]:
        print(f"  - {k}: {counts.get(k, 0)}")

    selected: List[ClassifiedNote] = []
    for cn in classified:
        if not include_category(cn.category, include_set):
            continue
        if args.direct_only and not cn.direct_reply_to_forum:
            continue
        if not cn.content_text_blocks:
            continue
        selected.append(cn)

    if not selected:
        print(f"No notes matched include={sorted(include_set)}")
        if args.direct_only:
            print("Hint: try again without --direct-only")
        sys.exit(0)

    # Direct replies first, then time, then id
    selected.sort(key=lambda x: (0 if x.direct_reply_to_forum else 1, (x.cdate or 0), x.note_id))

    os.makedirs(args.output_dir, exist_ok=True)

    include_label = "all" if "all" in include_set else "_".join(sorted(include_set))
    direct_label = "_direct" if args.direct_only else ""
    base_name = sanitize_filename(f"openreview_{forum_id}_{include_label}{direct_label}")

    out_md = os.path.join(args.output_dir, f"{base_name}.md") if "md" in formats else None
    out_txt = os.path.join(args.output_dir, f"{base_name}.txt") if "txt" in formats else None
    out_json = os.path.join(args.output_dir, f"{base_name}.json") if "json" in formats else None

    generated_utc = datetime.now(timezone.utc).isoformat()

    md_header_lines = [
        "# OpenReview Export",
        "",
        f"- **Forum ID:** `{forum_id}`",
        f"- **Venue ID (hint/inferred):** `{venue_id}`" if venue_id else "- **Venue ID (hint/inferred):** `unknown`",
        f"- **Included categories:** `{', '.join(sorted(include_set))}`",
        f"- **Direct replies only:** `{args.direct_only}`",
        f"- **Fetched replies:** `{len(replies)}`",
        f"- **Exported items:** `{len(selected)}`",
        f"- **Generated (UTC):** {generated_utc}",
        "",
        "## Detected Category Counts",
        "",
    ]
    for k in ["review", "meta_review", "decision", "comment", "response", "other"]:
        md_header_lines.append(f"- `{k}`: {counts.get(k, 0)}")
    md_header_lines.extend(["", "---", ""])

    txt_header_lines = [
        "OpenReview Export",
        "",
        f"Forum ID: {forum_id}",
        f"Venue ID (hint/inferred): {venue_id or 'unknown'}",
        f"Included categories: {', '.join(sorted(include_set))}",
        f"Direct replies only: {args.direct_only}",
        f"Fetched replies: {len(replies)}",
        f"Exported items: {len(selected)}",
        f"Generated (UTC): {generated_utc}",
        "",
        "Detected Category Counts:",
    ]
    for k in ["review", "meta_review", "decision", "comment", "response", "other"]:
        txt_header_lines.append(f"  - {k}: {counts.get(k, 0)}")
    txt_header_lines.extend(["", "=" * 80, ""])

    try:
        if out_md:
            with open(out_md, "w", encoding="utf-8") as f:
                f.write("\n".join(md_header_lines))
                for i, cn in enumerate(selected, start=1):
                    f.write(make_markdown_block(cn, i))

        if out_txt:
            with open(out_txt, "w", encoding="utf-8") as f:
                f.write("\n".join(txt_header_lines))
                for i, cn in enumerate(selected, start=1):
                    f.write(make_text_block(cn, i))

        if out_json:
            payload = {
                "forum_id": forum_id,
                "venue_id": venue_id,
                "generated_utc": generated_utc,
                "include": sorted(include_set),
                "direct_only": args.direct_only,
                "fetched_reply_count": len(replies),
                "exported_count": len(selected),
                "detected_category_counts": dict(counts),
                "items": [classified_note_to_json(cn) for cn in selected],
            }
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"Error writing output files: {e}")
        if args.debug:
            traceback.print_exc()
        sys.exit(1)

    print(f"\nSuccess: exported {len(selected)} item(s).")
    if out_md:
        print(f"Markdown file: {out_md}")
    if out_txt:
        print(f"Text file:     {out_txt}")
    if out_json:
        print(f"JSON file:     {out_json}")


if __name__ == "__main__":
    main()