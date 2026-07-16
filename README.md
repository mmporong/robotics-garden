# robotics-garden

로보틱스·피지컬 AI를 공부하며 쌓은 학습 노트와 외부 연구 정리를 발행하는 학습 가든이에요.

- 사이트: https://mmporong.github.io/robotics-garden/
- 기반: [Quartz v5](https://quartz.jzhao.xyz/) 포크 (커뮤니티 플러그인을 `quartz.config.yaml`로 구성)
- 배포: `main` 푸시 → GitHub Actions가 빌드해 GitHub Pages로 자동 배포

## 콘텐츠 구조

| 경로 | 내용 | 작성 방식 |
| --- | --- | --- |
| `content/physical-ai/` | 학습 노트 — 부트캠프에서 배우고 실습한 기록 | private 리포(physical-ai-lab)의 노트 중 `publish: true`만 `tools/publish_garden.py`가 동기화. **이 폴더는 매 동기화마다 통째로 재생성되므로 여기에서 직접 고치면 다음 동기화 때 사라진다** — 영구 수정은 소스 노트에 |
| `content/research/` | 리서치 — 외부 연구·논문·아티클을 읽고 소화한 정리 | 이 리포에 직접 작성 (동기화 대상 아님) |
| `content/assets/` | 글에 임베드하는 이미지·GIF | 동기화가 건드리지 않는 공용 폴더. 글에서 `../assets/파일명`으로 참조 |
| `content/index.md` | 홈 랜딩 피드의 마운트 지점 (`#home-feed`) | 실제 렌더는 `quartz/components/Head.tsx`의 스크립트가 담당 |

## 홈 랜딩 피드

홈(`/`)은 카드형 피드 페이지예요. `Head.tsx`의 스크립트가 `static/contentIndex.json`을 읽어 피처드 히어로, 카테고리 탭(전체·학습 노트·리서치), 아티클 리스트, 최근 글·태그 레일을 클라이언트에서 렌더해요. 썸네일은 각 글의 자동 생성 OG 이미지(`<슬러그>-og-image.webp`)를 그대로 써요. 새 글은 발행만 하면 피드에 자동으로 나타나요.

## 글쓰기 규칙

- 스타일 단일 기준: [STYLE_GUIDE.md](STYLE_GUIDE.md) — 토스체 존댓말, 학습 내용이 본문, 분량은 본문 약 1,200~3,600자 기준에 최대 1.5배까지
- 이미지 캡션: 이미지 바로 다음 줄(빈 줄 없이)에 `<em><span>설명</span><span class="cap-src">(출처: 제작자)</span></em>` — 항상 한 줄로 렌더되고 출처는 잘리지 않아요. 인용 이미지는 저작권법상 인용 요건(비평·연구 목적, 정당한 범위, 출처 명시)을 지켜요
- frontmatter 필수: `publish: true`, `title`, `date`, `tags`(실무 용어 5개 안팎), `description`

## 커스터마이징이 사는 곳 (배포 안전 영역)

배포는 `.quartz/` 플러그인을 매번 새로 받으므로, 커밋되는 곳만 배포에 반영돼요.

- `quartz.config.yaml` — 플러그인·테마 색상·탐색기(제목 physical-ai, 폴더 정렬)
- `quartz/styles/custom.scss` — 명판 시그니처, 탐색기 폴더 스크롤(3.5개 높이), 이미지 캡션, 홈 피드 스타일
- `quartz/components/Head.tsx` — 사이드바 프로필 주입, 홈 피드 렌더러

## 로컬 실행

```bash
npx quartz build --serve   # http://localhost:8080
```
