import { i18n } from "../i18n"
import { FullSlug, getFileExtension, joinSegments, pathToRoot } from "../util/path"
import { CSSResourceToStyleElement, JSResourceToScriptElement } from "../util/resources"
import { googleFontHref, googleFontSubsetHref } from "../util/theme"
import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"
import { unescapeHTML } from "../util/escape"
import { CustomOgImagesEmitterName } from "../../.quartz/plugins"
export default (() => {
  const Head: QuartzComponent = ({
    cfg,
    fileData,
    externalResources,
    ctx,
  }: QuartzComponentProps) => {
    const titleSuffix = cfg.pageTitleSuffix ?? ""
    const title =
      (fileData.frontmatter?.title ?? i18n(cfg.locale).propertyDefaults.title) + titleSuffix
    const description =
      fileData.frontmatter?.socialDescription ??
      fileData.frontmatter?.description ??
      unescapeHTML(fileData.description?.trim() ?? i18n(cfg.locale).propertyDefaults.description)

    const { css, js, additionalHead } = externalResources

    const url = new URL(`https://${cfg.baseUrl ?? "example.com"}`)
    const path = url.pathname as FullSlug
    const baseDir = fileData.slug === "404" ? path : pathToRoot(fileData.slug!)
    const iconPath = joinSegments(baseDir, "static/icon.png")

    // Url of current page
    const socialUrl =
      fileData.slug === "404" ? url.toString() : joinSegments(url.toString(), fileData.slug!)

    const usesCustomOgImage = ctx.cfg.plugins.emitters.some(
      (e) => e.name === CustomOgImagesEmitterName,
    )
    const ogImageDefaultPath = `https://${cfg.baseUrl}/static/og-image.png`

    const coreStylesheet = css[0]?.content
    const coreScript = js.find(
      (r) => r.loadTime === "beforeDOMReady" && r.contentType === "external",
    )

    return (
      <head>
        <title>{title}</title>
        <meta charSet="utf-8" />
        {/* 첫 방문 기본 테마 = 라이트 (다크모드 플러그인이 읽기 전에 심는다) */}
        <script
          dangerouslySetInnerHTML={{
            __html: `if(!localStorage.getItem("theme"))localStorage.setItem("theme","light")`,
          }}
        />
        {/* 사이드바 프로필: 사이트 제목(.page-title) 밑에 이름 + Email/LinkedIn 배지 주입 (배포 안전 core) */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var EMAIL="mmporong@gmail.com";function iconLink(h,s,a){var e=document.createElement("a");e.href=h;e.target="_blank";e.rel="noopener noreferrer";e.setAttribute("aria-label",a);var i=document.createElement("img");i.src=s;i.alt=a;i.loading="lazy";e.appendChild(i);return e;}function emailBtn(s){var e=document.createElement("a");e.href="mailto:"+EMAIL;e.setAttribute("aria-label","Email "+EMAIL);e.title="클릭하면 이메일 주소 복사";var i=document.createElement("img");i.src=s;i.alt="Email";i.loading="lazy";e.appendChild(i);e.addEventListener("click",function(ev){ev.preventDefault();var box=e.closest(".pc-links")||e.parentNode;function done(){if(box.querySelector(".pc-copied"))return;var t=document.createElement("span");t.className="pc-copied";t.textContent="이메일 복사됨";box.appendChild(t);setTimeout(function(){if(t.parentNode)t.parentNode.removeChild(t);},1400);}if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(EMAIL).then(done).catch(done);}else{done();}});return e;}function inject(){var pt=document.querySelector(".page-title");if(!pt||document.getElementById("profile-contact"))return;var w=document.createElement("div");w.id="profile-contact";var n=document.createElement("div");n.className="pc-name";n.textContent="임주영";var l=document.createElement("div");l.className="pc-links";l.appendChild(emailBtn("https://custom-icon-badges.demolab.com/badge/Email-EA4335?style=flat-square&logo=gmail&logoColor=fff"));l.appendChild(iconLink("https://www.linkedin.com/in/mmporong","https://custom-icon-badges.demolab.com/badge/LinkedIn-0A66C2?style=flat-square&logo=linkedin-white&logoColor=fff","LinkedIn"));l.appendChild(iconLink("https://github.com/mmporong","https://custom-icon-badges.demolab.com/badge/GitHub-181717?style=flat-square&logo=github&logoColor=fff","GitHub"));w.appendChild(n);w.appendChild(l);pt.insertAdjacentElement("afterend",w);}if(document.readyState!=="loading")inject();else document.addEventListener("DOMContentLoaded",inject);document.addEventListener("nav",inject);})();`,
          }}
        />
        {coreStylesheet && <link rel="preload" href={coreStylesheet} as="style" />}
        {coreScript && coreScript.contentType === "external" && (
          <link rel="preload" href={coreScript.src} as="script" />
        )}
        {cfg.theme.cdnCaching && cfg.theme.fontOrigin === "googleFonts" && (
          <>
            <link rel="preconnect" href="https://fonts.googleapis.com" />
            <link rel="preconnect" href="https://fonts.gstatic.com" />
            <link rel="stylesheet" href={googleFontHref(cfg.theme)} />
            {cfg.theme.typography.title && (
              <link rel="stylesheet" href={googleFontSubsetHref(cfg.theme, cfg.pageTitle)} />
            )}
          </>
        )}
        <link rel="preconnect" href="https://cdnjs.cloudflare.com" crossOrigin="anonymous" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />

        <meta name="og:site_name" content={cfg.pageTitle}></meta>
        <meta property="og:title" content={title} />
        <meta property="og:type" content="website" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={title} />
        <meta name="twitter:description" content={description} />
        <meta property="og:description" content={description} />
        <meta property="og:image:alt" content={description} />

        {!usesCustomOgImage && (
          <>
            <meta property="og:image" content={ogImageDefaultPath} />
            <meta property="og:image:url" content={ogImageDefaultPath} />
            <meta name="twitter:image" content={ogImageDefaultPath} />
            <meta
              property="og:image:type"
              content={`image/${getFileExtension(ogImageDefaultPath) ?? "png"}`}
            />
          </>
        )}

        {cfg.baseUrl && (
          <>
            <meta property="twitter:domain" content={cfg.baseUrl}></meta>
            <meta property="og:url" content={socialUrl}></meta>
            <meta property="twitter:url" content={socialUrl}></meta>
          </>
        )}

        <link rel="icon" href={iconPath} />
        <meta name="description" content={description} />
        <meta name="generator" content="Quartz" />

        {css.map((resource) => CSSResourceToStyleElement(resource, true))}
        {js
          .filter((resource) => resource.loadTime === "beforeDOMReady")
          .map((res) => JSResourceToScriptElement(res, true))}
        {additionalHead.map((resource) => {
          if (typeof resource === "function") {
            return resource(fileData)
          } else {
            return resource
          }
        })}
      </head>
    )
  }

  return Head
}) satisfies QuartzComponentConstructor
