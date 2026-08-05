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
"""
from __future__ import annotations

import argparse
import json
import sys
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
CATS = ("physical-ai", "research", "insights")
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
                return int(json.loads(r.read()).get("value") or 0), "ok"
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
        return json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("views", {})
    except Exception:
        return {}


def collect() -> tuple[dict[str, int], dict[str, int]]:
    slugs = load_slugs()
    prev = last_snapshot()
    views: dict[str, int] = {}
    stats = {"ok": 0, "new": 0, "ratelimited": 0, "kept": 0}
    print(f"글 {len(slugs)}편 수집 시작 (429 백오프 포함, 몇 분 걸린다)")
    for i, slug in enumerate(slugs, 1):
        n, status = fetch(slug)
        if status == "ratelimited" and slug in prev:
            # 실패를 0으로 덮으면 순위가 무너진다. 직전 값을 유지한다.
            n, status = prev[slug], "kept"
        views[slug] = n
        stats[status] = stats.get(status, 0) + 1
        if i % 20 == 0 or i == len(slugs):
            print(f"  {i}/{len(slugs)}  누적 {sum(views.values())}회")
        time.sleep(BASE_DELAY)
    return views, stats


def write(views: dict[str, int], stats: dict[str, int]) -> None:
    now = datetime.now(KST)
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(
        json.dumps(
            {"updated": now.isoformat(timespec="seconds"), "total": sum(views.values()), "views": views},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
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
    a = ap.parse_args()
    if a.report:
        return report()
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
