import { getAllSegmentPrefixes } from "../../util/path"

export type PaginationItem = number | "gap"

export function publicationDate(slug: string, indexedDate?: unknown): string {
  if (typeof indexedDate === "string" && /^\d{4}-\d{2}-\d{2}$/.test(indexedDate)) {
    return indexedDate
  }
  return slug.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? ""
}

export function paginationItems(page: number, pages: number): PaginationItem[] {
  if (pages <= 0) return []
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1)

  const current = Math.min(pages, Math.max(1, page))
  const visible = new Set([1, pages, current - 1, current, current + 1])
  if (current === 1) visible.add(3)
  if (current === pages) visible.add(pages - 2)
  const numbers = [...visible]
    .filter((number) => number >= 1 && number <= pages)
    .sort((a, b) => a - b)
  const items: PaginationItem[] = []
  for (const number of numbers) {
    const previous = items.at(-1)
    if (typeof previous === "number") {
      if (number - previous === 2) items.push(previous + 1)
      else if (number - previous > 2) items.push("gap")
    }
    items.push(number)
  }
  return items
}

export function countTopicPosts(posts: Array<{ tags: string[] }>): Record<string, number> {
  const counts: Record<string, number> = Object.create(null)
  for (const post of posts) {
    const tags = new Set(post.tags.flatMap(getAllSegmentPrefixes))
    for (const tag of tags) counts[tag] = (counts[tag] ?? 0) + 1
  }
  return counts
}

export function topicUrl(tag: string): string {
  return "tags/" + tag.split("/").map(encodeURIComponent).join("/")
}
