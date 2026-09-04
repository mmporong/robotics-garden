export function resolveReferenceIndexUrl(basePath: string, origin: string): URL {
  const normalizedBasePath = basePath.replace(/^\/+|\/+$/g, "")
  const siteRoot = new URL(`/${normalizedBasePath ? `${normalizedBasePath}/` : ""}`, origin)
  return new URL("static/references.json", siteRoot)
}

export function articleUrl(indexUrl: URL, slug: string): string {
  return new URL(encodeURI(slug), new URL("../", indexUrl)).toString()
}
