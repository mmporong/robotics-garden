from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("garden_publish.py")
SPEC = importlib.util.spec_from_file_location("garden_publish", MODULE_PATH)
assert SPEC and SPEC.loader
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class GardenPublishTests(unittest.TestCase):
    def test_lock_rejects_second_publisher_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as temp_name:
            lock = Path(temp_name) / "publish.lock"
            with publisher.exclusive_lock(lock):
                self.assertTrue(lock.exists())
                with self.assertRaisesRegex(RuntimeError, "진행 중"):
                    with publisher.exclusive_lock(lock):
                        pass
            self.assertFalse(lock.exists())

    def test_stale_lock_is_recovered(self):
        with tempfile.TemporaryDirectory() as temp_name:
            lock = Path(temp_name) / "publish.lock"
            lock.write_text("old\n", encoding="utf-8")
            old = time.time() - 20
            os.utime(lock, (old, old))
            with publisher.exclusive_lock(lock, stale_after=10):
                self.assertNotEqual(lock.read_text(encoding="utf-8"), "old\n")
            self.assertFalse(lock.exists())

    def test_daily_and_weekly_duplicate_detection_uses_kst_period(self):
        with tempfile.TemporaryDirectory() as temp_name:
            tree = Path(temp_name)
            (tree / "content/research").mkdir(parents=True)
            (tree / "content/insights").mkdir(parents=True)
            frontmatter = "---\ndate: {date}T08:00:00+09:00\npublish: true\n---\n"
            (tree / "content/research/old-draft-name.md").write_text(frontmatter.format(date="2026-11-05"), encoding="utf-8")
            (tree / "content/insights/another-old-name.md").write_text(frontmatter.format(date="2026-11-02"), encoding="utf-8")
            (tree / "content/research/2026-11-06_draft.md").write_text(
                "---\ndate: 2026-11-06T08:00:00+09:00\npublish: false\n---\n", encoding="utf-8"
            )
            now = dt.datetime(2026, 11, 5, 12, tzinfo=publisher.KST)
            self.assertTrue(publisher.already_published("daily", tree, now))
            self.assertTrue(publisher.already_published("weekly", tree, now))
            self.assertFalse(publisher.already_published("daily", tree, now + dt.timedelta(days=1)))
            self.assertFalse(publisher.already_published("weekly", tree, now + dt.timedelta(days=7)))

    def test_result_contract_accepts_only_mode_specific_hold(self):
        with tempfile.TemporaryDirectory() as temp_name:
            tree = Path(temp_name)
            daily = {
                "status": "hold",
                "reason": "no_candidate",
                "summary": "새 시뮬레이션 후보가 없음",
                "public_url": "",
                "commit": "",
            }
            publisher.verify_result(daily, "daily", tree)
            with self.assertRaisesRegex(RuntimeError, "보류"):
                publisher.verify_result(daily, "weekly", tree)

    def test_concurrent_already_published_is_a_clean_success(self):
        result = {
            "status": "success",
            "reason": "already_published",
            "summary": "다른 호스트가 오늘 글을 먼저 발행함",
            "public_url": "",
            "commit": "",
        }
        publisher.verify_result(result, "daily", Path("C:/unused"), "0" * 40)

    def test_success_requires_result_head_and_remote_to_match(self):
        result = {
            "status": "success",
            "reason": "published",
            "summary": "발행 완료",
            "public_url": publisher.SITE_ROOT + "research/example",
            "commit": "a" * 40,
        }
        answers = iter(["", "b" * 40, "a" * 40])
        with tempfile.TemporaryDirectory() as temp_name, mock.patch.object(
            publisher, "git", side_effect=lambda *args, **kwargs: next(answers)
        ), mock.patch.object(
            publisher, "run", return_value=mock.Mock(returncode=1)
        ):
            with self.assertRaisesRegex(RuntimeError, "origin/main 이력"):
                publisher.verify_result(result, "daily", Path(temp_name), "0" * 40)

    def test_load_result_rejects_unexpected_fields(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "result.json"
            path.write_text(json.dumps({
                "status": "hold",
                "reason": "no_candidate",
                "summary": "보류",
                "public_url": "",
                "commit": "",
                "extra": True,
            }), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "계약"):
                publisher.load_result(path)

    def test_prompt_pins_simulation_scope_and_single_repository(self):
        prompt = publisher.prompt_for("daily", Path("C:/isolated/garden"))
        self.assertIn("Isaac Sim", prompt)
        self.assertIn("OpenUSD", prompt)
        self.assertIn("physical-ai-lab과 메인 체크아웃을 수정하지 않는다", prompt)
        self.assertIn("하루에 한 편만 발행", prompt)

    def test_page_evidence_uses_rendered_link_text(self):
        with tempfile.TemporaryDirectory() as temp_name:
            article = Path(temp_name) / "article.md"
            article.write_text(
                "---\ntitle: \"링크 렌더 검증\"\ndate: 2026-11-05\npublish: true\n---\n\n"
                "[공식 문서](https://example.com)와 [[file-name|앞선 연구]]를 함께 읽으면 "
                "시뮬레이션의 실패 조건을 같은 기준으로 비교할 수 있어요.\n",
                encoding="utf-8",
            )
            title, evidence = publisher.page_evidence(article)
            self.assertEqual(title, "링크 렌더 검증")
            self.assertIn("공식 문서와 앞선 연구", evidence)
            self.assertNotIn("example.com", evidence)
            self.assertNotIn("file-name", evidence)

    def test_failure_artifact_includes_locally_committed_change(self):
        with tempfile.TemporaryDirectory() as repo_name, tempfile.TemporaryDirectory() as output_name:
            repo = Path(repo_name)
            publisher.run(["git", "init", "-q"], cwd=repo)
            publisher.run(["git", "config", "user.email", "test@example.com"], cwd=repo)
            publisher.run(["git", "config", "user.name", "Test"], cwd=repo)
            tracked = repo / "content.md"
            tracked.write_text("before\n", encoding="utf-8")
            publisher.run(["git", "add", "content.md"], cwd=repo)
            publisher.run(["git", "commit", "-qm", "base"], cwd=repo)
            base = publisher.git("rev-parse", "HEAD", cwd=repo)
            tracked.write_text("after\n", encoding="utf-8")
            publisher.run(["git", "commit", "-qam", "local article"], cwd=repo)
            (repo / "draft.md").write_text("draft\n", encoding="utf-8")
            destination = Path(output_name) / "artifacts"
            publisher.save_failure_artifacts(repo, destination, base)
            patch = (destination / "tracked.patch").read_text(encoding="utf-8")
            self.assertIn("+after", patch)
            self.assertEqual((destination / "untracked/draft.md").read_text(encoding="utf-8"), "draft\n")


if __name__ == "__main__":
    unittest.main()
