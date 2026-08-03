export const blockTypes = [
  'model',
  'custom-tool',
  'custom-middleware',
  'output-mode',
  'exception-retry',
  'filesystem',
  'skill',
  'system-prompt',
  'subagent',
  'todo-list',
] as const

export interface BlockDraftBase {
  id: string
  name: string
}

interface BlockPayloadBase {
  name: string
}

type ModelProvider = string
export type ModelProviderSettingInput = string | number | boolean | '' | null
type ModelProviderSettingsDraft = Record<string, ModelProviderSettingInput>

export interface ModelDraft extends BlockDraftBase {
  provider: ModelProvider
  base_url: string
  credential_secret: string
  credential_status: string
  model: string
  provider_settings: ModelProviderSettingsDraft
  tool_choice: string
  response_format: string
  model_settings: string
}

export interface ModelApiRecord extends BlockDraftBase {
  provider?: unknown
  base_url: string
  credential?: { status?: string }
  model: string
  provider_settings?: Record<string, unknown>
  tool_choice?: unknown
  response_format?: unknown
  model_settings?: unknown
}

interface ModelPayload extends BlockPayloadBase {
  provider: ModelProvider
  base_url: string
  credential: string | null
  model: string
  provider_settings: Record<string, unknown>
  tool_choice: unknown
  response_format: unknown
  model_settings: unknown
}

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

interface MiddlewareDraftEntry {
  _key: string
  name: string
  enabled: boolean
  source: string
}

interface MiddlewareApiEntry {
  name: string
  enabled: boolean
  source: string
}

export interface CustomMiddlewareDraft extends BlockDraftBase {
  middlewares: MiddlewareDraftEntry[]
}

interface CustomMiddlewareApiRecord extends BlockDraftBase {
  middlewares: MiddlewareApiEntry[]
}

interface CustomMiddlewarePayload extends BlockPayloadBase {
  middlewares: MiddlewareApiEntry[]
}

export interface CustomMiddlewareCatalogItem {
  filename: string
  name?: string
  description?: string
  source?: string
}

type OutputFilterMode = 'allowlist' | 'blocklist'
type OutputVariableEncoding = 'html' | 'plain'

interface OutputFilterMapping {
  field: string
  value: string
}

interface OutputEventTemplate {
  enabled: boolean
  template: string
}

interface OutputModeValue {
  filter_mode: OutputFilterMode
  filter_mappings: OutputFilterMapping[]
  variable_encoding: OutputVariableEncoding
  event_templates: Record<string, OutputEventTemplate>
}

export interface OutputModeDraft extends BlockDraftBase, OutputModeValue {}
type OutputModeApiRecord = OutputModeDraft
interface OutputModePayload extends BlockPayloadBase, OutputModeValue {}

interface OutputEventDefault {
  key: string
  label?: string
  description?: string
  variables: string[]
}

export interface OutputModeDefaults {
  events: OutputEventDefault[]
  filter_fields: string[]
  default_value: OutputModeValue
}

type ExceptionRetryStrategy = 'provider_native' | 'model_retry_middleware'
export type ExceptionRetryCondition =
  | 'transport_error'
  | 'timeout'
  | 'rate_limit'
  | 'server_error'
  | 'authentication_error'

interface ExceptionRetryValue {
  strategy: ExceptionRetryStrategy
  force_non_streaming: boolean
  max_retries: number | string
  retry_on: ExceptionRetryCondition[]
}

export interface ExceptionRetryDraft extends BlockDraftBase, ExceptionRetryValue {}
type ExceptionRetryApiRecord = ExceptionRetryDraft
interface ExceptionRetryPayload extends BlockPayloadBase, ExceptionRetryValue {}

export interface ExceptionRetryDefaults {
  strategies: ExceptionRetryStrategy[]
  conditions: ExceptionRetryCondition[]
  default_value: ExceptionRetryValue
}

interface MappedDirectory {
  virtual_path: string
  local_path: string
}

interface VirtualSource {
  virtual_path: string
  source_path: string
}

interface FilesystemToolDraft {
  visible: boolean
  description_override: string
}

interface FilesystemToolApiValue {
  visible: boolean
  description_override: string | null
}

export interface FilesystemDraft extends BlockDraftBase {
  mapped_directories: MappedDirectory[]
  virtual_directories: VirtualSource[]
  virtual_files: VirtualSource[]
  system_prompt_override: string
  tool_token_limit_before_evict: number | string | null
  tool_configs: Record<string, FilesystemToolDraft>
}

interface FilesystemApiRecord extends BlockDraftBase {
  mapped_directories: MappedDirectory[]
  virtual_directories: VirtualSource[]
  virtual_files: VirtualSource[]
  system_prompt_override: string | null
  tool_token_limit_before_evict: number | null
  tool_configs: Record<string, FilesystemToolApiValue>
}

interface FilesystemPayload extends BlockPayloadBase {
  mapped_directories: MappedDirectory[]
  virtual_directories: VirtualSource[]
  virtual_files: VirtualSource[]
  system_prompt_override: string | null
  tool_token_limit_before_evict: number | string | null
  tool_configs: Record<string, FilesystemToolApiValue>
}

interface FilesystemToolDefault {
  name: string
  kind?: string
  configurable: boolean
  visible: boolean
  default_description: string
}

export interface FilesystemDefaults {
  system_prompt: string
  tool_token_limit_before_evict: number | null
  tools: FilesystemToolDefault[]
}

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

export interface SystemPromptDraft extends BlockDraftBase {
  system_prompt: string
}

type SystemPromptApiRecord = SystemPromptDraft
interface SystemPromptPayload extends BlockPayloadBase { system_prompt: string }

export interface SubagentDraft extends BlockDraftBase {
  instruction_override: string
  task_description_override: string
}

interface SubagentApiRecord extends BlockDraftBase {
  instruction_override: string | null
  task_description_override: string | null
}

interface SubagentPayload extends BlockPayloadBase {
  instruction_override: string | null
  task_description_override: string | null
}

export interface SubagentDefaults {
  system_prompt: string
  tool_description: string
}

export interface TodoListDraft extends BlockDraftBase {
  system_prompt_override: string
  tool_description_override: string
}

interface TodoListApiRecord extends BlockDraftBase {
  system_prompt_override: string | null
  tool_description_override: string | null
}

interface TodoListPayload extends BlockPayloadBase {
  system_prompt_override: string | null
  tool_description_override: string | null
}

export interface TodoListDefaults {
  system_prompt: string
  tool_description: string
}

let middlewareEntrySequence = 0

function nextMiddlewareKey(): string {
  middlewareEntrySequence += 1
  return `middleware-entry-${middlewareEntrySequence}`
}

function cleanName(value: string): string {
  return value.trim()
}

function uniqueStrings(values: readonly string[]): string[] {
  const seen = new Set<string>()
  return values.flatMap((value) => {
    const cleaned = value.trim()
    if (!cleaned || seen.has(cleaned)) return []
    seen.add(cleaned)
    return [cleaned]
  })
}

function clone<T>(value: T): T {
  if (Array.isArray(value)) return value.map((item) => clone(item)) as T
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [key, clone(child)]),
    ) as T
  }
  return value
}

function overrideValue(value: string, defaultValue: string): string | null {
  return value === defaultValue ? null : value
}

function editableText(value: unknown, defaultValue: string): string {
  return typeof value === 'string' ? value : defaultValue
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

function identity(value: unknown): BlockDraftBase {
  const source = isRecord(value) ? value : {}
  return { id: stringValue(source.id), name: stringValue(source.name) }
}

function jsonObjectEditorValue(value: unknown, fallback: string): string {
  return isRecord(value) ? JSON.stringify(value) : fallback
}

function toolChoiceEditorValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'boolean' || isRecord(value)) return JSON.stringify(value)
  return ''
}

function jsonInputValue(value: string, fallback: unknown): unknown {
  if (!value.trim()) return fallback
  try {
    return JSON.parse(value) as unknown
  } catch {
    return value
  }
}

function providerSettingsEditorValue(value: unknown): ModelProviderSettingsDraft {
  if (!isRecord(value)) return {}
  const settings: ModelProviderSettingsDraft = {}
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean') {
      settings[key] = item
    } else if (Array.isArray(item) && item.every((entry) => typeof entry === 'string')) {
      settings[key] = JSON.stringify(item)
    }
  }
  return settings
}

function providerSettingsPayload(value: ModelProviderSettingsDraft): Record<string, unknown> {
  const settings: Record<string, unknown> = {}
  for (const [key, item] of Object.entries(value)) {
    if (item === '' || item === null) continue
    settings[key] = (key === 'stop' || key === 'stop_sequences') && typeof item === 'string'
      ? jsonInputValue(item, null)
      : item
  }
  return settings
}

function blankModel(): ModelDraft {
  return {
    id: '', name: '', provider: 'openai', base_url: '', credential_secret: '', credential_status: 'missing', model: '',
    provider_settings: {},
    tool_choice: '', response_format: '', model_settings: '{}',
  }
}

export const modelAdapter = {
  blank: blankModel,
  fromApi(value: ModelApiRecord): ModelDraft {
    const base = identity(value)
    const credential = isRecord(value.credential) ? value.credential : {}
    return {
      ...base,
      provider: stringValue(value.provider, 'openai'),
      base_url: stringValue(value.base_url),
      credential_secret: '',
      credential_status: credential.status === 'masked' ? 'masked' : 'missing',
      model: stringValue(value.model),
      provider_settings: providerSettingsEditorValue(value.provider_settings),
      tool_choice: toolChoiceEditorValue(value.tool_choice),
      response_format: jsonObjectEditorValue(value.response_format, ''),
      model_settings: jsonObjectEditorValue(value.model_settings, '{}'),
    }
  },
  toPayload(value: ModelDraft): ModelPayload {
    return {
      name: cleanName(value.name),
      provider: value.provider,
      base_url: value.base_url.trim(),
      credential: value.credential_secret || null,
      model: value.model.trim(),
      provider_settings: providerSettingsPayload(value.provider_settings),
      tool_choice: jsonInputValue(value.tool_choice, null),
      response_format: jsonInputValue(value.response_format, null),
      model_settings: jsonInputValue(value.model_settings, {}),
    }
  },
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

export function createMiddlewareEntry(value: Partial<MiddlewareApiEntry> = {}): MiddlewareDraftEntry {
  return {
    _key: nextMiddlewareKey(),
    name: value.name ?? '',
    enabled: value.enabled ?? true,
    source: value.source ?? '',
  }
}

export const customMiddlewareAdapter = {
  blank(): CustomMiddlewareDraft {
    return { id: '', name: '', middlewares: [] }
  },
  fromApi(value: CustomMiddlewareApiRecord): CustomMiddlewareDraft {
    return {
      ...identity(value),
      middlewares: Array.isArray(value.middlewares)
        ? value.middlewares.flatMap((entry) => isRecord(entry)
          ? [createMiddlewareEntry({
              name: stringValue(entry.name),
              enabled: typeof entry.enabled === 'boolean' ? entry.enabled : true,
              source: stringValue(entry.source),
            })]
          : [])
        : [],
    }
  },
  toPayload(value: CustomMiddlewareDraft): CustomMiddlewarePayload {
    return {
      name: cleanName(value.name),
      middlewares: value.middlewares.map((entry) => ({
        name: entry.name.trim(),
        enabled: entry.enabled,
        source: entry.source.trim(),
      })),
    }
  },
}

export const outputModeAdapter = {
  blank(defaults: OutputModeDefaults): OutputModeDraft {
    return { id: '', name: '', ...clone(defaults.default_value) }
  },
  fromApi(value: OutputModeApiRecord, defaults: OutputModeDefaults): OutputModeDraft {
    const templates = isRecord(value.event_templates) ? value.event_templates : {}
    const event_templates = Object.fromEntries(defaults.events.map((event) => {
      const fallback = defaults.default_value.event_templates[event.key]
      const source = isRecord(templates[event.key]) ? templates[event.key] : {}
      return [event.key, {
        enabled: typeof source.enabled === 'boolean'
          ? source.enabled
          : fallback?.enabled ?? false,
        template: typeof source.template === 'string'
          ? source.template
          : fallback?.template ?? '',
      }]
    }))
    return {
      ...identity(value),
      filter_mode: value.filter_mode === 'allowlist' || value.filter_mode === 'blocklist'
        ? value.filter_mode
        : defaults.default_value.filter_mode,
      filter_mappings: Array.isArray(value.filter_mappings)
        ? value.filter_mappings.flatMap((mapping) => isRecord(mapping)
          && typeof mapping.field === 'string'
          && typeof mapping.value === 'string'
          ? [{ field: mapping.field, value: mapping.value }]
          : [])
        : clone(defaults.default_value.filter_mappings),
      variable_encoding: value.variable_encoding === 'html' || value.variable_encoding === 'plain'
        ? value.variable_encoding
        : defaults.default_value.variable_encoding,
      event_templates,
    }
  },
  toPayload(value: OutputModeDraft): OutputModePayload {
    return {
      name: cleanName(value.name),
      filter_mode: value.filter_mode,
      filter_mappings: clone(value.filter_mappings),
      variable_encoding: value.variable_encoding,
      event_templates: clone(value.event_templates),
    }
  },
}

export const exceptionRetryAdapter = {
  blank(defaults: ExceptionRetryDefaults): ExceptionRetryDraft {
    return { id: '', name: '', ...clone(defaults.default_value) }
  },
  fromApi(
    value: ExceptionRetryApiRecord,
    defaults: ExceptionRetryDefaults,
  ): ExceptionRetryDraft {
    const fallback = defaults.default_value
    return {
      ...identity(value),
      strategy: defaults.strategies.includes(value.strategy)
        ? value.strategy
        : fallback.strategy,
      force_non_streaming: typeof value.force_non_streaming === 'boolean'
        ? value.force_non_streaming
        : fallback.force_non_streaming,
      max_retries: typeof value.max_retries === 'number'
        ? value.max_retries
        : fallback.max_retries,
      retry_on: Array.isArray(value.retry_on)
        ? defaults.conditions.filter((condition) => value.retry_on.includes(condition))
        : clone(fallback.retry_on),
    }
  },
  toPayload(value: ExceptionRetryDraft): ExceptionRetryPayload {
    return {
      name: cleanName(value.name),
      strategy: value.strategy,
      force_non_streaming: value.force_non_streaming,
      max_retries: value.max_retries,
      retry_on: [...new Set(value.retry_on)],
    }
  },
}

function filesystemToolDraft(
  source: unknown,
  fallback: FilesystemToolDefault,
): FilesystemToolDraft {
  const current = isRecord(source) ? source : {}
  return {
    visible: fallback.configurable && typeof current.visible === 'boolean'
      ? current.visible
      : fallback.visible,
    description_override: editableText(
      current.description_override,
      fallback.default_description,
    ),
  }
}

function filesystemToolConfigs(
  source: unknown,
  defaults: FilesystemDefaults,
): Record<string, FilesystemToolDraft> {
  const current = isRecord(source) ? source : {}
  return Object.fromEntries(defaults.tools.map((tool) => [
    tool.name,
    filesystemToolDraft(current[tool.name], tool),
  ]))
}

function mappingRows<T>(
  value: unknown,
  keys: readonly (keyof T)[],
): T[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!isRecord(item) || !keys.some((key) => typeof item[String(key)] === 'string')) {
      return []
    }
    return [Object.fromEntries(
      keys.map((key) => [key, stringValue(item[String(key)])]),
    ) as T]
  })
}

function normalizeTokenLimit(value: unknown, fallback: number | null): number | string | null {
  if (value === undefined) return fallback
  if (value === null) return null
  if (typeof value === 'string') {
    if (!value.trim()) return null
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : value
  }
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function nonBlankMapping<T extends { virtual_path: string }>(item: T, sourceKey: keyof T): boolean {
  return Boolean(item.virtual_path.trim() || String(item[sourceKey] ?? '').trim())
}

export const filesystemAdapter = {
  blank(defaults: FilesystemDefaults): FilesystemDraft {
    return {
      id: '', name: '', mapped_directories: [], virtual_directories: [], virtual_files: [],
      system_prompt_override: defaults.system_prompt,
      tool_token_limit_before_evict: defaults.tool_token_limit_before_evict,
      tool_configs: filesystemToolConfigs(undefined, defaults),
    }
  },
  fromApi(value: FilesystemApiRecord, defaults: FilesystemDefaults): FilesystemDraft {
    return {
      ...identity(value),
      mapped_directories: mappingRows<MappedDirectory>(
        value.mapped_directories,
        ['virtual_path', 'local_path'],
      ),
      virtual_directories: mappingRows<VirtualSource>(
        value.virtual_directories,
        ['virtual_path', 'source_path'],
      ),
      virtual_files: mappingRows<VirtualSource>(
        value.virtual_files,
        ['virtual_path', 'source_path'],
      ),
      system_prompt_override: editableText(value.system_prompt_override, defaults.system_prompt),
      tool_token_limit_before_evict: normalizeTokenLimit(
        value.tool_token_limit_before_evict,
        defaults.tool_token_limit_before_evict,
      ),
      tool_configs: filesystemToolConfigs(value.tool_configs, defaults),
    }
  },
  toPayload(value: FilesystemDraft, defaults: FilesystemDefaults): FilesystemPayload {
    const toolDefaults = new Map(defaults.tools.map((tool) => [tool.name, tool]))
    const tool_configs = Object.fromEntries(Object.entries(value.tool_configs).flatMap(([name, config]) => {
      const fallback = toolDefaults.get(name)
      if (!fallback) return []
      return [[name, {
        visible: fallback.configurable ? config.visible : fallback.visible,
        description_override: overrideValue(config.description_override, fallback.default_description),
      }]]
    }))
    return {
      name: cleanName(value.name),
      mapped_directories: value.mapped_directories
        .filter((item) => nonBlankMapping(item, 'local_path'))
        .map((item) => ({ virtual_path: item.virtual_path.trim(), local_path: item.local_path.trim() })),
      virtual_directories: value.virtual_directories
        .filter((item) => nonBlankMapping(item, 'source_path'))
        .map((item) => ({ virtual_path: item.virtual_path.trim(), source_path: item.source_path.trim() })),
      virtual_files: value.virtual_files
        .filter((item) => nonBlankMapping(item, 'source_path'))
        .map((item) => ({ virtual_path: item.virtual_path.trim(), source_path: item.source_path.trim() })),
      system_prompt_override: overrideValue(value.system_prompt_override, defaults.system_prompt),
      tool_token_limit_before_evict: normalizeTokenLimit(
        value.tool_token_limit_before_evict,
        defaults.tool_token_limit_before_evict,
      ),
      tool_configs,
    }
  },
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

export const systemPromptAdapter = {
  blank(): SystemPromptDraft {
    return { id: '', name: '', system_prompt: '' }
  },
  fromApi(value: SystemPromptApiRecord): SystemPromptDraft {
    return { ...identity(value), system_prompt: stringValue(value.system_prompt) }
  },
  toPayload(value: SystemPromptDraft): SystemPromptPayload {
    return { name: cleanName(value.name), system_prompt: value.system_prompt.trim() }
  },
}

export const subagentAdapter = {
  blank(defaults: SubagentDefaults): SubagentDraft {
    return {
      id: '', name: '',
      instruction_override: defaults.system_prompt,
      task_description_override: defaults.tool_description,
    }
  },
  fromApi(value: SubagentApiRecord, defaults: SubagentDefaults): SubagentDraft {
    return {
      ...identity(value),
      instruction_override: editableText(value.instruction_override, defaults.system_prompt),
      task_description_override: editableText(value.task_description_override, defaults.tool_description),
    }
  },
  toPayload(value: SubagentDraft, defaults: SubagentDefaults): SubagentPayload {
    return {
      name: cleanName(value.name),
      instruction_override: overrideValue(value.instruction_override, defaults.system_prompt),
      task_description_override: overrideValue(value.task_description_override, defaults.tool_description),
    }
  },
}

export const todoListAdapter = {
  blank(defaults: TodoListDefaults): TodoListDraft {
    return {
      id: '', name: '',
      system_prompt_override: defaults.system_prompt,
      tool_description_override: defaults.tool_description,
    }
  },
  fromApi(value: TodoListApiRecord, defaults: TodoListDefaults): TodoListDraft {
    return {
      ...identity(value),
      system_prompt_override: editableText(value.system_prompt_override, defaults.system_prompt),
      tool_description_override: editableText(value.tool_description_override, defaults.tool_description),
    }
  },
  toPayload(value: TodoListDraft, defaults: TodoListDefaults): TodoListPayload {
    return {
      name: cleanName(value.name),
      system_prompt_override: overrideValue(value.system_prompt_override, defaults.system_prompt),
      tool_description_override: overrideValue(value.tool_description_override, defaults.tool_description),
    }
  },
}

export const blockAdapters = {
  model: modelAdapter,
  'custom-tool': customToolAdapter,
  'custom-middleware': customMiddlewareAdapter,
  'output-mode': outputModeAdapter,
  'exception-retry': exceptionRetryAdapter,
  filesystem: filesystemAdapter,
  skill: skillAdapter,
  'system-prompt': systemPromptAdapter,
  subagent: subagentAdapter,
  'todo-list': todoListAdapter,
} as const
