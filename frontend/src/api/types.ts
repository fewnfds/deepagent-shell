export type JsonPrimitive = boolean | number | string | null

export type BlockType =
  | 'model'
  | 'system-prompt'
  | 'filesystem'
  | 'filesystem-permissions'
  | 'todo-list'
  | 'custom-tool'
  | 'skill'
  | 'custom-middleware'
  | 'output-mode'
  | 'exception-retry'
  | 'subagent'
  | 'other'

export interface CapabilityManifest {
  type: BlockType
  terminology_key: string
  label: string
  order: number
  icon_key: string
  editor_key: string
  subagent_overrideable: boolean
  required: boolean
  subagent_policy: 'force-remove' | 'inherit' | 'top-level-only'
  tool_names: string[]
}

export interface CatalogResponse {
  block_types: CapabilityManifest[]
  editor_defaults: Record<string, unknown>
}

export interface BlockPayload {
  name: string
  [key: string]: unknown
}

export type SavedBlock<TPayload extends BlockPayload = BlockPayload> = TPayload & {
  id: string
}

export interface ModelProviderCatalogItem {
  provider: string
  package: string
  class_name: string
  installed: boolean
  version: string | null
  documentation_url: string
}

export interface ModelProviderCatalog {
  langchain_version: string
  providers: ModelProviderCatalogItem[]
}

export interface CustomToolResource {
  name: string
  function: string
  tool_name: string | null
  description: string
  filename: string
}

export type FileManagerScope = 'files' | 'skills' | 'custom_tools' | 'custom_middlewares'
type ManagedFileKind = 'directory' | 'file' | 'unsupported'

export interface ManagedFileScopeCatalog {
  scopes: FileManagerScope[]
}

export interface ManagedFileItem {
  name: string
  path: string
  kind: ManagedFileKind
  size: number | null
  modified_at: string
  revision: string
}

export interface ManagedDirectory {
  scope: FileManagerScope
  path: string
  items: ManagedFileItem[]
}

export interface ManagedTextFile {
  scope: FileManagerScope
  path: string
  content: string
  revision: string
}

export interface ManagedFileUploadResult {
  scope: FileManagerScope
  path: string
  kind: 'file'
  size: number
}

export interface ManagedArchivePreview {
  total_size: number
  file_count: number
  directory_count: number
}

type SystemSecretUpdate =
  | { operation: 'preserve' }
  | { operation: 'replace'; value: string }

export interface SystemSettings {
  host: string
  port: number
  allow_remote: boolean
  langsmith_tracing_enabled: boolean
  management_token: { configured: boolean }
  cors_origins: string[]
  trusted_proxy_cidrs: string[]
  restart_required: boolean
  active_management_url: string
}

export interface SystemSettingsUpdate {
  host: string
  port: number
  allow_remote: boolean
  langsmith_tracing_enabled: boolean
  management_token: SystemSecretUpdate
  cors_origins: string[]
  trusted_proxy_cidrs: string[]
}

export interface ConfigurationValidationSettings {
  debounce_ms: number
  min_debounce_ms: number
  max_debounce_ms: number
}

export interface SkillResource {
  name: string
  folder: string
  description: string
}

export interface LocalizedMessagePayload {
  message_key: string
  message_args: Record<string, JsonPrimitive>
}

export interface ResourceCatalog<TItem> {
  catalog: TItem[]
  errors: Record<string, LocalizedMessagePayload>
}

export interface CapabilityReference {
  type: string
  block_id: string
}

export interface MiddlewarePackageBinding {
  package_id: string
  enabled: boolean
  config: Record<string, unknown>
}

export type MiddlewareConfigScalar = boolean | number | string

export interface MiddlewareConfigField {
  type: 'string' | 'integer' | 'number' | 'boolean'
  title: string
  description: string
  default?: MiddlewareConfigScalar
  enum?: MiddlewareConfigScalar[]
  minLength?: number
  maxLength?: number
  pattern?: string
  minimum?: number
  maximum?: number
  contentMediaType?: 'text/plain' | 'text/x-python'
  format?: 'python'
}

export interface MiddlewareConfigSchema {
  type: 'object'
  properties: Record<string, MiddlewareConfigField>
  required: string[]
  additionalProperties: false
}

export interface MiddlewarePackageResource {
  api_version: 1
  id: string
  name: string
  description: string
  config_schema: MiddlewareConfigSchema
  folder: string
  python_requirements: string[]
  requirements_fingerprint: string
  dependency_status: 'ready' | 'restart_required' | 'failed'
  dependency_error_code: string
}

export interface WorkflowPayload {
  name: string
  description: string
  main_agent_id: string
  enabled: boolean
}

export interface Workflow extends WorkflowPayload {
  id: string
  main_agent_name: string
}

export interface SubagentReference {
  subagent_id: string
}

export interface MainAgentPayload {
  name: string
  capability_refs: CapabilityReference[]
  subagents: SubagentReference[]
}

export type MainAgent = MainAgentPayload & { id: string }

export interface CapabilityOverride {
  type: string
  mode: 'disabled' | 'replace'
  block_id: string
}

export interface SubagentSettings {
  capability_overrides: CapabilityOverride[]
}

export interface SubagentPayload {
  component_name: string
  name: string
  description: string
  settings: SubagentSettings
}

export type Subagent = SubagentPayload & { id: string }

type ValidationTarget =
  | { kind: 'block'; type: BlockType; id?: string }
  | { kind: 'main_agent'; type?: ''; id?: string }
  | { kind: 'subagent'; type?: ''; id?: string }

export interface DraftValidationRequest {
  target: ValidationTarget
  payload: Record<string, unknown>
}

export interface ValidationIssue {
  code: string
  scope: string
  owner_id: string
  owner_name: string
  owner_type?: string
  path: string
  message: string
  message_key: string
  message_args: Record<string, JsonPrimitive>
  severity: 'error' | 'warning'
}

export interface ValidationReport {
  valid: boolean
  stage: string
  issues: ValidationIssue[]
}

export interface HealthResponse {
  status: string
  runtime: string
}

export interface ReadinessResponse {
  status: string
  sections: Record<string, unknown>
}

export interface ApiServerSettings {
  enabled: boolean
  status: 'running' | 'stopped'
  api_key: {
    configured: boolean
  }
  max_initial_messages: number
  api_base_url: string
  models_endpoint: string
  chat_completions_endpoint: string
  runtime: string
}

type ApiKeyCommand =
  | { operation: 'keep' }
  | { operation: 'clear' }
  | { operation: 'replace'; value: string }

export interface ApiServerSettingsUpdate {
  api_key: ApiKeyCommand
  max_initial_messages?: number
}

export interface PaginationResponse<TItem> {
  items: TItem[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

export type TerminalStatus = 'client_disconnected' | 'completed' | 'failed'

export type EventSource = 'api_call' | 'interception' | 'system' | 'runtime'
export type EventLevel = 'debug' | 'info' | 'warning' | 'error'

export interface EventFeedItem {
  id: string
  source: EventSource
  occurred_at: string
  level: EventLevel
  request_id: string
  summary: string
  inline_content: string | null
  matched_in_content: boolean
  download_available: boolean
}

export type EventFeedResponse = PaginationResponse<EventFeedItem>

export interface EventFeedPreviewResponse {
  content: string
}

export interface EventFeedFilters {
  started_at: string
  ended_at: string
  page?: number
  page_size?: number
  source?: EventSource[]
  level?: EventLevel[]
  query?: string
}

export interface RetentionSettings {
  retention_limit: number
  max_retention_limit: number
}

export interface SystemLogSettings {
  max_size_mib: number
  min_size_mib: number
  max_size_mib_limit: number
}

interface RuntimeDiagnosticEntry {
  sequence: number
  timestamp: string
  level: string
  request_id: string
  model: string
  agent_name: string
  code: string
  exception_type: string
  message: string
}

export interface RuntimeDiagnostics {
  verbose: boolean
  retention_limit: number
  max_retention_limit: number
}

export interface AgentSessionSummary {
  session_id: string
  model: string
  agent_name: string
  started_at: string
  updated_at: string
  status: TerminalStatus
  error_code: string | null
  model_call_count: number
}

interface AgentSessionTimelineStep {
  step_id: string
  sequence: string | number
  kind: string
  timestamp: string | null
  data: Record<string, unknown>
}

export interface AgentSessionTimelineRun {
  id: string
  session_id: string
  request_id: string
  model: string
  agent_name: string
  started_at: string
  finished_at: string
  status: TerminalStatus
  error_code: string | null
  input_message_count: number
  timeline: AgentSessionTimelineStep[]
  response_summary: string
}

interface AgentSessionTokenUsage {
  input_tokens: number | null
  non_reasoning_output_tokens: number | null
  reasoning_output_tokens: number | null
}

export interface AgentSessionTimeline {
  session_id: string
  token_usage: AgentSessionTokenUsage
  runs: AgentSessionTimelineRun[]
}

export type ManagementEvent =
  | { type: 'event_stream_connected' }
  | { type: 'settings_changed' }
  | { type: 'history_changed' }
  | { type: 'interception_changed'; id?: string }
  | { type: 'agent_session_changed'; session_id: string }
  | { type: 'runtime_diagnostic'; entry: RuntimeDiagnosticEntry }
  | { type: 'system_log'; entry: Record<string, unknown> }
  | ({ type: string } & Record<string, unknown>)

export interface AgentSessionFilters {
  page?: number
  page_size?: number
  query?: string
  agent?: string
  status?: TerminalStatus
}
