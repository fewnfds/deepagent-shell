export const blockTypes = [
  'model',
  'custom-tool',
  'custom-middleware',
  'output-mode',
  'exception-retry',
  'filesystem',
  'filesystem-permissions',
  'skill',
  'system-prompt',
  'subagent',
  'todo-list',
  'summarization',
  'prompt-caching',
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
  package_id: string
  enabled: boolean
  config: Record<string, unknown>
}

interface MiddlewareApiEntry {
  package_id: string
  enabled: boolean
  config: Record<string, unknown>
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
  id: string
  name: string
  description: string
  config_schema: MiddlewareConfigSchema
  dependency_status: 'ready' | 'restart_required' | 'failed'
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

export interface MappedDirectory {
  virtual_path: string
  local_path: string
}

export interface VirtualSource {
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
  human_message_token_limit_before_evict: number | string | null
  grep_max_count: number | string
  max_execute_timeout: number | string
  tool_configs: Record<string, FilesystemToolDraft>
}

interface FilesystemApiRecord extends BlockDraftBase {
  mapped_directories: MappedDirectory[]
  virtual_directories: VirtualSource[]
  virtual_files: VirtualSource[]
  system_prompt_override: string | null
  tool_token_limit_before_evict: number | null
  human_message_token_limit_before_evict?: number | null
  grep_max_count?: number
  max_execute_timeout?: number
  tool_configs: Record<string, FilesystemToolApiValue>
}

interface FilesystemPayload extends BlockPayloadBase {
  mapped_directories: MappedDirectory[]
  virtual_directories: VirtualSource[]
  virtual_files: VirtualSource[]
  system_prompt_override: string | null
  tool_token_limit_before_evict: number | string | null
  human_message_token_limit_before_evict: number | string | null
  grep_max_count: number | string
  max_execute_timeout: number | string
  tool_configs: Record<string, FilesystemToolApiValue>
}

export interface FilesystemToolDefault {
  name: string
  kind?: string
  configurable: boolean
  visible: boolean
  default_description: string
}

export interface FilesystemDefaults {
  system_prompt: string
  tool_token_limit_before_evict: number | null
  human_message_token_limit_before_evict?: number | null
  grep_max_count?: number
  max_execute_timeout?: number
  tools: FilesystemToolDefault[]
}

export type SummarizationThresholdType = 'auto' | 'fraction' | 'tokens' | 'messages'
export interface SummarizationThresholdDraft {
  type: SummarizationThresholdType
  value: number | string | null
}
export interface SummarizationDraft extends BlockDraftBase {
  enabled: boolean
  trigger: SummarizationThresholdDraft
  keep: SummarizationThresholdDraft
  truncate_args_enabled: boolean
  truncate_args_trigger: SummarizationThresholdDraft
  truncate_args_keep: SummarizationThresholdDraft
  truncate_args_max_length: number | string
  truncate_args_text: string
  trim_tokens_to_summarize: number | string | null
  summary_prompt_override: string
}
export interface PromptCachingDraft extends BlockDraftBase {
  enabled: boolean
  type: 'ephemeral'
  ttl: '5m' | '1h'
  min_messages_to_cache: number | string
}
export type SummarizationDefaults = Omit<SummarizationDraft, 'id' | 'name'> & {
  summary_prompt_default: string
}
interface SummarizationApiRecord extends BlockDraftBase {
  enabled?: unknown
  trigger?: unknown
  keep?: unknown
  truncate_args_enabled?: unknown
  truncate_args_trigger?: unknown
  truncate_args_keep?: unknown
  truncate_args_max_length?: unknown
  truncate_args_text?: unknown
  trim_tokens_to_summarize?: unknown
  summary_prompt_override?: unknown
}
interface SummarizationPayload extends BlockPayloadBase,
  Omit<SummarizationDraft, 'id' | 'name' | 'summary_prompt_override'> {
  summary_prompt_override: string | null
}
export type PromptCachingDefaults = Omit<PromptCachingDraft, 'id' | 'name'>
interface PromptCachingApiRecord extends BlockDraftBase {
  enabled?: unknown
  type?: unknown
  ttl?: unknown
  min_messages_to_cache?: unknown
}
interface PromptCachingPayload extends BlockPayloadBase, Omit<PromptCachingDraft, 'id' | 'name'> {}

export type FilesystemPermissionValue = 'read-write' | 'read-only' | 'no-access'

export interface FilesystemPermissionEntryDraft {
  path: string
  permission: FilesystemPermissionValue
}

type FilesystemPermissionEntryApi = FilesystemPermissionEntryDraft

interface FilesystemPermissionToolOverrideDraft extends FilesystemToolDraft {
  override: boolean
}

export interface FilesystemPermissionsDraft extends BlockDraftBase {
  permissions: FilesystemPermissionEntryDraft[]
  system_prompt_override_enabled: boolean
  system_prompt_use_default: boolean
  system_prompt_value: string
  tool_overrides: Record<string, FilesystemPermissionToolOverrideDraft>
}

interface FilesystemPermissionsApiRecord extends BlockDraftBase {
  permissions: FilesystemPermissionEntryApi[]
  system_prompt_override: { value: string | null } | null
  tool_overrides: Record<string, FilesystemToolApiValue | null>
}

interface FilesystemPermissionsPayload extends BlockPayloadBase {
  permissions: FilesystemPermissionEntryApi[]
  system_prompt_override: { value: string | null } | null
  tool_overrides: Record<string, FilesystemToolApiValue>
}

export interface FilesystemPermissionsDefaults {
  system_prompt: string
  tools: FilesystemToolDefault[]
}

export interface FilesystemImportSource extends BlockDraftBase {
  mapped_directories?: MappedDirectory[]
  virtual_directories?: VirtualSource[]
  virtual_files?: VirtualSource[]
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
    package_id: value.package_id ?? '',
    enabled: value.enabled ?? true,
    config: { ...(value.config ?? {}) },
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
              package_id: stringValue(entry.package_id),
              enabled: typeof entry.enabled === 'boolean' ? entry.enabled : true,
              config: isRecord(entry.config) ? { ...entry.config } : {},
            })]
          : [])
        : [],
    }
  },
  toPayload(value: CustomMiddlewareDraft): CustomMiddlewarePayload {
    return {
      name: cleanName(value.name),
      middlewares: value.middlewares.map((entry) => ({
        package_id: entry.package_id.trim(),
        enabled: entry.enabled,
        config: { ...entry.config },
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

function summarizationThresholdDraft(
  value: unknown,
  fallback: SummarizationThresholdDraft,
): SummarizationThresholdDraft {
  const source = isRecord(value) ? value : {}
  const type = ['auto', 'fraction', 'tokens', 'messages'].includes(String(source.type))
    ? source.type as SummarizationThresholdType
    : fallback.type
  return {
    type,
    value: type === 'auto' ? null : normalizeTokenLimit(source.value, fallback.value as number | null),
  }
}

export const summarizationAdapter = {
  blank(defaults: SummarizationDefaults): SummarizationDraft {
    return {
      id: '',
      name: '',
      ...clone(defaults),
      summary_prompt_override: defaults.summary_prompt_default,
    }
  },
  fromApi(value: SummarizationApiRecord, defaults: SummarizationDefaults): SummarizationDraft {
    return {
      ...identity(value),
      enabled: typeof value.enabled === 'boolean' ? value.enabled : defaults.enabled,
      trigger: summarizationThresholdDraft(value.trigger, defaults.trigger),
      keep: summarizationThresholdDraft(value.keep, defaults.keep),
      truncate_args_enabled: typeof value.truncate_args_enabled === 'boolean'
        ? value.truncate_args_enabled
        : defaults.truncate_args_enabled,
      truncate_args_trigger: summarizationThresholdDraft(
        value.truncate_args_trigger,
        defaults.truncate_args_trigger,
      ),
      truncate_args_keep: summarizationThresholdDraft(
        value.truncate_args_keep,
        defaults.truncate_args_keep,
      ),
      truncate_args_max_length: normalizeTokenLimit(
        value.truncate_args_max_length,
        Number(defaults.truncate_args_max_length),
      ) ?? defaults.truncate_args_max_length,
      truncate_args_text: stringValue(value.truncate_args_text, defaults.truncate_args_text),
      trim_tokens_to_summarize: normalizeTokenLimit(
        value.trim_tokens_to_summarize,
        defaults.trim_tokens_to_summarize as number | null,
      ),
      summary_prompt_override: stringValue(
        value.summary_prompt_override,
        defaults.summary_prompt_default,
      ),
    }
  },
  toPayload(value: SummarizationDraft, defaults: SummarizationDefaults): SummarizationPayload {
    const threshold = (item: SummarizationThresholdDraft): SummarizationThresholdDraft => ({
      type: item.type,
      value: item.type === 'auto' ? null : normalizeTokenLimit(item.value, null),
    })
    return {
      name: cleanName(value.name),
      enabled: value.enabled,
      trigger: threshold(value.trigger),
      keep: threshold(value.keep),
      truncate_args_enabled: value.truncate_args_enabled,
      truncate_args_trigger: threshold(value.truncate_args_trigger),
      truncate_args_keep: threshold(value.truncate_args_keep),
      truncate_args_max_length: normalizeTokenLimit(value.truncate_args_max_length, null)
        ?? value.truncate_args_max_length,
      truncate_args_text: value.truncate_args_text,
      trim_tokens_to_summarize: normalizeTokenLimit(value.trim_tokens_to_summarize, null),
      summary_prompt_override: value.summary_prompt_override === defaults.summary_prompt_default
        ? null
        : value.summary_prompt_override || null,
    }
  },
}

export const promptCachingAdapter = {
  blank(defaults: PromptCachingDefaults): PromptCachingDraft {
    return { id: '', name: '', ...clone(defaults) }
  },
  fromApi(value: PromptCachingApiRecord, defaults: PromptCachingDefaults): PromptCachingDraft {
    return {
      ...identity(value),
      enabled: typeof value.enabled === 'boolean' ? value.enabled : defaults.enabled,
      type: 'ephemeral',
      ttl: value.ttl === '1h' || value.ttl === '5m' ? value.ttl : defaults.ttl,
      min_messages_to_cache: normalizeTokenLimit(
        value.min_messages_to_cache,
        Number(defaults.min_messages_to_cache),
      ) ?? defaults.min_messages_to_cache,
    }
  },
  toPayload(value: PromptCachingDraft): PromptCachingPayload {
    return {
      name: cleanName(value.name),
      enabled: value.enabled,
      type: value.type,
      ttl: value.ttl,
      min_messages_to_cache: normalizeTokenLimit(value.min_messages_to_cache, null)
        ?? value.min_messages_to_cache,
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
      human_message_token_limit_before_evict: defaults.human_message_token_limit_before_evict ?? 50_000,
      grep_max_count: defaults.grep_max_count ?? 1_000,
      max_execute_timeout: defaults.max_execute_timeout ?? 3_600,
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
      human_message_token_limit_before_evict: normalizeTokenLimit(
        value.human_message_token_limit_before_evict,
        defaults.human_message_token_limit_before_evict ?? 50_000,
      ),
      grep_max_count: normalizeTokenLimit(value.grep_max_count, defaults.grep_max_count ?? 1_000) ?? 1_000,
      max_execute_timeout: normalizeTokenLimit(value.max_execute_timeout, defaults.max_execute_timeout ?? 3_600) ?? 3_600,
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
      human_message_token_limit_before_evict: normalizeTokenLimit(
        value.human_message_token_limit_before_evict,
        defaults.human_message_token_limit_before_evict ?? 50_000,
      ),
      grep_max_count: normalizeTokenLimit(value.grep_max_count, defaults.grep_max_count ?? 1_000) ?? 1_000,
      max_execute_timeout: normalizeTokenLimit(value.max_execute_timeout, defaults.max_execute_timeout ?? 3_600) ?? 3_600,
      tool_configs,
    }
  },
}

function filesystemPermissionToolOverrides(
  value: unknown,
  defaults: FilesystemPermissionsDefaults,
): Record<string, FilesystemPermissionToolOverrideDraft> {
  const source = isRecord(value) ? value : {}
  return Object.fromEntries(defaults.tools.map((tool) => {
    const configured = isRecord(source[tool.name]) ? source[tool.name] : null
    return [tool.name, {
      override: configured !== null,
      visible: configured && typeof configured.visible === 'boolean'
        ? configured.visible
        : tool.visible,
      description_override: configured
        ? editableText(configured.description_override, tool.default_description)
        : tool.default_description,
    }]
  }))
}

export const filesystemPermissionsAdapter = {
  blank(defaults: FilesystemPermissionsDefaults): FilesystemPermissionsDraft {
    return {
      id: '',
      name: '',
      permissions: [],
      system_prompt_override_enabled: false,
      system_prompt_use_default: true,
      system_prompt_value: defaults.system_prompt,
      tool_overrides: filesystemPermissionToolOverrides(undefined, defaults),
    }
  },
  fromApi(
    value: FilesystemPermissionsApiRecord,
    defaults: FilesystemPermissionsDefaults,
  ): FilesystemPermissionsDraft {
    const prompt = isRecord(value.system_prompt_override)
      ? value.system_prompt_override
      : null
    return {
      ...identity(value),
      permissions: Array.isArray(value.permissions)
        ? value.permissions.flatMap((entry) => isRecord(entry)
          && typeof entry.path === 'string'
          && ['read-write', 'read-only', 'no-access'].includes(String(entry.permission))
          ? [{
              path: entry.path,
              permission: entry.permission as FilesystemPermissionValue,
            }]
          : [])
        : [],
      system_prompt_override_enabled: prompt !== null,
      system_prompt_use_default: prompt?.value === null,
      system_prompt_value: typeof prompt?.value === 'string'
        ? prompt.value
        : defaults.system_prompt,
      tool_overrides: filesystemPermissionToolOverrides(value.tool_overrides, defaults),
    }
  },
  toPayload(
    value: FilesystemPermissionsDraft,
    defaults: FilesystemPermissionsDefaults,
  ): FilesystemPermissionsPayload {
    const toolDefaults = new Map(defaults.tools.map((tool) => [tool.name, tool]))
    const tool_overrides = Object.fromEntries(
      Object.entries(value.tool_overrides).flatMap(([name, override]) => {
        const fallback = toolDefaults.get(name)
        if (!fallback || !override.override) return []
        return [[name, {
          visible: fallback.configurable ? override.visible : fallback.visible,
          description_override: overrideValue(
            override.description_override,
            fallback.default_description,
          ),
        }]]
      }),
    )
    return {
      name: cleanName(value.name),
      permissions: value.permissions
        .filter((entry) => entry.path.trim())
        .map((entry) => ({
          path: entry.path.trim(),
          permission: entry.permission,
        })),
      system_prompt_override: value.system_prompt_override_enabled
        ? {
            value: value.system_prompt_use_default
              ? null
              : value.system_prompt_value,
          }
        : null,
      tool_overrides,
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
  'filesystem-permissions': filesystemPermissionsAdapter,
  skill: skillAdapter,
  'system-prompt': systemPromptAdapter,
  subagent: subagentAdapter,
  'todo-list': todoListAdapter,
  summarization: summarizationAdapter,
  'prompt-caching': promptCachingAdapter,
} as const
import type { MiddlewareConfigSchema } from '@/api'
