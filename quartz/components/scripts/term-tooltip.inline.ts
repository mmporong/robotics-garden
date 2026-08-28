type TermDefinition = {
  term: string
  tooltip: string
}

const repeatTooltipSkipSelector =
  "abbr, a, pre, script, style, textarea, select, option, svg, math, [data-no-term-tooltip]"
const connectedTermCharacter = /[A-Za-z0-9_./+·-]/

function collectTermDefinitions(article: HTMLElement) {
  const definitions = new Map<string, TermDefinition>()

  for (const term of article.querySelectorAll<HTMLElement>(
    "abbr[title], abbr[data-tooltip]",
  )) {
    const termText = term.textContent?.replace(/\s+/g, " ").trim()
    const tooltip = term.dataset.tooltip ?? term.getAttribute("title")
    const definitionKey = termText?.toLocaleLowerCase()
    if (!termText || !tooltip || !definitionKey || definitions.has(definitionKey)) continue

    definitions.set(definitionKey, { term: termText, tooltip })
  }

  return [...definitions.values()].sort((left, right) => right.term.length - left.term.length)
}

function hasSafeTermBoundaries(text: string, start: number, term: string) {
  const before = text[start - 1]
  const after = text[start + term.length]
  const first = term[0]
  const last = term[term.length - 1]

  if (before && connectedTermCharacter.test(first) && connectedTermCharacter.test(before)) {
    return false
  }
  if (after && connectedTermCharacter.test(last) && connectedTermCharacter.test(after)) {
    return false
  }
  return true
}

function findNextDefinition(text: string, offset: number, definitions: TermDefinition[]) {
  let best: { definition: TermDefinition; start: number } | undefined
  const searchableText = text.toLocaleLowerCase()

  for (const definition of definitions) {
    const searchableTerm = definition.term.toLocaleLowerCase()
    let start = searchableText.indexOf(searchableTerm, offset)
    while (start >= 0 && !hasSafeTermBoundaries(text, start, definition.term)) {
      start = searchableText.indexOf(searchableTerm, start + 1)
    }
    if (start < 0) continue

    if (
      !best ||
      start < best.start ||
      (start === best.start && definition.term.length > best.definition.term.length)
    ) {
      best = { definition, start }
    }
  }

  return best
}

function wrapRepeatedTerms(article: HTMLElement, definitions: TermDefinition[]) {
  if (definitions.length === 0) return

  const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT)
  const textNodes: Text[] = []
  let current = walker.nextNode()
  while (current) {
    const textNode = current as Text
    const parent = textNode.parentElement
    if (
      textNode.data.trim() &&
      parent &&
      !parent.closest(repeatTooltipSkipSelector)
    ) {
      textNodes.push(textNode)
    }
    current = walker.nextNode()
  }

  for (const textNode of textNodes) {
    const source = textNode.data
    const fragment = document.createDocumentFragment()
    let offset = 0
    let matched = false

    while (offset < source.length) {
      const next = findNextDefinition(source, offset, definitions)
      if (!next) break

      matched = true
      if (next.start > offset) {
        fragment.append(document.createTextNode(source.slice(offset, next.start)))
      }

      const term = document.createElement("abbr")
      const displayedTerm = source.slice(next.start, next.start + next.definition.term.length)
      term.dataset.tooltip = next.definition.tooltip
      term.dataset.tooltipAuto = "true"
      term.tabIndex = 0
      term.setAttribute(
        "aria-label",
        `${displayedTerm}: ${next.definition.tooltip}`,
      )
      term.textContent = displayedTerm
      fragment.append(term)
      offset = next.start + next.definition.term.length
    }

    if (!matched) continue
    if (offset < source.length) fragment.append(document.createTextNode(source.slice(offset)))
    textNode.replaceWith(fragment)
  }
}

function prepareTermTooltips() {
  for (const article of document.querySelectorAll<HTMLElement>("article")) {
    wrapRepeatedTerms(article, collectTermDefinitions(article))
  }

  const terms = document.querySelectorAll<HTMLElement>(
    "article abbr[title], article abbr[data-tooltip]",
  )

  for (const term of terms) {
    const tooltip = term.dataset.tooltip ?? term.getAttribute("title")
    if (!tooltip) continue

    term.dataset.tooltip = tooltip
    term.removeAttribute("title")
    term.tabIndex = 0

    const termText = term.textContent?.trim()
    if (termText && !term.hasAttribute("aria-label")) {
      term.setAttribute("aria-label", `${termText}: ${tooltip}`)
    }
  }
}

function tooltipTermFrom(target: EventTarget | null) {
  if (!(target instanceof Element)) return null
  return target.closest<HTMLElement>("article abbr[data-tooltip]")
}

function alignTooltip(term: HTMLElement) {
  const rect = term.getBoundingClientRect()
  const tooltipHalfWidth = 176
  const viewportPadding = 16

  if (rect.left < tooltipHalfWidth + viewportPadding) {
    term.dataset.tooltipAlign = "start"
  } else if (window.innerWidth - rect.right < tooltipHalfWidth + viewportPadding) {
    term.dataset.tooltipAlign = "end"
  } else {
    term.dataset.tooltipAlign = "center"
  }
}

document.addEventListener("pointerover", (event) => {
  const term = tooltipTermFrom(event.target)
  if (term) alignTooltip(term)
})

document.addEventListener("focusin", (event) => {
  const term = tooltipTermFrom(event.target)
  if (term) alignTooltip(term)
})

document.addEventListener("nav", prepareTermTooltips)
document.addEventListener("render", prepareTermTooltips)
prepareTermTooltips()
