import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import test, { describe } from "node:test"
import { classifyReference, extractSourceUrl, referenceDate, resolveReferenceKind } from "./referenceIndex"

describe("reference index", () => {
  test("원고 파일명보다 한국 시간의 실제 발행일을 우선한다", () => {
    const slug = "research/2026-10-17_socialnav_sarl"
    assert.equal(referenceDate("2026-10-18T08:00:00+09:00", slug), "2026-10-18")
    assert.equal(referenceDate(new Date("2026-10-17T23:00:00Z"), slug), "2026-10-18")
    assert.equal(referenceDate(undefined, slug), "2026-10-17")
    assert.equal(referenceDate("invalid", slug), "2026-10-17")
  })

  test("마크다운 링크와 그대로 쓴 URL에서 원문 주소를 추출한다", () => {
    assert.equal(
      extractSourceUrl(
        "본문\n\n<!-- src-block -->\n출처 — [논문](https://arxiv.org/abs/2304.13705) · 그림 인용",
      ),
      "https://arxiv.org/abs/2304.13705",
    )
    assert.equal(
      extractSourceUrl("본문\n\n<!-- src-block -->\n출처 — https://example.org/project/"),
      "https://example.org/project/",
    )
    assert.equal(
      extractSourceUrl(
        "본문\n\n<!-- src-block -->\n출처 — [논문](https://example.org/paper_(final).pdf) · 원문",
      ),
      "https://example.org/paper_(final).pdf",
    )
  })

  test("대표 원문이 없거나 둘 이상이면 색인하지 않는다", () => {
    assert.equal(extractSourceUrl("본문만 있음"), undefined)
    assert.equal(
      extractSourceUrl(
        "<!-- src-block -->\n출처 — https://example.org/one · https://example.org/two",
      ),
      undefined,
    )
  })

  test("논문 주소와 관련 자료 주소를 구분한다", () => {
    assert.equal(classifyReference("https://arxiv.org/abs/2608.29100"), "paper")
    assert.equal(classifyReference("https://example.org/paper.pdf"), "paper")
    assert.equal(classifyReference("https://github.com/example/project"), "resource")
    assert.equal(resolveReferenceKind("paper", "https://example.org/article"), "paper")
    assert.equal(resolveReferenceKind("resource", "https://arxiv.org/abs/2608.29100"), "resource")
  })

  test("현재 리서치 글은 모두 하나의 출처 URL을 제공한다", () => {
    const researchDir = path.resolve("content/research")
    const articles = fs
      .readdirSync(researchDir)
      .filter((name) => name.endsWith(".md") && name !== "index.md")

    assert.ok(articles.length > 0)
    const missing = articles.filter((name) => {
      const markdown = fs.readFileSync(path.join(researchDir, name), "utf8")
      return !extractSourceUrl(markdown)
    })

    assert.deepEqual(missing, [])
  })
})
