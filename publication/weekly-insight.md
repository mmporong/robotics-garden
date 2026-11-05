# 주간 종합 인사이트 발행 계약

매주 한 편, 직전 주간 인사이트 뒤에 발행된 시뮬레이션 리서치를 종합한다.

1. `content/insights`의 가장 최근 글 이후에 발행된 `content/research`를 읽는다. 검증 가능한 새 재료가 두 편 미만이면 `hold/insufficient_material`로 끝낸다.
2. 여러 글을 차례로 요약하지 않는다. 두 편 이상의 근거가 만나는 문제 하나를 정하고, 조건 차이·반례·적용 경계를 비교해 하나의 판단으로 묶는다.
3. 서로 다른 분모·과제·시뮬레이터의 수치를 더하거나 평균 내지 않는다. 각 수치의 조건과 한계를 같이 쓴다.
4. 본문 논지를 나눠 설명하는 미디어를 두 개 이상 사용한다. 기존 리서치 글의 원자료를 재사용할 때도 출처와 라이선스를 캡션에서 보존한다.
5. frontmatter에 `주간인사이트`와 시뮬레이션 관련 실무 태그를 넣고, 본문 끝 출처 블록에는 실제 종합한 대표 원문 URL을 각각 둔다.
6. 어려운 용어의 첫 등장 설명, 공개 안전, denylist, 링크, 미디어, 색인, 렌더링은 publish 스킬의 발행 게이트를 모두 통과한다.
7. `npm test`와 `npx quartz build`를 통과시키고 변경 파일만 커밋해 `origin main`에 push한 뒤 공개 URL에서 제목과 고유 문장을 확인한다.

자료 부족만 정상 보류다. 도구·네트워크·검증·push·배포 문제는 failure다.

## 브라우저 호스트가 없을 때

CUA browser host unavailable이면 브라우저 검증을 통과한 것처럼 기록하지 않는다. 작성 패스와 별도의 검증 패스를 유지하면서 새 인사이트 Markdown 한 편과 그 글이 참조하는 PNG·JPG·JPEG·GIF·WebP·AVIF 정적 이미지 추가만 허용한다. 원문이 제공한 SVG는 XML 검사에서 스크립트·애니메이션·링크·이벤트·외부 URL이 하나도 없는 정적 원그림일 때만 허용한다. 기존 글·기존 자산·Quartz·설정·패키지·CSS·JavaScript를 바꾸지 않고 script·iframe·object·embed·동영상·새 도식 HTML을 넣지 않는다.

두 편 이상의 시뮬레이션 리서치 종합, denylist, 어려운 용어의 첫 등장 설명, 이미지 실제 디코딩, 라이선스와 캡션 출처, `npm test`, `npx quartz build`, 빌드 HTML, 공개 HTML과 공개 미디어 응답 검증은 그대로 수행한다. 검증 기록은 worktree 밖에 둔다. success summary에는 `브라우저 상호작용 검증 미실행: CUA browser host unavailable`과 `콘텐츠 전용 게이트 PASS`를 모두 적는다.
