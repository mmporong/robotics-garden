from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import json
import os
import shutil
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
    def make_content_repo(self, root: Path) -> str:
        publisher.run(["git", "init", "-q"], cwd=root)
        publisher.run(["git", "config", "user.email", "test@example.com"], cwd=root)
        publisher.run(["git", "config", "user.name", "Test"], cwd=root)
        for folder in ("content/research", "content/insights", "content/assets"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("base\n", encoding="utf-8")
        publisher.run(["git", "add", "README.md"], cwd=root)
        publisher.run(["git", "commit", "-qm", "base"], cwd=root)
        return publisher.git("rev-parse", "HEAD", cwd=root)

    def write_daily_article(self, root: Path, body: str = "") -> Path:
        article = root / "content/research/2026-11-05_example.md"
        article.write_text(
            "---\ntitle: example\ndate: 2026-11-05T08:00:00+09:00\npublish: true\n---\n\n"
            '<figure><img src="../assets/example.png" alt="example"></figure>\n' + body,
            encoding="utf-8",
        )
        (root / "content/assets/example.png").write_bytes(b"fake-png-for-mocked-decoder")
        return article

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
        prompt = publisher.prompt_for("daily", Path("C:/isolated/garden"), "abc123")
        self.assertIn("Isaac Sim", prompt)
        self.assertIn("OpenUSD", prompt)
        self.assertIn("physical-ai-lab과 메인 체크아웃을 수정하지 않는다", prompt)
        self.assertIn("하루에 한 편만 발행", prompt)
        self.assertIn("--verify-content-only", prompt)
        self.assertIn('--base "abc123"', prompt)

    def test_prompt_targets_claude_publish_skill_without_browser(self):
        prompt = publisher.prompt_for("weekly", Path("C:/isolated/garden"), "abc123")
        self.assertIn(".claude", prompt)
        self.assertNotIn(".codex", prompt)
        self.assertNotIn("Codex", prompt)
        self.assertIn("브라우저를 열거나 앞으로 가져오지 않는다", prompt)
        self.assertIn("브라우저 상호작용 검증 미실행:", prompt)
        self.assertIn("콘텐츠 전용 게이트 PASS", prompt)

    def test_claude_command_passes_schema_without_meta_declaration(self):
        command = publisher.claude_command(Path("C:/bin/claude.exe"))
        self.assertEqual(command[:2], [str(Path("C:/bin/claude.exe")), "-p"])
        for flag in ("--no-session-persistence", "--dangerously-skip-permissions", "--verbose",
                     "--strict-mcp-config", "--no-chrome"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--output-format") + 1], "stream-json")
        schema = json.loads(command[command.index("--json-schema") + 1])
        self.assertNotIn("$schema", schema)
        self.assertEqual(set(schema["required"]), {"status", "reason", "summary", "public_url", "commit"})

    def test_agent_environment_disables_memory_and_background_and_drops_session_bindings(self):
        inherited = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "parent", "CLAUDE_CODE_MESSAGING_SOCKET": "sock",
                     "CLAUDE_CODE_CHILD_NOTES_DIR": "C:/tmp/started", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "0",
                     "CLAUDE_CODE_GIT_BASH_PATH": "C:/git/bash.exe", "PATH": "C:/bin"}
        with mock.patch.dict(os.environ, inherited, clear=True):
            env = publisher.agent_environment()
        self.assertEqual(env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")
        # 검토 서브에이전트가 백그라운드로 넘어가면 결과 강제 반환이 검토보다 먼저 온다.
        self.assertEqual(env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"], "1")
        for key in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_CHILD_NOTES_DIR"):
            self.assertNotIn(key, env)
        self.assertEqual(env["CLAUDE_CODE_GIT_BASH_PATH"], "C:/git/bash.exe")
        self.assertEqual(env["PATH"], "C:/bin")

    def test_prompt_summary_marks_satisfy_unattended_gate(self):
        prompt = publisher.prompt_for("daily", Path("C:/isolated/garden"), "abc123")
        summary = f"발행 완료. {publisher.CONTENT_ONLY_MARK} {publisher.UNATTENDED_REASON}; {publisher.CONTENT_GATE_PASS}"
        self.assertIn(f"{publisher.CONTENT_ONLY_MARK} {publisher.UNATTENDED_REASON}", prompt)
        self.assertIn(publisher.CONTENT_GATE_PASS, prompt)
        # 금지 표기를 그대로 인용하면 에이전트가 summary에 옮겨 적어 게이트가 오판할 수 있다.
        self.assertNotIn(publisher.BROWSER_PASS_MARK, prompt)
        with mock.patch.object(publisher, "verify_content_only", return_value={"media": []}) as gate:
            publisher.postpush_content_gate(summary, Path("C:/tree"), "a" * 40, "daily", require_content_only=True)
        gate.assert_called_once()

    def test_unattended_gate_rejects_browser_pass_claims(self):
        summaries = (
            f"{publisher.BROWSER_PASS_MARK}",
            f"{publisher.BROWSER_PASS_MARK}; {publisher.CONTENT_ONLY_MARK} x; {publisher.CONTENT_GATE_PASS}",
            "발행 성공",
        )
        for summary in summaries:
            with self.subTest(summary=summary), mock.patch.object(publisher, "verify_content_only") as gate:
                with self.assertRaisesRegex(RuntimeError, "콘텐츠 전용"):
                    publisher.postpush_content_gate(summary, Path("C:/tree"), "a" * 40, "daily", require_content_only=True)
                gate.assert_not_called()

    def test_structured_result_comes_from_last_result_event(self):
        expected = {"status": "hold", "reason": "no_candidate", "summary": "점검", "public_url": "", "commit": ""}
        with tempfile.TemporaryDirectory() as temp_name:
            events = Path(temp_name) / "events.jsonl"
            events.write_text(
                "\n".join([
                    json.dumps({"type": "system", "subtype": "init"}),
                    "not-json",
                    json.dumps({"type": "result", "subtype": "success", "is_error": False,
                                "structured_output": {"status": "failure"}}),
                    json.dumps({"type": "result", "subtype": "success", "is_error": False,
                                "structured_output": expected}, ensure_ascii=False),
                ]),
                encoding="utf-8",
            )
            result_path = Path(temp_name) / "result.json"
            self.assertEqual(publisher.extract_structured_result(events, result_path), expected)
            self.assertEqual(publisher.load_result(result_path), expected)

    def test_structured_result_rejects_error_or_missing_output(self):
        valid = {"status": "hold", "reason": "no_candidate", "summary": "점검", "public_url": "", "commit": ""}
        cases = {
            "missing-result": [json.dumps({"type": "assistant"})],
            "error": [json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True})],
            "no-structured": [json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "끝"})],
            "error-with-structured": [json.dumps({"type": "result", "subtype": "success", "is_error": True,
                                                  "structured_output": valid})],
        }
        for name, lines in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_name:
                events = Path(temp_name) / "events.jsonl"
                events.write_text("\n".join(lines), encoding="utf-8")
                result_path = Path(temp_name) / "result.json"
                with self.assertRaisesRegex(RuntimeError, "Claude"):
                    publisher.extract_structured_result(events, result_path)
                self.assertFalse(result_path.exists())

    def test_nonzero_exit_keeps_result_event_and_stderr_diagnostics(self):
        valid = {"status": "hold", "reason": "no_candidate", "summary": "점검", "public_url": "", "commit": ""}
        with tempfile.TemporaryDirectory() as temp_name:
            events = Path(temp_name) / "events.jsonl"
            errors = Path(temp_name) / "stderr.log"
            events.write_text(json.dumps({"type": "result", "subtype": "success", "is_error": True,
                                          "result": "사용 한도에 도달했습니다"}, ensure_ascii=False), encoding="utf-8")
            errors.write_text("[claude-code:rate_limit]\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, r"exit 1.*사용 한도에 도달했습니다.*rate_limit"):
                publisher.extract_structured_result(events, Path(temp_name) / "result.json", 1, errors)
            events.write_text(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                                          "structured_output": valid}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "exit 2"):
                publisher.extract_structured_result(events, Path(temp_name) / "result.json", 2, errors)

    def run_execute_with_agent(self, agent_events: list[dict[str, object]], returncode: int):
        """worktree·git·Claude 실행을 대신하고 execute()의 성공·실패 기록 흐름만 확인한다."""
        state = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, state, ignore_errors=True)
        tree = state / "tree"
        tree.mkdir()

        def fake_agent(command, worktree, prompt, events, errors):
            events.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in agent_events), encoding="utf-8")
            errors.write_text("", encoding="utf-8")
            return returncode

        with mock.patch.object(publisher, "STATE_ROOT", state), \
                mock.patch.object(publisher, "exclusive_lock", side_effect=lambda: contextlib.nullcontext()), \
                mock.patch.object(publisher, "prepare_worktree", return_value=tree), \
                mock.patch.object(publisher, "already_published", return_value=False), \
                mock.patch.object(publisher, "git", return_value="a" * 40), \
                mock.patch.object(publisher, "find_claude", return_value=Path("C:/bin/claude.exe")), \
                mock.patch.object(publisher, "run_agent", side_effect=fake_agent), \
                mock.patch.object(publisher, "verify_result") as verify, \
                mock.patch.object(publisher, "save_status") as save_status, \
                mock.patch.object(publisher, "save_failure_artifacts") as save_failure, \
                mock.patch.object(publisher, "cleanup_worktree") as cleanup:
            outcome: object
            try:
                outcome = publisher.execute("daily")
            except RuntimeError as exc:
                outcome = exc
        return outcome, verify, save_status, save_failure, cleanup

    def test_execute_records_failure_artifacts_for_agent_failures(self):
        cases = {
            "exit-1-is-error": ([{"type": "result", "subtype": "success", "is_error": True, "result": "모델 오류"}], 1),
            "no-result": ([{"type": "system", "subtype": "init"}], 0),
            "no-structured": ([{"type": "result", "subtype": "success", "is_error": False, "result": "끝"}], 0),
        }
        for name, (events, code) in cases.items():
            with self.subTest(name=name):
                outcome, verify, save_status, save_failure, cleanup = self.run_execute_with_agent(events, code)
                self.assertIsInstance(outcome, RuntimeError)
                self.assertIn("Claude 실행 실패", str(outcome))
                verify.assert_not_called()
                save_status.assert_not_called()
                save_failure.assert_called_once()
                cleanup.assert_called_once()

    def test_execute_success_requires_content_only_gate(self):
        hold = {"status": "hold", "reason": "no_candidate", "summary": "후보 없음", "public_url": "", "commit": ""}
        outcome, verify, save_status, save_failure, cleanup = self.run_execute_with_agent(
            [{"type": "result", "subtype": "success", "is_error": False, "structured_output": hold}], 0
        )
        self.assertEqual(outcome, 0)
        self.assertTrue(verify.call_args.kwargs["require_content_only"])
        save_status.assert_called_once_with("daily", hold)
        save_failure.assert_not_called()
        cleanup.assert_called_once()

    def test_content_only_accepts_one_article_and_referenced_raster(self):
        with tempfile.TemporaryDirectory() as temp_name:
            tree = Path(temp_name)
            base = self.make_content_repo(tree)
            self.write_daily_article(tree)
            with mock.patch.object(publisher, "validate_raster") as decode:
                result = publisher.verify_content_only(tree, base, "daily")
            self.assertEqual(result["article"], "content/research/2026-11-05_example.md")
            self.assertEqual(result["media"], ["content/assets/example.png"])
            decode.assert_called_once()

    def test_content_only_rejects_existing_file_modification(self):
        with tempfile.TemporaryDirectory() as temp_name:
            tree = Path(temp_name)
            base = self.make_content_repo(tree)
            self.write_daily_article(tree)
            (tree / "README.md").write_text("changed\n", encoding="utf-8")
            with mock.patch.object(publisher, "validate_raster"):
                with self.assertRaisesRegex(RuntimeError, "허용 범위 밖"):
                    publisher.verify_content_only(tree, base, "daily")

    def test_content_only_rejects_dynamic_html(self):
        cases = {
            "iframe": '<iframe src="https://example.com"></iframe>',
            "style": "<style>.fig{color:red}</style>",
            "link": '<link rel="stylesheet" href="x.css">',
            "srcset": '<img src="../assets/example.png" srcset="../assets/example.png 2x">',
        }
        for name, markup in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_name:
                tree = Path(temp_name)
                base = self.make_content_repo(tree)
                self.write_daily_article(tree, markup)
                with self.assertRaisesRegex(RuntimeError, "동적·상호작용"):
                    publisher.verify_content_only(tree, base, "daily")

    def test_browser_verified_result_skips_content_only_gate(self):
        with mock.patch.object(publisher, "verify_content_only") as gate:
            result = publisher.postpush_content_gate(
                "브라우저 상호작용 검증: PASS", Path("C:/tree"), "a" * 40, "daily"
            )
        self.assertIsNone(result)
        gate.assert_not_called()

    def test_content_only_result_runs_static_gate(self):
        expected = {"media": ["content/assets/example.png"]}
        with mock.patch.object(publisher, "verify_content_only", return_value=expected) as gate:
            result = publisher.postpush_content_gate(
                "브라우저 상호작용 검증 미실행: 무인 Claude 실행; 콘텐츠 전용 게이트 PASS",
                Path("C:/tree"), "a" * 40, "daily",
            )
        self.assertEqual(result, expected)
        gate.assert_called_once()

    def test_success_without_single_verification_mode_is_rejected(self):
        for summary in ("발행 성공", "브라우저 상호작용 검증: PASS; 브라우저 상호작용 검증 미실행: unavailable; 콘텐츠 전용 게이트 PASS"):
            with self.subTest(summary=summary), self.assertRaisesRegex(RuntimeError, "모드 표기"):
                publisher.postpush_content_gate(summary, Path("C:/tree"), "a" * 40, "daily")

    def test_content_only_rejects_unreferenced_new_media(self):
        with tempfile.TemporaryDirectory() as temp_name:
            tree = Path(temp_name)
            base = self.make_content_repo(tree)
            self.write_daily_article(tree)
            (tree / "content/assets/orphan.jpg").write_bytes(b"orphan")
            with mock.patch.object(publisher, "validate_raster"):
                with self.assertRaisesRegex(RuntimeError, "허용 범위 밖"):
                    publisher.verify_content_only(tree, base, "daily")

    def test_inert_svg_validator_accepts_static_original_figure(self):
        with tempfile.TemporaryDirectory() as temp_name:
            svg = Path(temp_name) / "figure.svg"
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="878.1" height="586.9">'
                '<defs><clipPath id="clip"><rect width="20" height="20"/></clipPath></defs>'
                '<g clip-path="url(#clip)"><path d="M0 0L20 20"/><text>solver</text></g></svg>',
                encoding="utf-8",
            )
            publisher.validate_inert_svg(svg)

    def test_inert_svg_validator_rejects_execution_and_links(self):
        cases = {
            "script": '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><script>x()</script></svg>',
            "event": '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" onload="x()"/>',
            "href": '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><image href="https://example.com/x.png"/></svg>',
        }
        with tempfile.TemporaryDirectory() as temp_name:
            for name, source in cases.items():
                with self.subTest(name=name):
                    svg = Path(temp_name) / f"{name}.svg"
                    svg.write_text(source, encoding="utf-8")
                    with self.assertRaises(RuntimeError):
                        publisher.validate_inert_svg(svg)

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
