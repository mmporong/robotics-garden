import { loadQuartzConfig, loadQuartzLayout } from "./quartz/plugins/loader/config-loader"
import { ReferenceIndex } from "./quartz/plugins/emitters/referenceIndex"

const config = await loadQuartzConfig()
config.plugins.emitters.push(ReferenceIndex())
export default config
export const layout = await loadQuartzLayout()
