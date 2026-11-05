# 일간 시뮬레이션 리서치 발행 계약

하루에 한 편만 발행한다. 주제는 로봇 시뮬레이션으로 제한한다.

허용 범위는 시뮬레이터, 합성 데이터, 디지털 트윈, 물리 엔진, 시뮬레이션 기반 학습·평가·검증, Sim-to-Real이다. Isaac Sim, Isaac Lab, NVIDIA Cosmos, OpenUSD와 연결되는 NVIDIA 공식 기술 자료·문서·프로젝트도 원문 후보로 사용할 수 있다. 제품 소식만 옮기거나 시뮬레이션과 관계없는 로봇 조작·내비게이션 논문은 제외한다.

1. 최신 논문과 공식 원문을 웹에서 조사하고 `content/research` 전체의 대표 원문 URL·제목·핵심 논지와 중복되지 않는 후보 하나를 고른다.
2. 논문이면 논문 원문을 대표 출처로 쓴다. 공식 기술 자료를 고르면 NVIDIA·OpenUSD의 공식 문서나 프로젝트 페이지를 대표 출처로 쓴다. 블로그 재인용과 검색 결과 페이지는 대표 출처로 쓰지 않는다.
3. 본문은 frontmatter와 HTML 태그를 제외하고 6,000~10,800자를 실효 범위로 삼는다. 원리가 요구하면 16,200자까지 허용한다. 정의 → 작동 원리 → 검증 조건과 수치 → 실패 조건과 한계 → 시뮬레이션 작업에 적용할 판단 순서로 쓴다.
   frontmatter 태그에는 `로봇시뮬레이션`과 Isaac Sim·Isaac Lab·Cosmos·OpenUSD 등 실제 글의 대상 기술을 넣는다.
4. 본문 끝 `<!-- src-block -->` 뒤에는 `출처 — URL` 형식으로 대표 원문 URL을 정확히 하나 둔다.
5. 원문의 핵심 그림·실험 프레임·공식 데모 등 논지를 뒷받침하는 미디어를 하나 이상 사용하고 재배포 조건과 캡션 출처를 확인한다. 새 설명 도식이 필요하면 publish 스킬의 archify 계약을 따른다.
6. 어려운 용어는 첫 등장 한 번에만 쉬운 한국어 `<abbr title="…">` 설명을 붙이고 `$HOME/.codex/skills/publish/scripts/audit_terms.py`로 후보를 전부 판정한다.
7. 수행하지 않은 실습·측정·경험을 만들지 않는다. 공식 자료의 수치와 기능 범위를 검증하고, 마케팅 표현을 성능 보장으로 넓히지 않는다.
8. `npm test`와 `npx quartz build`를 통과시키고 생성된 자료 색인에서 새 글의 slug와 대표 원문을 확인한다. 변경 파일만 스테이징해 한글 Conventional Commit으로 커밋하고 `origin main`에 push한다.
   push 직전에 `git fetch origin main`을 실행한다. 원격에 오늘 날짜의 `publish: true` 리서치가 생겼다면 새 글을 push하지 않고 `success/already_published`로 끝낸다. 다른 원격 커밋 때문에 rebase가 필요하면 최신 `origin/main`에 재배치한 뒤 오늘 글을 다시 확인한다. 이 자동화가 시작될 때부터 있던 글을 수정하거나 삭제하지 않는다.
9. GitHub Pages 공개 URL에서 제목과 고유 문장을 확인한다. 후보가 없을 때만 `hold/no_candidate`, 작성·검증·push·배포 문제가 생기면 해당 failure로 끝낸다.

## 브라우저 호스트가 없을 때

CUA browser host unavailable이면 브라우저 검증을 통과한 것처럼 기록하지 않는다. 작성 패스와 별도의 검증 패스를 유지하면서 새 리서치 Markdown 한 편과 그 글이 참조하는 PNG·JPG·JPEG·GIF·WebP·AVIF 정적 이미지 추가만 허용한다. 원문이 제공한 SVG는 XML 검사에서 스크립트·애니메이션·링크·이벤트·외부 URL이 하나도 없는 정적 원그림일 때만 허용한다. 기존 글·기존 자산·Quartz·설정·패키지·CSS·JavaScript를 바꾸지 않고 script·iframe·object·embed·동영상·새 도식 HTML을 넣지 않는다.

본문 분량, 대표 원문 하나, 중복, denylist, 어려운 용어의 첫 등장 설명, 이미지 실제 디코딩, 라이선스와 캡션 출처, `npm test`, `npx quartz build`, 빌드 HTML, `references.json`, 공개 HTML과 공개 미디어 응답 검증은 그대로 수행한다. 검증 기록은 worktree 밖에 둔다. success summary에는 `브라우저 상호작용 검증 미실행: CUA browser host unavailable`과 `콘텐츠 전용 게이트 PASS`를 모두 적는다.

`publication/socialnav_queue.json`의 이전 예약 큐는 이번 시뮬레이션 일간 흐름의 입력이 아니다.
