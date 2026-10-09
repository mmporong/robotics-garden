#!/usr/bin/env python3
"""가든 글의 조회수를 모아 정적 스냅샷과 시계열 기록으로 남긴다.

왜 필요한가 (2026-08-05 실측):
    홈 피드가 브라우저에서 글 100편의 조회수를 한꺼번에 조회하고 있었다.
    카운터 API가 rate limit을 걸어 100편 중 70편이 429, 24편이 404로 떨어졌고
    실패분은 전부 0으로 처리돼 인기순이 사실상 무의미했다. 동시성을 낮춰도
    시간당 총량 제한이라 안정되지 않는다(동시 1개에서도 429가 났다).
    그래서 수집을 브라우저에서 떼어내 여기로 옮긴다. 여기서는 시간을 들여
    백오프하며 확실히 모으고, 프론트엔드는 결과 파일 하나만 읽는다.

출력 둘:
    1) quartz/static/views.json  — 최신 스냅샷(홈 피드가 읽는다)
    2) data/views_history.jsonl  — 날짜별 누적(나중에 추이 확인용)

사용:
    python3 tools/collect_views.py            # 수집 후 두 파일 갱신
    python3 tools/collect_views.py --dry-run  # 파일을 쓰지 않고 결과만 출력
    python3 tools/collect_views.py --report   # 저장된 시계열을 표로 출력
    python3 tools/collect_views.py --rebuild  # API 호출 없이 저장된 월별 집계 재계산
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "public" / "static" / "contentIndex.json"
SNAPSHOT = ROOT / "quartz" / "static" / "views.json"
HISTORY = ROOT / "data" / "views_history.jsonl"

API = "https://abacus.jasoncameron.dev"
NS = "mmporong-robotics-garden"
CATS = ("physical-ai", "tech", "research", "insights")
KST = timezone(timedelta(hours=9))

# 429가 잦아 넉넉히 잡는다. 100편 기준 정상 수집에 3~6분.
BASE_DELAY = 0.35
MAX_RETRY = 6


def fnv(s: str) -> str:
    """홈 피드의 fnv 해시와 반드시 같아야 한다 (키가 어긋나면 전부 404)."""
    h = 2166136261
    for ch in s:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return ("0000000" + format(h, "x"))[-8:]


def fetch(slug: str) -> tuple[int, str]:
    """(조회수, 상태). 404는 '아직 방문 없음'이라 0으로 정상 처리한다."""
    url = f"{API}/get/{NS}/v-{fnv(slug)}"
    delay = BASE_DELAY
    for attempt in range(MAX_RETRY):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                value = json.loads(r.read()).get("value")
                if type(value) is not int or value < 0:
                    raise ValueError("유효한 조회수가 아니다")
                return value, "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 0, "new"
            if e.code == 429:
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
                continue
            return 0, f"http{e.code}"
        except Exception:
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
    return 0, "ratelimited"


def load_slugs() -> list[str]:
    if not INDEX.exists():
        sys.exit(f"contentIndex.json이 없다: {INDEX}\n가든에서 `npx quartz build`를 먼저 돌린다.")
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    return sorted(
        s for s in idx
        if s.split("/")[0] in CATS and not s.endswith("/index")
    )


def last_snapshot() -> dict[str, int]:
    """직전 스냅샷. 이번에 못 받은 글은 이 값을 유지해 0으로 깎이지 않게 한다."""
    if not SNAPSHOT.exists():
        return {}
    try:
        payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        views = payload["views"]
        if not isinstance(views, dict) or any(type(n) is not int or n < 0 for n in views.values()):
            raise ValueError("조회수 객체가 유효하지 않다")
        return views
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("기존 스냅샷을 읽을 수 없어 수집을 중단한다.") from exc


def collect() -> tuple[dict[str, int], dict[str, int]]:
    slugs = load_slugs()
    if not slugs:
        raise RuntimeError("수집 대상이 비어 있어 기존 조회수를 유지한다.")
    prev = last_snapshot()
    views: dict[str, int] = {}
    stats = {"ok": 0, "new": 0, "ratelimited": 0, "kept": 0}
    print(f"글 {len(slugs)}편 수집 시작 (429 백오프 포함, 몇 분 걸린다)")
    for i, slug in enumerate(slugs, 1):
        n, status = fetch(slug)
        if (status not in ("ok", "new") or (status == "new" and prev.get(slug, 0) > 0)) and slug in prev:
            # 실패를 0으로 덮으면 순위가 무너진다. 직전 값을 유지한다.
            n, status = prev[slug], "kept"
        views[slug] = n
        stats[status] = stats.get(status, 0) + 1
        if i % 20 == 0 or i == len(slugs):
            print(f"  {i}/{len(slugs)}  누적 {sum(views.values())}회")
        time.sleep(BASE_DELAY)
    if not stats["ok"] and not stats["new"]:
        raise RuntimeError("유효한 수집 결과가 없어 기존 스냅샷과 갱신 시각을 유지한다.")
    return views, stats


def monthly(views: dict[str, int], at: datetime, rows: list[dict]) -> dict:
    """KST 월별 양의 증가분. 일간 관측 사이의 방문 시각은 추정하지 않는다."""
    at = at.astimezone(KST)
    start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    samples = []
    for row in rows:
        stamp = datetime.fromisoformat(row["at"]).astimezone(KST)
        if stamp <= at:
            samples.append((stamp, row["views"]))
    samples.append((at, views))
    samples.sort(key=lambda sample: sample[0])
    previous: dict[str, int] = {}
    gains = dict.fromkeys(views, 0)
    baseline_at = None
    for stamp, counts in samples:
        if stamp < start:
            baseline_at = stamp.isoformat(timespec="seconds")
        for slug, count in counts.items():
            if type(count) is not int or count < 0:
                raise ValueError(f"수집 기록의 조회수가 유효하지 않다: {slug}")
            if stamp >= start and slug in gains:
                if slug in previous:
                    # 카운터 감소는 방문 취소로 계산하지 않는다. 이후 증가는 새 기준에서 잰다.
                    gains[slug] += max(0, count - previous[slug])
                else:
                    published = re.search(r"/(\d{4}-\d{2}-\d{2})", slug)
                    if published and start.date().isoformat() <= published[1] <= at.date().isoformat():
                        gains[slug] += count
            previous[slug] = count
    return {
        "period": at.strftime("%Y-%m"),
        "timezone": "Asia/Seoul",
        "baseline_at": baseline_at,
        "total": sum(gains.values()),
        "views": gains,
    }


def history_rows() -> list[dict]:
    if not HISTORY.exists():
        return []
    return [json.loads(line) for line in HISTORY.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_snapshot(payload: dict) -> None:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=SNAPSHOT.parent,
                                         prefix=f".{SNAPSHOT.name}.", delete=False) as f:
            temporary = Path(f.name)
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, SNAPSHOT)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def rebuild(dry_run: bool = False) -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    payload["monthly"] = monthly(payload["views"], datetime.fromisoformat(payload["updated"]), history_rows())
    if not dry_run:
        save_snapshot(payload)
    print(f"월별 집계 {payload['monthly']['period']}: {payload['monthly']['total']}회 (수집 시각·이력 보존)")


def write(views: dict[str, int], stats: dict[str, int]) -> None:
    now = datetime.now(KST)
    payload = {"updated": now.isoformat(timespec="seconds"), "total": sum(views.values()),
               "views": views, "stats": stats, "monthly": monthly(views, now, history_rows())}
    save_snapshot(payload)
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(
            {"date": now.strftime("%Y-%m-%d"), "at": now.isoformat(timespec="seconds"),
             "total": sum(views.values()), "stats": stats, "views": views},
            ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"\n스냅샷 → {SNAPSHOT}")
    print(f"시계열 → {HISTORY} (누적 {sum(1 for _ in HISTORY.open(encoding='utf-8'))}회차)")


def report() -> None:
    if not HISTORY.exists():
        sys.exit("아직 수집 기록이 없다.")
    rows = [json.loads(l) for l in HISTORY.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"수집 회차 {len(rows)}회\n")
    print(f"{'날짜':<12}{'합계':>7}{'증가':>7}   수집 상태")
    prev_total = None
    for r in rows:
        d = f"+{r['total']-prev_total}" if prev_total is not None else "-"
        st = r.get("stats", {})
        print(f"{r['date']:<12}{r['total']:>7}{d:>7}   ok {st.get('ok',0)} · 신규 {st.get('new',0)} · 실패 {st.get('ratelimited',0)}")
        prev_total = r["total"]
    latest = rows[-1]["views"]
    top = sorted(latest.items(), key=lambda kv: -kv[1])[:15]
    print(f"\n조회수 상위 15편 ({rows[-1]['date']} 기준)")
    for slug, n in top:
        if n:
            print(f"  {n:>5}  {slug.split('/')[-1][:52]}")
    if len(rows) >= 2:
        before = rows[-2]["views"]
        gain = sorted(((s, v - before.get(s, 0)) for s, v in latest.items()), key=lambda kv: -kv[1])[:10]
        print(f"\n직전 회차 대비 증가 상위")
        for slug, g in gain:
            if g > 0:
                print(f"  +{g:>4}  {slug.split('/')[-1][:52]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 출력")
    ap.add_argument("--report", action="store_true", help="저장된 시계열을 표로 출력")
    ap.add_argument("--rebuild", action="store_true", help="API 호출 없이 저장된 월별 집계 재계산")
    a = ap.parse_args()
    if a.report:
        return report()
    if a.rebuild:
        return rebuild(a.dry_run)
    views, stats = collect()
    ranked = sorted(views.items(), key=lambda kv: -kv[1])
    print(f"\n합계 {sum(views.values())}회 · "
          f"성공 {stats.get('ok',0)} · 신규 {stats.get('new',0)} · "
          f"유지 {stats.get('kept',0)} · 실패 {stats.get('ratelimited',0)}")
    print("상위 10편:")
    for slug, n in ranked[:10]:
        print(f"  {n:>5}  {slug.split('/')[-1][:52]}")
    if a.dry_run:
        print("\n--dry-run: 파일을 쓰지 않았다.")
        return
    write(views, stats)


if __name__ == "__main__":
    main()
