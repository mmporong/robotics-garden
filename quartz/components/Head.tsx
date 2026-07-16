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
        {/* 홈 랜딩 피드: content/index.md의 #home-feed에 카드 피드 렌더 (배포 안전 core, SPA nav 대응) */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var CATS={"physical-ai":"학습 노트","research":"리서치"};var cache=null;function el(t,c,txt){var e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e;}function fmtDate(d){var p=d.split("-");return p.length===3?p[0]+". "+p[1]+". "+p[2]+".":d;}function excerpt(s){s=(s||"").replace(/\\s+/g," ").trim();if(s.length<=110)return s;s=s.slice(0,110);var i=s.lastIndexOf(" ");if(i>60)s=s.slice(0,i);return s+"\\u2026";}function load(base){if(cache)return Promise.resolve(cache);return fetch(base+"/static/contentIndex.json").then(function(r){return r.json();}).then(function(d){cache=d;return d;});}function thumb(p){var im=document.createElement("img");im.src=p.img;im.alt="";im.loading="lazy";im.addEventListener("error",function(){im.style.display="none";});return im;}function build(){var root=document.getElementById("home-feed");if(!root||root.dataset.done)return;root.dataset.done="1";var base=document.body.dataset.basepath||"";load(base).then(function(data){var posts=Object.keys(data).filter(function(s){return /^(physical-ai|research)\\//.test(s)&&!/\\/index$/.test(s);}).map(function(s){var e=data[s];var m=s.match(/(\\d{4}-\\d{2}-\\d{2})/);return{slug:s,title:e.title,cat:s.split("/")[0],date:m?m[1]:"",tags:e.tags||[],ex:excerpt(e.content),url:base+"/"+encodeURI(s),img:base+"/"+encodeURI(s)+"-og-image.webp"};}).sort(function(a,b){return a.date>b.date?-1:a.date<b.date?1:(a.slug>b.slug?-1:1);});var active="all";var bar=el("div","hf-bar");var brand=el("a","hf-brand");brand.href=base+"/";brand.appendChild(el("span","hf-eyebrow","ROBOTICS LEARNING LOG"));brand.appendChild(el("span","hf-wordmark","hello, robot"));var nav=el("div","hf-links");[["GitHub","https://github.com/mmporong"],["LinkedIn","https://www.linkedin.com/in/mmporong"],["Email","mailto:mmporong@gmail.com"]].forEach(function(x){var a=el("a",null,x[0]);a.href=x[1];if(x[1].indexOf("http")===0){a.target="_blank";a.rel="noopener noreferrer";}nav.appendChild(a);});bar.appendChild(brand);bar.appendChild(nav);var hero=el("a","hf-hero");var tabs=el("nav","hf-tabs");tabs.setAttribute("aria-label","카테고리");var sec=el("h2","hf-sec","전체 아티클");var main=el("div","hf-main");var list=el("div","hf-list");var rail=el("aside","hf-rail");function heroFill(p){hero.innerHTML="";hero.href=p.url;var t=el("div","hf-hero-text");var meta=el("div","hf-meta");meta.appendChild(el("span","hf-chip",CATS[p.cat]));meta.appendChild(el("time","hf-date",fmtDate(p.date)));t.appendChild(meta);t.appendChild(el("span","hf-hero-title",p.title));t.appendChild(el("p","hf-hero-desc",p.ex));hero.appendChild(t);var w=el("div","hf-hero-img");w.appendChild(thumb(p));hero.appendChild(w);}function listFill(arr){list.innerHTML="";if(!arr.length){list.appendChild(el("p","hf-empty","이 카테고리의 다른 글이 아직 없어요."));return;}arr.forEach(function(p){var a=el("a","hf-row");a.href=p.url;var t=el("div","hf-row-text");var meta=el("div","hf-meta");meta.appendChild(el("span","hf-chip",CATS[p.cat]));meta.appendChild(el("time","hf-date",fmtDate(p.date)));t.appendChild(meta);t.appendChild(el("span","hf-row-title",p.title));t.appendChild(el("p","hf-row-desc",p.ex));a.appendChild(t);var w=el("div","hf-thumb");w.appendChild(thumb(p));a.appendChild(w);list.appendChild(a);});}function render(){var f=active==="all"?posts:posts.filter(function(p){return p.cat===active;});sec.textContent=active==="all"?"전체 아티클":CATS[active];if(!f.length){hero.style.display="none";listFill([]);return;}hero.style.display="";heroFill(f[0]);listFill(f.slice(1));}[["all","전체"],["physical-ai","학습 노트"],["research","리서치"]].forEach(function(x){var b=el("button","hf-tab"+(x[0]==="all"?" active":""),x[1]);b.dataset.cat=x[0];b.addEventListener("click",function(){active=x[0];[].forEach.call(tabs.children,function(c){c.classList.toggle("active",c===b);});render();});tabs.appendChild(b);});var box1=el("div","hf-box");box1.appendChild(el("h3",null,"최근 글"));var ol=el("ol","hf-recent");posts.slice(0,5).forEach(function(p){var li=el("li");var a=el("a",null,p.title);a.href=p.url;li.appendChild(a);li.appendChild(el("span","hf-date",fmtDate(p.date)));ol.appendChild(li);});box1.appendChild(ol);var box2=el("div","hf-box");box2.appendChild(el("h3",null,"태그"));var tg=el("div","hf-tags");var cnt={};posts.forEach(function(p){p.tags.forEach(function(t){cnt[t]=(cnt[t]||0)+1;});});Object.keys(cnt).sort(function(a,b){return cnt[b]-cnt[a];}).slice(0,12).forEach(function(t){var a=el("a",null,"#"+t);a.href=base+"/tags/"+encodeURI(t);tg.appendChild(a);});box2.appendChild(tg);rail.appendChild(box1);rail.appendChild(box2);main.appendChild(list);main.appendChild(rail);root.appendChild(bar);root.appendChild(hero);root.appendChild(tabs);root.appendChild(sec);root.appendChild(main);render();});}if(document.readyState!=="loading")build();else document.addEventListener("DOMContentLoaded",build);document.addEventListener("nav",build);})();`,
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
