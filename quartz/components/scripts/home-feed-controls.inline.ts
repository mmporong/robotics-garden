import { countTopicPosts, paginationItems, topicUrl } from "./home-feed-controls"

type PaginationState = {
  page: number
  pages: number
  total: number
  pageSize: number
}

function renderPager(root: HTMLElement, state: PaginationState, onChange: (page: number) => void) {
  root.hidden = state.pages <= 1
  if (root.hidden) return

  const button = (label: string, page: number, accessibleName: string) => {
    const node = document.createElement("button")
    node.type = "button"
    node.className = "hf-page"
    node.textContent = label
    node.dataset.page = String(page)
    node.setAttribute("aria-label", accessibleName)
    node.setAttribute("aria-controls", "home-article-list")
    node.addEventListener("click", () => {
      if (page !== state.page) onChange(page)
    })
    return node
  }

  const controls = document.createElement("div")
  controls.className = "hf-pagination-controls"
  const previous = button("‹ 이전", state.page - 1, "이전 페이지")
  previous.classList.add("hf-page-direction")
  previous.disabled = state.page === 1
  const next = button("다음 ›", state.page + 1, "다음 페이지")
  next.classList.add("hf-page-direction")
  next.disabled = state.page === state.pages

  const numbers = document.createElement("div")
  numbers.className = "hf-page-numbers"
  for (const item of paginationItems(state.page, state.pages)) {
    if (item === "gap") {
      const gap = document.createElement("span")
      gap.className = "hf-page-gap"
      gap.textContent = "…"
      gap.setAttribute("aria-hidden", "true")
      numbers.append(gap)
      continue
    }
    const node = button(String(item), item, `${item} 페이지`)
    if (item === state.page) {
      node.classList.add("active")
      node.setAttribute("aria-current", "page")
    }
    numbers.append(node)
  }

  const picker = document.createElement("label")
  picker.className = "hf-page-picker"
  const label = document.createElement("span")
  label.className = "hf-page-picker-label"
  label.textContent = "페이지 선택"
  const select = document.createElement("select")
  select.setAttribute("aria-controls", "home-article-list")
  for (let page = 1; page <= state.pages; page++) {
    const option = document.createElement("option")
    option.value = String(page)
    option.textContent = `${page} / ${state.pages}`
    option.selected = page === state.page
    select.append(option)
  }
  select.addEventListener("change", () => onChange(Number(select.value)))
  picker.append(label, select)

  const status =
    root.querySelector<HTMLParagraphElement>(".hf-page-status") ?? document.createElement("p")
  status.className = "hf-page-status"
  status.setAttribute("role", "status")
  status.setAttribute("aria-live", "polite")
  status.setAttribute("aria-atomic", "true")
  const first = (state.page - 1) * state.pageSize + 1
  const last = Math.min(state.total, state.page * state.pageSize)
  controls.append(previous, numbers, picker, next)
  const existingControls = root.querySelector(".hf-pagination-controls")
  if (existingControls) existingControls.replaceWith(controls)
  else root.prepend(controls)
  if (!status.isConnected) root.append(status)
  status.textContent = `${first}–${last} / ${state.total}편`
}

declare global {
  interface Window {
    gardenHomeControls: {
      renderPager: typeof renderPager
      countTopicPosts: typeof countTopicPosts
      topicUrl: typeof topicUrl
    }
  }
}

window.gardenHomeControls = { renderPager, countTopicPosts, topicUrl }
