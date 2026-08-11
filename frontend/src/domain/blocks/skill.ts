import {
  cleanName,
  editableText,
  identity,
  overrideValue,
  stringList,
  uniqueStrings,
  type BlockDraftBase,
  type BlockPayloadBase,
} from './shared'

export interface SkillDraft extends BlockDraftBase {
  skills: string[]
  system_prompt_enabled: boolean
  instruction_override: string
}

interface SkillApiRecord extends BlockDraftBase {
  skills: string[]
  system_prompt_enabled?: boolean
  instruction_override: string | null
}

interface SkillPayload extends BlockPayloadBase {
  skills: string[]
  system_prompt_enabled: boolean
  instruction_override: string | null
}

export interface SkillDefaults {
  system_prompt: string
  required_placeholders?: string[]
}

export interface SkillCatalogItem {
  name: string
  description?: string
}

export const skillAdapter = {
  blank(defaults: SkillDefaults): SkillDraft {
    return {
      id: '', name: '', skills: [], system_prompt_enabled: true,
      instruction_override: defaults.system_prompt,
    }
  },
  fromApi(value: SkillApiRecord, defaults: SkillDefaults): SkillDraft {
    return {
      ...identity(value),
      skills: stringList(value.skills),
      system_prompt_enabled: value.system_prompt_enabled !== false,
      instruction_override: editableText(value.instruction_override, defaults.system_prompt),
    }
  },
  toPayload(value: SkillDraft, defaults: SkillDefaults): SkillPayload {
    return {
      name: cleanName(value.name),
      skills: uniqueStrings(value.skills),
      system_prompt_enabled: value.system_prompt_enabled,
      instruction_override: value.system_prompt_enabled
        ? overrideValue(value.instruction_override, defaults.system_prompt)
        : null,
    }
  },
}
