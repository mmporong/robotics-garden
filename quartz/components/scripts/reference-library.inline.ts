import { articleUrl, resolveReferenceIndexUrl } from "./reference-library-path"

type ReferenceKind = "paper" | "resource"

type ReferenceRecord = {
  slug: string
  title: string
  date: string
  tags: string[]
  sourceUrl: string
  sourceHost: string
  kind: ReferenceKind
}

type ReferenceIndexPayload = {
  version: 1
  total: number
  counts: Record<ReferenceKind, number>
  references: ReferenceRecord[]
}

const PAGE_SIZE = 12
const KIND_LABEL: Record<ReferenceKind, string> = {
  paper: "논문·학술자료",
  resource: "프로젝트·관련자료",
}

function element<K extends keyof HTMLElementTagNameMap>(
  tagName: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tagName)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text
  return node
}

function referenceCard(reference: ReferenceRecord, indexUrl: URL): HTMLElement {
  const card = element("article", "rl-card")
  const meta = element("div", "rl-meta")
  meta.append(
    element("span", `rl-kind rl-kind-${reference.kind}`, KIND_LABEL[reference.kind]),
    element("time", "rl-date", reference.date.replaceAll("-", ". ") + "."),
  )

  const title = element("a", "rl-title", reference.title)
  title.href = articleUrl(indexUrl, reference.slug)
  title.classList.add("internal")

  const tags = element("div", "rl-tags")
  for (const tag of reference.tags.slice(0, 3)) tags.append(element("span", "rl-tag", tag))

  const links = element("div", "rl-links")
  const source = element("a", "rl-source", `원문 · ${reference.sourceHost}`)
  source.href = reference.sourceUrl
  source.target = "_blank"
  source.rel = "noopener noreferrer"
  source.dataset.noPopover = "true"
  const summary = element("a", "rl-summary", "해설 읽기")
  summary.href = articleUrl(indexUrl, reference.slug)
  summary.classList.add("internal")
  links.append(source, summary)

  card.append(meta, title, tags, links)
  return card
}

async function buildReferenceLibrary() {
  const root = document.getElementById("reference-library")
  if (!root || root.dataset.ready === "true") return
  root.dataset.ready = "true"

  const indexUrl = resolveReferenceIndexUrl(document.body.dataset.basepath ?? "", location.origin)

  try {
    const response = await fetch(indexUrl)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const payload = (await response.json()) as ReferenceIndexPayload

    let selected: "all" | ReferenceKind = "all"
    let visible = PAGE_SIZE
    let query = ""

    const controls = element("div", "rl-controls")
    const search = element("input", "rl-search")
    search.type = "search"
    search.placeholder = "제목·태그·출처 검색"
    search.setAttribute("aria-label", "논문과 참고자료 검색")
    const filters = element("div", "rl-filters")
    filters.setAttribute("role", "group")
    filters.setAttribute("aria-label", "자료 종류")
    const resultCount = element("p", "rl-count")
    resultCount.setAttribute("role", "status")
    resultCount.setAttribute("aria-live", "polite")
    resultCount.setAttribute("aria-atomic", "true")
    const list = element("div", "rl-list")
    const more = element("button", "rl-more")
    more.type = "button"

    const matches = () => {
      const normalized = query.trim().toLocaleLowerCase("ko")
      return payload.references.filter((reference) => {
        if (selected !== "all" && reference.kind !== selected) return false
        if (!normalized) return true
        return [reference.title, reference.sourceHost, ...reference.tags]
          .join(" ")
          .toLocaleLowerCase("ko")
          .includes(normalized)
      })
    }

    const render = () => {
      const filtered = matches()
      const cards = filtered.slice(0, visible).map((item) => referenceCard(item, indexUrl))
      list.replaceChildren(
        ...(cards.length > 0
          ? cards
          : [element("p", "rl-empty", "검색 조건에 맞는 자료가 없어요.")]),
      )
      resultCount.textContent = `전체 ${payload.total}건 중 ${filtered.length}건`

      const remaining = filtered.length - visible
      more.hidden = remaining <= 0
      more.textContent = remaining > 0 ? `더 보기 (${remaining}건 남음)` : ""
    }

    const filterOptions: Array<["all" | ReferenceKind, string, number]> = [
      ["all", "전체", payload.total],
      ["paper", KIND_LABEL.paper, payload.counts.paper],
      ["resource", KIND_LABEL.resource, payload.counts.resource],
    ]
    for (const [kind, label, count] of filterOptions) {
      const button = element(
        "button",
        `rl-filter${kind === "all" ? " active" : ""}`,
        `${label} ${count}`,
      )
      button.type = "button"
      button.dataset.kind = kind
      button.setAttribute("aria-pressed", kind === "all" ? "true" : "false")
      button.addEventListener("click", () => {
        selected = kind
        visible = PAGE_SIZE
        for (const sibling of filters.querySelectorAll<HTMLButtonElement>("button")) {
          const active = sibling === button
          sibling.classList.toggle("active", active)
          sibling.setAttribute("aria-pressed", String(active))
        }
        render()
      })
      filters.append(button)
    }

    search.addEventListener("input", () => {
      query = search.value
      visible = PAGE_SIZE
      render()
    })
    more.addEventListener("click", () => {
      visible += PAGE_SIZE
      render()
    })

    controls.append(search, filters, resultCount)
    root.replaceChildren(controls, list, more)
    document.querySelector<HTMLElement>(".page-listing")?.setAttribute("hidden", "")
    render()
  } catch (error) {
    delete root.dataset.ready
    root.replaceChildren(
      element(
        "p",
        "rl-error",
        "참고자료 목록을 불러오지 못했습니다. 출처 링크는 각 리서치 글 아래에 남아 있습니다.",
      ),
    )
    console.error("reference library:", error)
  }
}

if (typeof document !== "undefined") {
  buildReferenceLibrary()
  document.addEventListener("nav", buildReferenceLibrary)
}
