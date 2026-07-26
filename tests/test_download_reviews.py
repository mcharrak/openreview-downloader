"""Regression tests for complete OpenReview forum exports.

The tests stub the optional ``openreview`` dependency so they run without an
account, network access, or a locally installed OpenReview client.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "download_reviews.py"


def load_downloader_module():
    """Import the script with the smallest API surface needed by these tests."""
    openreview_stub = types.SimpleNamespace(
        api=types.SimpleNamespace(OpenReviewClient=object), Client=object
    )
    module_name = "download_reviews_under_test"
    sys.modules.pop(module_name, None)
    with patch.dict(sys.modules, {"openreview": openreview_stub}):
        spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return module


downloader = load_downloader_module()


class FakeClient:
    def __init__(self, by_query):
        self.by_query = by_query
        self.calls = []

    def get_all_notes(self, **kwargs):
        self.calls.append(kwargs)
        return self.by_query.get(tuple(sorted(kwargs.items())), [])


class CompleteForumExportTests(unittest.TestCase):
    def test_default_include_is_all_categories(self):
        with patch.object(sys, "argv", ["download_reviews.py", "--email", "author@example.com"]):
            args = downloader.parse_args()
        self.assertEqual(args.include, "all")

    def test_thread_and_direct_reply_routes_are_merged_and_deduplicated(self):
        forum_id = "forum-1"
        review = {
            "id": "review-1",
            "forum": forum_id,
            "replyto": forum_id,
            "cdate": 30,
            "content": {"review": {"value": "Reviewer report"}},
        }
        meta_review = {
            "id": "meta-1",
            "forum": forum_id,
            "replyto": forum_id,
            "cdate": 20,
            "invitation": "NeurIPS.cc/2026/Conference/-/Meta_Review",
            "content": {"recommendation": {"value": "Revise the experiments."}},
        }
        nested_reply = {
            "id": "reply-1",
            "forum": forum_id,
            "replyto": "review-1",
            "cdate": 40,
            "signatures": ["NeurIPS.cc/2026/Conference/Authors"],
            "content": {"response": {"value": "Author response"}},
        }
        client = FakeClient(
            {
                (("forum", forum_id),): [review, nested_reply],
                (("replyto", forum_id),): [review, meta_review],
            }
        )

        notes = downloader.fetch_replies_robust(client, forum_id, venue_id=None)

        self.assertEqual([note["id"] for note in notes], ["meta-1", "review-1", "reply-1"])
        self.assertEqual(client.calls, [{"forum": forum_id}, {"replyto": forum_id}])

        classified = [downloader.classify_note(note, forum_id) for note in notes]
        self.assertEqual([item.category for item in classified], ["meta_review", "review", "response"])
        self.assertEqual(len(downloader.select_notes(classified, {"all"}, False)), 3)
        self.assertEqual(len(downloader.select_notes(classified, {"review"}, False)), 1)

    def test_empty_visible_note_is_retained_and_marked_in_text_exports(self):
        note = {
            "id": "decision-1",
            "forum": "forum-1",
            "replyto": "forum-1",
            "invitation": "NeurIPS.cc/2026/Conference/-/Decision",
            "content": {},
        }
        classified = downloader.classify_note(note, "forum-1")

        self.assertEqual(classified.category, "decision")
        self.assertEqual(downloader.select_notes([classified], {"all"}, False), [classified])
        self.assertIn("No textual content fields", downloader.make_markdown_block(classified, 1))
        self.assertIn("No textual content fields", downloader.make_text_block(classified, 1))


if __name__ == "__main__":
    unittest.main()
