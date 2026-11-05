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


def find_codex() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    candidates = []
    if local:
        candidates.append(Path(local) / "Programs/OpenAI/Codex/bin/codex.exe")
    found = shutil.which("codex.exe") or shutil.which("codex.cmd") or shutil.which("codex")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("Codex CLI를 찾지 못했습니다")


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
    return f"""$publish {label}

무인 자동 발행이다. 사용자 확인을 기다리거나 외부 메시지·알림을 보내지 말고 성공·보류·실패 중 하나가 확정될 때까지 진행한다.
현재 Codex publish 스킬과 {Path.home() / '.codex/skills/publish/SKILL.md'} 전체, {ROOT / 'AGENTS.md'}와 {tree / 'STYLE_GUIDE.md'}를 읽고 따른다.

Windows 발행용 최신 origin/main 격리 worktree는 다음 경로다.
{tree}

이 경로 안에서만 작성·검증·커밋·push한다. physical-ai-lab과 메인 체크아웃을 수정하지 않는다. worktree·clone을 더 만들지 않고 npm ci와 플러그인 설치를 실행하지 않는다. 준비된 node_modules와 .quartz를 사용한다.
전역 Codex 모델·reasoning effort·설정을 바꾸지 않는다.

브라우저 호스트를 사용할 수 있으면 publish 스킬의 기존 브라우저 상호작용 게이트를 수행한다. CUA browser host unavailable이면 브라우저 PASS를 만들지 말고 콘텐츠 전용 모드로 전환한다. 이때 작성 패스와 검증 패스를 분리하고, push 전에 아래 명령이 PASS해야 한다.
python "{ROOT / 'tools/garden_publish.py'}" --verify-content-only --tree "{tree}" --base "{base}" --mode {mode}

콘텐츠 전용 모드에서는 새 Markdown 한 편과 그 글이 참조하는 비상호작용 정적 미디어만 추가할 수 있다. 래스터 이미지와 실행 요소·이벤트·외부 참조가 없는 원문 정적 SVG만 허용한다. 기존 콘텐츠·기존 자산·Quartz·설정·패키지·CSS·JavaScript는 수정하지 않고, script·iframe·object·embed·새 도식 HTML을 넣지 않는다. audit_terms 결과 같은 검증 사이드카는 worktree 밖 PUBLISH_TMP_ROOT 또는 현재 실행의 로그 경로에 둔다. 브라우저 상호작용을 실행하지 못한 이유와 콘텐츠 전용 게이트 PASS를 success summary에 명시한다.

아래 모드 계약을 모두 적용한다.

{contract}

새 글을 발행한 성공이면 status=success, reason=published, 실제 공개 URL과 origin/main에 push한 커밋 SHA를 기록한다. push 직전 다른 호스트가 같은 주기의 글을 먼저 발행한 것을 확인했다면 status=success, reason=already_published로 끝내고 URL과 commit을 비운다. 정상 보류와 실패도 URL과 commit을 비우며, 실제 reason을 쓴다. 최종 응답은 지정된 JSON schema만 따른다.
"""


def codex_command(codex: Path, tree: Path, result: Path) -> list[str]:
    return [
        str(codex), "exec", "--ephemeral",
        "-c", 'approval_policy="never"', "--sandbox", "danger-full-access",
        "--cd", str(tree), "--output-schema", str(SCHEMA),
        "--output-last-message", str(result), "--json", "-",
    ]


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
        raise RuntimeError(f"Codex 결과 JSON을 읽지 못했습니다: {exc}") from exc
    required = {"status", "reason", "summary", "public_url", "commit"}
    if not isinstance(value, dict) or set(value) != required or not isinstance(value["summary"], str) or not value["summary"].strip():
        raise RuntimeError("Codex 결과 계약이 맞지 않습니다")
    return value


def run_codex(command: list[str], tree: Path, prompt: str, events: Path, errors: Path,
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
            raise RuntimeError("Codex 실행이 5시간 제한을 넘었습니다")
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


def postpush_content_gate(summary: str, tree: Path, base: str, mode: str) -> dict[str, object] | None:
    browser_verified = "브라우저 상호작용 검증: PASS" in summary
    content_only = "브라우저 상호작용 검증 미실행:" in summary and "콘텐츠 전용 게이트 PASS" in summary
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


def verify_result(result: dict[str, object], mode: str, tree: Path, base: str | None = None) -> None:
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
    gate = postpush_content_gate(str(result["summary"]), tree, base, mode)
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


def smoke() -> int:
    codex = find_codex()
    completed = run(
        [str(codex), "exec", "--ephemeral", "--sandbox", "read-only", "--cd", str(ROOT), "-"],
        input_text="읽기 전용 연결 점검이다. 파일·Git·외부 서비스를 변경하지 말고 AUTOMATION_SMOKE_OK만 출력한다.",
    )
    if "AUTOMATION_SMOKE_OK" not in completed.stdout:
        raise RuntimeError("Codex 스모크 응답이 맞지 않습니다")
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
                command = codex_command(find_codex(), tree, result_path)
                returncode = run_codex(command, tree, prompt_for(mode, tree, base), events, errors)
                if returncode != 0:
                    tail = errors.read_text(encoding="utf-8", errors="replace")[-1200:]
                    raise RuntimeError(f"Codex 실행 실패(exit {returncode}): {tail}")
                result = load_result(result_path)
                verify_result(result, mode, tree, base)
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
    codex = find_codex()
    print(json.dumps({"mode": mode, "command": codex_command(codex, planned, Path("<result.json>")), "prompt": prompt_for(mode, planned)}, ensure_ascii=False, indent=2))
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
