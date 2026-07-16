import { PageFrame, PageFrameProps } from "./types"
import HeaderConstructor from "../Header"

const Header = HeaderConstructor()

/**
 * toss.tech풍 프레임 — 사이드바 없이 상단 바(.toss-topbar) + 중앙 단일 컬럼 + 푸터.
 * left[] 컴포넌트(page-title, 검색, 다크모드)를 상단 바에 가로 배치해
 * 기존 컴포넌트의 클라이언트 스크립트를 그대로 재사용한다.
 * grid collapse는 custom.scss의 `.page[data-frame="toss"] > #quartz-body` 규칙이 담당.
 */
export const TossFrame: PageFrame = {
  name: "toss",
  render({
    componentData,
    header,
    beforeBody,
    pageBody: Content,
    afterBody,
    left,
    right: _right,
    footer: Footer,
  }: PageFrameProps) {
    return (
      <>
        <div class="toss-topbar">
          {left.map((BodyComponent) => (
            <BodyComponent {...componentData} />
          ))}
        </div>
        <div class="center">
          <div class="page-header">
            <Header {...componentData}>
              {header.map((HeaderComponent) => (
                <HeaderComponent {...componentData} />
              ))}
            </Header>
            <div class="popover-hint">
              {beforeBody.map((BodyComponent) => (
                <BodyComponent {...componentData} />
              ))}
            </div>
          </div>
          <Content {...componentData} />
          <div class="page-footer">
            {afterBody.map((BodyComponent) => (
              <BodyComponent {...componentData} />
            ))}
          </div>
        </div>
        <Footer {...componentData} />
      </>
    )
  },
}
