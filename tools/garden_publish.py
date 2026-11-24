#!/usr/bin/env python3
"""Windows에서 가든의 일간 리서치와 주간 인사이트를 무인 발행한다."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from pathlib import PurePosixPath

KST = dt.timezone(dt.timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PUBLICATION = ROOT / "publication"
SCHEMA = PUBLICATION / "publish-result.schema.json"
STATE_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "robotics-garden-publish"
LOCK = STATE_ROOT / "publish.lock"
LOCK_STALE_AFTER = 6 * 60 * 60
SITE_ROOT = "https://mmporong.github.io/robotics-garden/"
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
# 프롬프트와 push 후 게이트가 같은 표기를 쓰도록 summary 계약 문구를 한곳에 둔다.
BROWSER_PASS_MARK = "브라우저 상호작용 검증: PASS"
CONTENT_ONLY_MARK = "브라우저 상호작용 검증 미실행:"
CONTENT_GATE_PASS = "콘텐츠 전용 게이트 PASS"
UNATTENDED_REASON = "무인 Claude 실행"
# 호출한 Claude 세션에 묶인 변수다. 수동 실행 때 자식 CLI가 부모 세션의 메시징·감독 상태를 물려받지 않게 뺀다.
SESSION_BOUND_ENV = (
    "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_PID", "CLAUDE_CODE_ENTRYPOINT",
)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif"}
STATIC_IMAGE_EXTENSIONS = RASTER_EXTENSIONS | {".svg"}
FORBIDDEN_SVG_TAGS = {
    "a", "animate", "animateMotion", "animateTransform", "audio", "foreignObject",
    "iframe", "object", "script", "set", "style", "video",
}
FORBIDDEN_CONTENT = re.compile(
    r"<(?:script|style|link|iframe|object|embed|video|audio|canvas|svg)\b|\bsrcset\s*=|\bon[a-z]+\s*=|javascript:|data:text/html",
    re.IGNORECASE,
)


def run(args: list[str], *, cwd: Path | None = None, input_text: str | None = None,
        capture: bool = True, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
        check=check,
        shell=False,
        creationflags=NO_WINDOW,
    )


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> str:
    return run(["git", *args], cwd=cwd, check=check).stdout.strip()


def find_claude() -> Path:
    candidates = [Path.home() / ".local/bin/claude.exe"]
    # .cmd 래퍼는 cmd.exe를 거쳐 --json-schema 인자의 %·^ 같은 문자를 해석할 수 있어 마지막 대안으로만 둔다.
    found = shutil.which("claude.exe") or shutil.which("claude.cmd") or shutil.which("claude")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("Claude Code CLI를 찾지 못했습니다")


@contextlib.contextmanager
def exclusive_lock(path: Path = LOCK, stale_after: int = LOCK_STALE_AFTER):
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as exc:
            age = time.time() - path.stat().st_mtime
            if attempt == 0 and age > stale_after:
                stale = path.with_name(f"{path.name}.stale-{os.getpid()}")
                path.rename(stale)
                stale.unlink(missing_ok=True)
                continue
            raise RuntimeError(f"다른 발행 실행이 진행 중입니다: {path}") from exc
    try:
        os.write(fd, f"{os.getpid()}\n".encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def published_dates(folder: Path) -> list[dt.date]:
    dates = []
    for path in folder.glob("*.md"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not match or not re.search(r"^publish:\s*true\s*$", match.group(1), re.MULTILINE | re.IGNORECASE):
            continue
        date_match = re.search(r"^date:\s*[\"']?(\d{4}-\d{2}-\d{2})", match.group(1), re.MULTILINE)
        if date_match:
            dates.append(dt.date.fromisoformat(date_match.group(1)))
    return dates


def already_published(mode: str, tree: Path, now: dt.datetime | None = None) -> bool:
    today = (now or dt.datetime.now(KST)).astimezone(KST).date()
    if mode == "daily":
        return today in published_dates(tree / "content/research")
    year, week, _ = today.isocalendar()
    return any(d.isocalendar()[:2] == (year, week) for d in published_dates(tree / "content/insights"))


def prompt_for(mode: str, tree: Path, base: str = "<BASE_SHA>") -> str:
    contract = (PUBLICATION / ("daily-simulation.md" if mode == "daily" else "weekly-insight.md")).read_text(encoding="utf-8")
    label = "일간 시뮬레이션 리서치" if mode == "daily" else "주간 종합 인사이트"
    return f"""publish 스킬로 {label} 한 편을 발행한다.

무인 자동 발행이다. 사용자 확인을 기다리거나 외부 메시지·알림을 보내지 말고 성공·보류·실패 중 하나가 확정될 때까지 진행한다.
Skill 도구로 publish 스킬을 불러오고, {Path.home() / '.claude/skills/publish/SKILL.md'} 전체, {ROOT / 'AGENTS.md'}와 {tree / 'STYLE_GUIDE.md'}를 읽고 따른다.

Windows 발행용 최신 origin/main 격리 worktree는 다음 경로다.
{tree}

이 경로 안에서만 작성·검증·커밋·push한다. physical-ai-lab과 메인 체크아웃을 수정하지 않는다. worktree·clone을 더 만들지 않고 npm ci와 플러그인 설치를 실행하지 않는다. 준비된 node_modules와 .quartz를 사용한다.
전역 Claude 설정·모델·플러그인·예약 작업을 바꾸지 않는다.

무인 실행에서는 브라우저를 열거나 앞으로 가져오지 않는다. 브라우저 PASS를 만들지 말고 콘텐츠 전용 모드로 진행한다. 작성 패스와 검증 패스를 분리하고(검증은 작성하지 않은 서브에이전트나 별도 단계로), push 전에 아래 명령이 PASS해야 한다.
python "{ROOT / 'tools/garden_publish.py'}" --verify-content-only --tree "{tree}" --base "{base}" --mode {mode}

검증 서브에이전트와 오래 걸리는 명령은 포그라운드로 실행하고 결과를 받기 전에 응답을 끝내지 않는다. 이 실행에서는 응답을 끝내는 즉시 최종 결과 반환이 강제된다. 그래도 독립 검증이 끝나기 전에 결과 반환을 요구받으면 status=failure, reason=runtime_failed로 반환하고, 검증 완료 알림이 오면 남은 수정·재검증·발행을 마친 뒤 최종 결과를 다시 반환한다. 마지막으로 반환한 결과만 기록된다.

콘텐츠 전용 모드에서는 새 Markdown 한 편과 그 글이 참조하는 비상호작용 정적 미디어만 추가할 수 있다. 래스터 이미지와 실행 요소·이벤트·외부 참조가 없는 원문 정적 SVG만 허용한다. 기존 콘텐츠·기존 자산·Quartz·설정·패키지·CSS·JavaScript는 수정하지 않고, script·iframe·object·embed·새 도식 HTML을 넣지 않는다. audit_terms 결과 같은 검증 사이드카는 worktree 밖 {STATE_ROOT / 'logs'} 아래에 둔다. 성공 summary에는 `{CONTENT_ONLY_MARK} {UNATTENDED_REASON}`과 `{CONTENT_GATE_PASS}`를 모두 적고, 브라우저 검증을 통과했다는 표기는 쓰지 않는다.

아래 모드 계약을 모두 적용한다.

{contract}

새 글을 발행한 성공이면 status=success, reason=published, 실제 공개 URL과 origin/main에 push한 커밋 SHA를 기록한다. push 직전 다른 호스트가 같은 주기의 글을 먼저 발행한 것을 확인했다면 status=success, reason=already_published로 끝내고 URL과 commit을 비운다. 정상 보류와 실패도 URL과 commit을 비우며, 실제 reason을 쓴다. 최종 결과는 지정된 JSON schema의 구조화 출력으로만 반환한다.
"""


def result_schema() -> str:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    # Claude CLI의 --json-schema 검증기는 2020-12 메타스키마 선언($schema)을 거부한다.
    schema.pop("$schema", None)
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


def claude_command(claude: Path) -> list[str]:
    return [
        str(claude), "-p",
        "--output-format", "stream-json", "--verbose",
        "--no-session-persistence", "--dangerously-skip-permissions",
        # MCP 서버와 Chrome 연동을 싣지 않아 무인 실행이 사용자 브라우저를 쓰지 못하게 한다.
        "--strict-mcp-config", "--no-chrome",
        "--json-schema", result_schema(),
    ]


def agent_environment() -> dict[str, str]:
    env = {
        key: value for key, value in os.environ.items()
        if key not in SESSION_BOUND_ENV and not key.startswith("CLAUDE_CODE_CHILD_")
    }
    # 실행마다 임시 worktree 경로가 달라, 자동 메모리를 기록하면 경로별 메모리 폴더가 따로 생긴다.
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    # -p --json-schema 실행은 응답이 끝나는 즉시 구조화 결과를 강제한다. 검토 서브에이전트가 백그라운드로
    # 넘어가면 결과를 받기 전에 failure를 반환하게 되므로(2026-11-24 일간 실행) 백그라운드 실행을 끈다.
    env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] = "1"
    return env


def extract_structured_result(events: Path, result: Path, returncode: int = 0,
                              errors: Path | None = None) -> dict[str, object]:
    """마지막 result 이벤트에서 구조화 결과를 꺼낸다.

    CLI는 is_error 결과를 낸 뒤 비정상 종료하므로, 종료 코드와 관계없이 result 이벤트의 진단을 먼저 읽어
    실패 메시지에 남긴다.
    """
    final: dict[str, object] | None = None
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            final = event
    structured = final.get("structured_output") if final is not None else None
    if returncode == 0 and final is not None and not final.get("is_error") and isinstance(structured, dict):
        result.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
        return structured
    details = [f"exit {returncode}"]
    if final is None:
        details.append("최종 result 이벤트 없음")
    else:
        details.append(
            f"subtype={final.get('subtype')} is_error={final.get('is_error')} stop_reason={final.get('stop_reason')}"
        )
        if not isinstance(structured, dict):
            details.append("구조화 결과 없음")
        if final.get("result"):
            details.append(f"result={str(final.get('result'))[-400:]}")
    if errors is not None and errors.exists():
        stderr_tail = errors.read_text(encoding="utf-8", errors="replace").strip()[-600:]
        if stderr_tail:
            details.append(f"stderr={stderr_tail}")
    raise RuntimeError("Claude 실행 실패: " + " | ".join(details))


def link_directory(link: Path, target: Path) -> None:
    if link.exists():
        return
    if not target.is_dir():
        raise RuntimeError(f"공유할 의존성 디렉터리가 없습니다: {target}")
    run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)])


def prepare_worktree(base: Path) -> Path:
    git("fetch", "--quiet", "origin", "main")
    tree = base / "garden"
    git("worktree", "add", "--detach", str(tree), "origin/main")
    link_directory(tree / "node_modules", ROOT / "node_modules")
    link_directory(tree / ".quartz", ROOT / ".quartz")
    return tree


def cleanup_worktree(tree: Path | None) -> None:
    if tree is None:
        return
    resolved_tree = tree.resolve(strict=False)
    resolved_state = STATE_ROOT.resolve(strict=False)
    if resolved_state not in resolved_tree.parents:
        raise RuntimeError(f"정리 대상이 발행 상태 경로 밖입니다: {resolved_tree}")
    # Junction만 먼저 해제해야 공유 캐시를 worktree 제거가 따라가지 않는다.
    for name in ("node_modules", ".quartz"):
        link = tree / name
        if os.path.isjunction(link):
            os.rmdir(link)
    git("worktree", "remove", "--force", str(tree), check=False)
    git("worktree", "prune", check=False)


def load_result(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"발행 결과 JSON을 읽지 못했습니다: {exc}") from exc
    required = {"status", "reason", "summary", "public_url", "commit"}
    if not isinstance(value, dict) or set(value) != required or not isinstance(value["summary"], str) or not value["summary"].strip():
        raise RuntimeError("발행 결과 계약이 맞지 않습니다")
    return value


def run_agent(command: list[str], tree: Path, prompt: str, events: Path, errors: Path,
              timeout: int = 5 * 60 * 60) -> int:
    with events.open("w", encoding="utf-8") as stdout, errors.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            command,
            cwd=tree,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            creationflags=NO_WINDOW,
            env=agent_environment(),
        )
        try:
            process.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], check=False)
                process.wait(timeout=30)
            else:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise RuntimeError("Claude 실행이 5시간 제한을 넘었습니다")
        return process.returncode


def save_failure_artifacts(tree: Path, destination: Path, base: str | None = None) -> None:
    if not tree.is_dir():
        return
    destination.mkdir(parents=True, exist_ok=True)
    diff_args = ["git", "diff", "--binary", "--no-ext-diff"]
    if base:
        diff_args.append(base)
    diff = run(diff_args, cwd=tree, check=False)
    if diff.stdout:
        (destination / "tracked.patch").write_text(diff.stdout, encoding="utf-8")
    untracked = git("ls-files", "--others", "--exclude-standard", cwd=tree, check=False).splitlines()
    for relative in untracked:
        source = tree / relative
        if not source.is_file() or relative.startswith(("node_modules/", ".quartz/")):
            continue
        target = destination / "untracked" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def save_status(mode: str, payload: dict[str, object]) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    (STATE_ROOT / f"last-{mode}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def changed_files(tree: Path, base: str) -> dict[str, str]:
    changes: dict[str, str] = {}
    output = git("diff", "--name-status", "--no-renames", base, cwd=tree)
    for line in output.splitlines():
        if not line.strip():
            continue
        status, path = line.split("\t", 1)
        changes[path.replace("\\", "/")] = status
    for path in git("ls-files", "--others", "--exclude-standard", cwd=tree).splitlines():
        changes.setdefault(path.replace("\\", "/"), "A")
    return changes


def markdown_media_paths(article: Path) -> set[str]:
    text = article.read_text(encoding="utf-8")
    references = set(re.findall(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\']', text, re.IGNORECASE))
    references.update(re.findall(r"!\[[^\]]*\]\(<?([^\s)>]+)", text))
    paths: set[str] = set()
    for reference in references:
        clean = urllib.parse.unquote(reference.split("?", 1)[0].split("#", 1)[0]).replace("\\", "/")
        if "://" in clean or clean.startswith(("data:", "/")):
            raise RuntimeError(f"콘텐츠 전용 미디어는 content/assets의 로컬 파일이어야 합니다: {reference}")
        pure = PurePosixPath(clean)
        if pure.suffix.lower() not in STATIC_IMAGE_EXTENSIONS or pure.parent.as_posix() != "../assets":
            raise RuntimeError(f"허용되지 않은 미디어 참조입니다: {reference}")
        paths.add(f"content/assets/{pure.name}")
    return paths


def validate_raster(path: Path, tree: Path) -> None:
    script = (
        "import sharp from 'sharp';"
        "const p=process.argv[1];const m=await sharp(p).metadata();"
        "if(!m.width||!m.height)process.exit(2);await sharp(p).raw().toBuffer();"
    )
    completed = run(
        ["node", "--input-type=module", "-e", script, str(path)],
        cwd=tree,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"래스터 미디어 디코딩 실패: {path.name}: {completed.stderr[-500:]}")


def validate_inert_svg(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if re.search(r"<!DOCTYPE|<!ENTITY", source, re.IGNORECASE):
        raise RuntimeError(f"SVG에 DTD 또는 entity 선언이 있습니다: {path.name}")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise RuntimeError(f"SVG XML 파싱 실패: {path.name}: {exc}") from exc
    local = lambda name: name.rsplit("}", 1)[-1]
    if local(root.tag) != "svg":
        raise RuntimeError(f"SVG 루트 요소가 아닙니다: {path.name}")
    for element in root.iter():
        tag = local(element.tag)
        if tag in FORBIDDEN_SVG_TAGS:
            raise RuntimeError(f"SVG에 실행·상호작용 요소가 있습니다: {tag}")
        for attribute, value in element.attrib.items():
            attr = local(attribute).lower()
            lowered = value.lower().strip()
            if attr.startswith("on") or attr == "href" or "javascript:" in lowered:
                raise RuntimeError(f"SVG에 이벤트·링크 속성이 있습니다: {attr}")
            for target in re.findall(r"url\(([^)]+)\)", value, re.IGNORECASE):
                if not target.strip(" \"'").startswith("#"):
                    raise RuntimeError("SVG에 외부 URL 참조가 있습니다")
    width = root.attrib.get("width", "")
    height = root.attrib.get("height", "")
    view_box = root.attrib.get("viewBox", "")
    numeric = lambda value: float(re.match(r"^[0-9]+(?:\.[0-9]+)?", value).group()) if re.match(r"^[0-9]+(?:\.[0-9]+)?", value) else 0
    if not ((numeric(width) > 0 and numeric(height) > 0) or len(view_box.split()) == 4):
        raise RuntimeError(f"SVG 크기를 확인할 수 없습니다: {path.name}")


def validate_static_image(path: Path, tree: Path) -> None:
    if path.suffix.lower() == ".svg":
        validate_inert_svg(path)
    else:
        validate_raster(path, tree)


def verify_content_only(tree: Path, base: str, mode: str) -> dict[str, object]:
    if not tree.is_dir():
        raise RuntimeError(f"worktree가 없습니다: {tree}")
    git("cat-file", "-e", f"{base}^{{commit}}", cwd=tree)
    changes = changed_files(tree, base)
    prefix = "content/research/" if mode == "daily" else "content/insights/"
    articles = [path for path, status in changes.items() if path.startswith(prefix) and path.endswith(".md") and not path.endswith("/index.md") and status == "A"]
    if len(articles) != 1:
        raise RuntimeError(f"새 {mode} Markdown이 정확히 한 편이어야 합니다: {articles}")
    article_path = articles[0]
    article = tree / article_path
    article_text = article.read_text(encoding="utf-8")
    if FORBIDDEN_CONTENT.search(article_text):
        raise RuntimeError("콘텐츠 전용 글에 동적·상호작용 HTML 또는 실행 가능한 속성이 있습니다")
    media_refs = markdown_media_paths(article)
    minimum_media = 1 if mode == "daily" else 2
    if len(media_refs) < minimum_media:
        raise RuntimeError(f"{mode} 글에는 래스터 정적 미디어가 최소 {minimum_media}개 필요합니다")
    allowed = {article_path, *media_refs}
    unexpected = sorted(set(changes) - allowed)
    if unexpected:
        raise RuntimeError(f"콘텐츠 전용 허용 범위 밖 변경입니다: {unexpected}")
    for path, status in changes.items():
        if status != "A":
            raise RuntimeError(f"기존 파일 수정·삭제는 허용되지 않습니다: {status} {path}")
        if run(["git", "cat-file", "-e", f"{base}:{path}"], cwd=tree, check=False).returncode == 0:
            raise RuntimeError(f"기준 커밋에 이미 있던 파일입니다: {path}")
    new_media = {path for path in changes if path.startswith("content/assets/")}
    if new_media - media_refs:
        raise RuntimeError(f"새 글이 참조하지 않는 신규 미디어가 있습니다: {sorted(new_media - media_refs)}")
    for media in media_refs:
        media_path = tree / media
        if not media_path.is_file():
            raise RuntimeError(f"참조 미디어 파일이 없습니다: {media}")
        if media in new_media:
            validate_static_image(media_path, tree)
    return {"mode": mode, "article": article_path, "media": sorted(media_refs), "changes": sorted(changes)}


def changed_article(mode: str, tree: Path, base: str, commit: str) -> Path:
    prefix = "content/research/" if mode == "daily" else "content/insights/"
    names = git("diff", "--name-only", f"{base}..{commit}", cwd=tree).splitlines()
    matches = [Path(name) for name in names if name.startswith(prefix) and name.endswith(".md") and not name.endswith("/index.md")]
    if len(matches) != 1:
        raise RuntimeError(f"이번 실행의 새 글이 정확히 한 편이 아닙니다: {matches}")
    return tree / matches[0]


def postpush_content_gate(summary: str, tree: Path, base: str, mode: str,
                          require_content_only: bool = False) -> dict[str, object] | None:
    browser_verified = BROWSER_PASS_MARK in summary
    content_only = CONTENT_ONLY_MARK in summary and CONTENT_GATE_PASS in summary
    if require_content_only:
        # 무인 실행에는 브라우저 도구가 없으므로 브라우저 PASS 주장은 콘텐츠 게이트 우회 시도로 본다.
        if browser_verified or not content_only:
            raise RuntimeError("무인 실행 결과는 콘텐츠 전용 게이트 표기만 허용합니다")
        return verify_content_only(tree, base, mode)
    if browser_verified == content_only:
        raise RuntimeError("success summary의 브라우저 검증 모드 표기가 없거나 서로 충돌합니다")
    if content_only:
        return verify_content_only(tree, base, mode)
    return None


def page_evidence(article: Path) -> tuple[str, str]:
    source = article.read_text(encoding="utf-8")
    title_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', source, re.MULTILINE)
    if not title_match:
        raise RuntimeError("새 글의 title을 찾지 못했습니다")
    body = re.sub(r"^---\s*\n.*?\n---\s*", "", source, count=1, flags=re.DOTALL)
    body = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", body)
    body = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", body)
    body = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)
    body = re.sub(r"<[^>]+>|\[\[|\]\]|[*_`#>|-]", " ", body)
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n\s*\n", body)]
    evidence = next((part[:80] for part in paragraphs if len(part) >= 40 and not part.startswith("출처 ")), "")
    if not evidence:
        raise RuntimeError("공개 페이지에서 확인할 본문 고유 문장을 찾지 못했습니다")
    return title_match.group(1), evidence


def verify_result(result: dict[str, object], mode: str, tree: Path, base: str | None = None,
                  require_content_only: bool = False) -> None:
    status = result["status"]
    reason = result["reason"]
    public_url = result["public_url"]
    commit = result["commit"]
    if status == "success" and reason == "already_published":
        if public_url != "" or commit != "":
            raise RuntimeError("중복 발행 생략 결과의 URL과 commit은 비어 있어야 합니다")
        return
    if status == "hold":
        expected = "no_candidate" if mode == "daily" else "insufficient_material"
        if reason != expected or public_url != "" or commit != "":
            raise RuntimeError("정상 보류 결과가 모드 계약과 맞지 않습니다")
        return
    if status == "failure":
        if reason not in {"runtime_failed", "gate_failed", "deployment_failed"} or public_url != "" or commit != "":
            raise RuntimeError("실패 결과 계약이 맞지 않습니다")
        raise RuntimeError(str(result["summary"]))
    if status != "success" or reason != "published" or not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
        raise RuntimeError("성공 결과 계약이 맞지 않습니다")
    if not isinstance(public_url, str) or not public_url.startswith(SITE_ROOT):
        raise RuntimeError("공개 URL이 가든 주소가 아닙니다")
    if not base:
        base = git("rev-parse", f"{commit}^", cwd=tree)
    git("fetch", "--quiet", "origin", "main", cwd=tree)
    remote = git("rev-parse", "origin/main", cwd=tree)
    resolved = git("rev-parse", commit, cwd=tree)
    if run(["git", "merge-base", "--is-ancestor", resolved, remote], cwd=tree, check=False).returncode != 0:
        raise RuntimeError(f"결과 커밋이 origin/main 이력에 없습니다: result={resolved} origin/main={remote}")
    if resolved == base or run(["git", "merge-base", "--is-ancestor", base, resolved], cwd=tree, check=False).returncode != 0:
        raise RuntimeError(f"결과 커밋이 실행 시작점 뒤에 있지 않습니다: base={base} result={resolved}")
    gate = postpush_content_gate(str(result["summary"]), tree, base, mode, require_content_only)
    article = changed_article(mode, tree, base, resolved)
    expected_slug = article.relative_to(tree / "content").with_suffix("").as_posix()
    if expected_slug not in urllib.parse.unquote(public_url):
        raise RuntimeError(f"공개 URL이 새 글 slug와 맞지 않습니다: {expected_slug}")
    title, evidence = page_evidence(article)
    last_error = ""
    for delay in (0, 20, 40, 60, 60, 60):
        if delay:
            time.sleep(delay)
        try:
            encoded_url = urllib.parse.quote(public_url, safe=":/%?=&")
            request = urllib.request.Request(encoded_url, headers={"User-Agent": "robotics-garden-publisher/1.0"})
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.status == 200:
                    raw_html = response.read().decode("utf-8", errors="replace")
                    rendered = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", raw_html)).split())
                    if title in rendered and evidence in rendered:
                        if gate is None:
                            return
                        media_ready = True
                        for media in gate["media"]:
                            name = Path(str(media)).name
                            if name not in urllib.parse.unquote(raw_html):
                                media_ready = False
                                last_error = f"공개 HTML에 미디어가 없음: {name}"
                                break
                            media_url = urllib.parse.urljoin(SITE_ROOT, "assets/" + urllib.parse.quote(name))
                            try:
                                with urllib.request.urlopen(
                                    urllib.request.Request(media_url, headers={"User-Agent": "robotics-garden-publisher/1.0"}),
                                    timeout=20,
                                ) as media_response:
                                    if media_response.status != 200 or not media_response.read(32):
                                        media_ready = False
                                        last_error = f"공개 미디어 응답 실패: {name}"
                                        break
                            except (urllib.error.URLError, TimeoutError) as exc:
                                media_ready = False
                                last_error = f"공개 미디어 확인 실패: {name}: {exc}"
                                break
                        if media_ready:
                            return
                        continue
                    last_error = "제목 또는 본문 고유 문장이 아직 배포되지 않음"
                    continue
                last_error = f"HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
    raise RuntimeError(f"공개 URL 확인 실패: {last_error}")


SMOKE_PROMPT = (
    "읽기 전용 연결 점검이다. 도구를 쓰지 말고 파일·Git·외부 서비스를 변경하지 않는다. "
    "구조화 결과로 status=hold, reason=no_candidate, summary=AUTOMATION_SMOKE_OK, public_url=\"\", commit=\"\"을 반환한다."
)


def smoke() -> int:
    """실제 발행과 같은 명령·환경·기본 모델로 구조화 결과 경로를 점검한다. 도구는 끈다."""
    command = claude_command(find_claude()) + ["--tools", ""]
    # 시간 초과 때 남은 훅 프로세스가 로그를 잡고 있어도 정리 오류가 원래 예외를 가리지 않게 한다.
    with tempfile.TemporaryDirectory(prefix="smoke-", ignore_cleanup_errors=True) as temp_name:
        temp = Path(temp_name)
        events, errors, result_path = temp / "events.jsonl", temp / "stderr.log", temp / "result.json"
        with events.open("w", encoding="utf-8") as stdout, errors.open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(
                command, input=SMOKE_PROMPT, text=True, encoding="utf-8", errors="replace",
                stdout=stdout, stderr=stderr, cwd=ROOT, env=agent_environment(),
                timeout=300, shell=False, creationflags=NO_WINDOW,
            )
        result = extract_structured_result(events, result_path, completed.returncode, errors)
        load_result(result_path)
        if result.get("status") != "hold" or result.get("summary") != "AUTOMATION_SMOKE_OK":
            raise RuntimeError(f"Claude 스모크 구조화 결과가 맞지 않습니다: {result}")
    print("AUTOMATION_SMOKE_OK")
    return 0


def execute(mode: str) -> int:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    logs = STATE_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    stamp = dt.datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    with exclusive_lock():
        with tempfile.TemporaryDirectory(prefix=f"{mode}-", dir=STATE_ROOT) as temp_name:
            temp = Path(temp_name)
            tree = temp / "garden"
            events = logs / f"{mode}_{stamp}.jsonl"
            errors = logs / f"{mode}_{stamp}.stderr.log"
            result_path = logs / f"{mode}_{stamp}.result.json"
            failed = True
            base = None
            try:
                tree = prepare_worktree(temp)
                if already_published(mode, tree):
                    result = {"status": "success", "reason": "already_published", "summary": "해당 발행 주기에 이미 글이 있습니다.", "public_url": "", "commit": ""}
                    save_status(mode, result)
                    print(json.dumps(result, ensure_ascii=False))
                    failed = False
                    return 0
                base = git("rev-parse", "HEAD", cwd=tree)
                command = claude_command(find_claude())
                returncode = run_agent(command, tree, prompt_for(mode, tree, base), events, errors)
                extract_structured_result(events, result_path, returncode, errors)
                result = load_result(result_path)
                verify_result(result, mode, tree, base, require_content_only=True)
                save_status(mode, result)
                print(json.dumps(result, ensure_ascii=False))
                failed = False
                return 0
            finally:
                try:
                    if failed:
                        save_failure_artifacts(tree, logs / f"{mode}_{stamp}.failure-artifacts", base)
                finally:
                    cleanup_worktree(tree)


def dry_run(mode: str) -> int:
    planned = Path("<LOCALAPPDATA>") / "robotics-garden-publish" / f"{mode}-<timestamp>" / "garden"
    print(json.dumps({"mode": mode, "command": claude_command(find_claude()), "prompt": prompt_for(mode, planned)}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("daily", "weekly"), default="daily")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--verify-content-only", action="store_true")
    parser.add_argument("--tree", type=Path)
    parser.add_argument("--base")
    args = parser.parse_args()
    try:
        if args.smoke:
            return smoke()
        if args.verify_content_only:
            if args.tree is None or not args.base:
                raise RuntimeError("--verify-content-only에는 --tree와 --base가 필요합니다")
            print(json.dumps(verify_content_only(args.tree.resolve(), args.base, args.mode), ensure_ascii=False, indent=2))
            return 0
        return dry_run(args.mode) if args.dry_run else execute(args.mode)
    except Exception as exc:  # 예약 작업에는 traceback 대신 한 줄 실패를 남긴다.
        failure = {"status": "failure", "reason": "runtime_failed", "summary": str(exc), "public_url": "", "commit": ""}
        save_status(args.mode, failure)
        print(f"garden_publish 실패: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
