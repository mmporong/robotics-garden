(() => {
  const styleId = "jdamr-20261002-tooltips"

  function prepare() {
    const article = document.querySelector("article")
    if (!article?.querySelector("[data-jdamr-tooltip-scope]")) return
    article.dataset.jdamrTooltipFix = "true"
    if (!document.getElementById(styleId)) {
      const style = document.createElement("style")
      style.id = styleId
      style.textContent = `
        article[data-jdamr-tooltip-fix] abbr[data-tooltip]::after {
          display: none;
          max-width: min(22rem, var(--jdamr-tooltip-space, calc(100vw - 2rem)));
        }
        article[data-jdamr-tooltip-fix] abbr[data-tooltip]:is(:hover, :focus)::after {
          display: block;
        }
      `
      document.head.append(style)
    }
  }

  function align(term) {
    const rect = term.getBoundingClientRect()
    const viewportPadding = 16
    const tooltipHalfWidth = 176
    const startsAtLeft = rect.left < tooltipHalfWidth + viewportPadding
    const endsAtRight = window.innerWidth - rect.right < tooltipHalfWidth + viewportPadding
    let space = window.innerWidth - 2 * viewportPadding
    if (startsAtLeft) {
      term.dataset.tooltipAlign = "start"
      space = window.innerWidth - rect.left - viewportPadding
    } else if (endsAtRight) {
      term.dataset.tooltipAlign = "end"
      space = rect.right - viewportPadding
    } else {
      term.dataset.tooltipAlign = "center"
    }
    term.style.setProperty("--jdamr-tooltip-space", `${Math.max(0, space)}px`)
  }

  function update(event) {
    if (!(event.target instanceof Element)) return
    const term = event.target.closest("article[data-jdamr-tooltip-fix] abbr[data-tooltip]")
    if (term) align(term)
  }

  const bindingKey = "__jdamr20261002TooltipBindings"
  if (!window[bindingKey]) {
    window[bindingKey] = true
    document.addEventListener("pointerover", update)
    document.addEventListener("focusin", update)
    document.addEventListener("nav", prepare)
    document.addEventListener("render", prepare)
    window.addEventListener("resize", () => {
      for (const term of document.querySelectorAll(
        "article[data-jdamr-tooltip-fix] abbr[data-tooltip]:is(:hover, :focus)",
      )) align(term)
    })
  }
  prepare()
})()
