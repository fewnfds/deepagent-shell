import {
  cleanName,
  identity,
  stringList,
  uniqueStrings,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

export interface CustomToolDraft extends BlockDraftBase {
  tools: string[]
}

type CustomToolApiRecord = CustomToolDraft
interface CustomToolPayload extends BlockPayloadBase { tools: string[] }

export interface CustomToolCatalogItem {
  name: string
  function?: string
  tool_name?: string | null
  filename?: string
  description?: string
}

export const customToolAdapter = {
  blank(): CustomToolDraft {
    return { id: '', name: '', tools: [] }
  },
  fromApi(value: CustomToolApiRecord): CustomToolDraft {
    return { ...identity(value), tools: stringList(value.tools) }
  },
  toPayload(value: CustomToolDraft): CustomToolPayload {
    return { name: cleanName(value.name), tools: uniqueStrings(value.tools) }
  },
}
