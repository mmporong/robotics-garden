import fs from "node:fs/promises"
import path from "node:path"
import { BuildCtx } from "../../util/ctx"
import { FilePath, joinSegments } from "../../util/path"
import { ProcessedContent } from "../vfile"
import { QuartzEmitterPlugin } from "../types"

export type ReferenceKind = "paper" | "resource"

export type ReferenceRecord = {
  slug: string
  title: string
  date: string
  tags: string[]
  sourceUrl: string
  sourceHost: string
  kind: ReferenceKind
}

export type ReferenceIndexPayload = {
  version: 1
  total: number
  counts: Record<ReferenceKind, number>
  references: ReferenceRecord[]
}

const SOURCE_MARKER = "<!-- src-block -->"
const SOURCE_LINE = /^출처\s*—\s*(.+)$/m
const MARKDOWN_URL = /\[[^\]]*\]\((https?:\/\/.+)\)(?=\s*(?:·|$))/i
const BARE_URL = /https?:\/\/[^\s<>]+/i

function stripUrlPunctuation(url: string): string {
  return url.replace(/[.,;:!?，。；：！？·]+$/u, "")
}

export function extractSourceUrl(markdown: string): string | undefined {
  const markerAt = markdown.lastIndexOf(SOURCE_MARKER)
  if (markerAt < 0) return undefined

  const sourceLine = markdown.slice(markerAt + SOURCE_MARKER.length).match(SOURCE_LINE)?.[1]
  if (!sourceLine) return undefined

  const urls = sourceLine.match(new RegExp(BARE_URL.source, "gi")) ?? []
  if (urls.length !== 1) return undefined

  const url = sourceLine.match(MARKDOWN_URL)?.[1] ?? urls[0]
  return url ? stripUrlPunctuation(url) : undefined
}

export function classifyReference(sourceUrl: string): ReferenceKind {
  const url = new URL(sourceUrl)
  const host = url.hostname.replace(/^www\./, "").toLowerCase()
  const paperHosts = new Set([
    "arxiv.org",
    "aclanthology.org",
    "dl.acm.org",
    "doi.org",
    "dx.doi.org",
    "ieeexplore.ieee.org",
    "link.springer.com",
    "nature.com",
    "openreview.net",
    "pubmed.ncbi.nlm.nih.gov",
    "roboticsproceedings.org",
    "proceedings.mlr.press",
    "openaccess.thecvf.com",
    "sciencedirect.com",
  ])

  if (paperHosts.has(host) || /\.pdf$/i.test(url.pathname)) return "paper"
  return "resource"
}

export function resolveReferenceKind(value: unknown, sourceUrl: string): ReferenceKind {
  return value === "paper" || value === "resource" ? value : classifyReference(sourceUrl)
}

export function sourceHost(sourceUrl: string): string {
  return new URL(sourceUrl).hostname.replace(/^www\./, "")
}

function dateFromSlug(slug: string): string {
  return slug.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? ""
}

function normalizeTags(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((tag): tag is string => typeof tag === "string") : []
}

export function collectReferenceRecords(content: ProcessedContent[]): ReferenceRecord[] {
  const references: ReferenceRecord[] = []

  for (const [, file] of content) {
    const slug = String(file.data.slug ?? "")
    if (!slug.startsWith("research/") || slug === "research/index") continue

    const sourceUrl = extractSourceUrl(file.value.toString())
    if (!sourceUrl) {
      throw new Error(`${file.data.relativePath}: 출처 블록에서 원문 URL을 찾지 못했습니다`)
    }

    const frontmatter = (file.data.frontmatter ?? {}) as Record<string, unknown>
    references.push({
      slug,
      title: typeof frontmatter.title === "string" ? frontmatter.title : slug.split("/").at(-1)!,
      date: dateFromSlug(slug),
      tags: normalizeTags(frontmatter.tags),
      sourceUrl,
      sourceHost: sourceHost(sourceUrl),
      kind: resolveReferenceKind(frontmatter.referenceKind, sourceUrl),
    })
  }

  return references.sort(
    (left, right) => right.date.localeCompare(left.date) || right.slug.localeCompare(left.slug),
  )
}

export function makeReferenceIndex(content: ProcessedContent[]): ReferenceIndexPayload {
  const references = collectReferenceRecords(content)
  return {
    version: 1,
    total: references.length,
    counts: {
      paper: references.filter((reference) => reference.kind === "paper").length,
      resource: references.filter((reference) => reference.kind === "resource").length,
    },
    references,
  }
}

async function writeReferenceIndex(
  ctx: BuildCtx,
  content: ProcessedContent[],
): Promise<FilePath[]> {
  const relativePath = joinSegments("static", "references.json") as FilePath
  const outputPath = path.join(ctx.argv.output, relativePath)
  await fs.mkdir(path.dirname(outputPath), { recursive: true })
  await fs.writeFile(outputPath, JSON.stringify(makeReferenceIndex(content)), "utf8")
  return [relativePath]
}

export const ReferenceIndex: QuartzEmitterPlugin = () => ({
  name: "ReferenceIndex",
  emit: (ctx, content) => writeReferenceIndex(ctx, content),
  partialEmit: (ctx, content) => writeReferenceIndex(ctx, content),
})
