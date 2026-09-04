import assert from "node:assert/strict"
import test, { describe } from "node:test"
import { articleUrl, resolveReferenceIndexUrl } from "./reference-library-path"

describe("reference library paths", () => {
  test("루트 배포의 색인과 해설 주소를 만든다", () => {
    const indexUrl = resolveReferenceIndexUrl("", "http://localhost:8080")

    assert.equal(indexUrl.toString(), "http://localhost:8080/static/references.json")
    assert.equal(articleUrl(indexUrl, "research/example"), "http://localhost:8080/research/example")
  })

  test("서브경로 SPA 이동에서도 사이트 안의 색인과 해설 주소를 유지한다", () => {
    const indexUrl = resolveReferenceIndexUrl("/robotics-garden", "https://example.com")

    assert.equal(indexUrl.toString(), "https://example.com/robotics-garden/static/references.json")
    assert.equal(
      articleUrl(indexUrl, "research/example"),
      "https://example.com/robotics-garden/research/example",
    )
  })
})
