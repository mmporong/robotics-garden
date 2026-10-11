import assert from "node:assert/strict"
import { describe, test } from "node:test"
import { countTopicPosts, paginationItems, topicUrl } from "./home-feed-controls"

describe("home feed pagination", () => {
  test("앞·가운데·마지막에서 현재 페이지와 양끝을 유지한다", () => {
    assert.deepEqual(paginationItems(1, 19), [1, 2, 3, "gap", 19])
    assert.deepEqual(paginationItems(9, 19), [1, "gap", 8, 9, 10, "gap", 19])
    assert.deepEqual(paginationItems(19, 19), [1, "gap", 17, 18, 19])
  })

  test("빈 목록과 짧은 목록에는 불필요한 생략을 넣지 않는다", () => {
    assert.deepEqual(paginationItems(1, 0), [])
    assert.deepEqual(paginationItems(1, 1), [1])
    assert.deepEqual(paginationItems(4, 7), [1, 2, 3, 4, 5, 6, 7])
  })

  test("모든 위치에서 일곱 항목 이하로 유효한 페이지를 보여 준다", () => {
    for (const pages of [8, 19, 100]) {
      for (let page = 1; page <= pages; page++) {
        const items = paginationItems(page, pages)
        const numbers = items.filter((item): item is number => typeof item === "number")
        assert.ok(items.length <= 7)
        assert.equal(numbers[0], 1)
        assert.equal(numbers.at(-1), pages)
        assert.ok(numbers.includes(page))
        assert.equal(numbers.length, new Set(numbers).size)
        assert.ok(numbers.every((number) => number >= 1 && number <= pages))
        assert.deepEqual(
          numbers,
          [...numbers].sort((a, b) => a - b),
        )
      }
    }
  })
})

describe("home feed topic links", () => {
  test("두 번째 태그와 계층 태그를 포함해 글당 한 번 센다", () => {
    const counts = countTopicPosts([
      { tags: ["c++", "ros2", "ros2"] },
      { tags: ["모방학습", "ros2", "제어/mpc"] },
      { tags: ["제어", "제어/mpc"] },
    ])
    assert.equal(counts["c++"], 1)
    assert.equal(counts.ros2, 2)
    assert.equal(counts["제어"], 2)
    assert.equal(counts["제어/mpc"], 2)
  })

  test("기호와 한글을 보존하면서 경로·쿼리·해시와 구분한다", () => {
    assert.equal(topicUrl("c++"), "tags/c%2B%2B")
    assert.equal(topicUrl("ros2"), "tags/ros2")
    assert.equal(topicUrl("제어/mpc"), "tags/%EC%A0%9C%EC%96%B4/mpc")
    assert.equal(topicUrl("a&b?#"), "tags/a%26b%3F%23")
  })
})
