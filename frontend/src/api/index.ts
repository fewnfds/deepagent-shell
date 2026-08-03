import {
  buildQuery,
  managementAuth,
  managementDownload,
  managementRequest,
  managementUpload,
  watchManagementEvents,
} from './transport'
import type {
  AgentSessionTimeline,
  AgentSessionFilters,
  AgentSessionSummary,
  ApiServerSettings,
  ApiServerSettingsUpdate,
  AutomationScriptResource,
  AutomationWorkflowPayload,
  AutomationWorkflowType,
  BlockPayload,
  BlockType,
  CatalogResponse,
  ConfigurationValidationSettings,
  CustomMiddlewareResource,
  CustomToolResource,
  DraftValidationRequest,
  EventFeedFilters,
  EventFeedPreviewResponse,
  EventFeedResponse,
  EventSource,
  HealthResponse,
  ManagementEvent,
  ManagedArchivePreview,
  ManagedDirectory,
  ManagedFileScopeCatalog,
  ManagedFileUploadResult,
  ManagedTextFile,
  FileManagerScope,
  ModelProviderCatalog,
  PaginationResponse,
  PrimaryAgent,
  PrimaryAgentPayload,
  ReadinessResponse,
  ResourceCatalog,
  SavedAutomationWorkflow,
  RetentionSettings,
  RuntimeDiagnostics,
  SavedBlock,
  SkillResource,
  Subagent,
  SubagentPayload,
  SystemLogSettings,
  SystemSettings,
  SystemSettingsUpdate,
  ValidationReport,
} from './types'

export * from './transport'
export type * from './types'

function jsonBody(payload: unknown): Pick<RequestInit, 'body' | 'method'> {
  return { method: 'POST', body: JSON.stringify(payload) }
}

function withoutId<T extends object>(value: T): Omit<T, 'id'> {
  const copy = { ...value } as T & { id?: unknown }
  delete copy.id
  return copy
}

function recordPath(base: string, id: string): string {
  return `${base}/${encodeURIComponent(id)}`
}

export const managementApi = {
  clearManagementToken(): void {
    managementAuth.clear()
  },

  getHealth(): Promise<HealthResponse> {
    return managementRequest('/api/health')
  },

  getReadiness(): Promise<ReadinessResponse> {
    return managementRequest('/api/readiness')
  },

  getCatalog(): Promise<CatalogResponse> {
    return managementRequest('/api/catalog')
  },

  fetchModels(
    provider: string,
    baseUrl: string,
    credential: string | null,
    blockId = '',
  ): Promise<string[]> {
    return managementRequest('/api/fetch-models', jsonBody({
      provider,
      base_url: baseUrl,
      credential,
      block_id: blockId,
    }))
  },

  listModelProviders(): Promise<ModelProviderCatalog> {
    return managementRequest('/api/model-providers')
  },

  listCustomTools(): Promise<ResourceCatalog<CustomToolResource>> {
    return managementRequest('/api/tools/custom')
  },

  listCustomMiddlewares(): Promise<ResourceCatalog<CustomMiddlewareResource>> {
    return managementRequest('/api/middlewares/custom')
  },

  listSkills(): Promise<ResourceCatalog<SkillResource>> {
    return managementRequest('/api/skills')
  },

  listAutomationScripts(): Promise<ResourceCatalog<AutomationScriptResource>> {
    return managementRequest('/api/automation/scripts')
  },

  listAutomationWorkflows(
    type: AutomationWorkflowType,
  ): Promise<SavedAutomationWorkflow[]> {
    return managementRequest(`/api/automation/${type}`)
  },

  getAutomationWorkflow(
    type: AutomationWorkflowType,
    id: string,
  ): Promise<SavedAutomationWorkflow> {
    return managementRequest(recordPath(`/api/automation/${type}`, id))
  },

  saveAutomationWorkflow(
    type: AutomationWorkflowType,
    data: AutomationWorkflowPayload | SavedAutomationWorkflow,
  ): Promise<SavedAutomationWorkflow> {
    const id = 'id' in data && typeof data.id === 'string' ? data.id : ''
    const path = id
      ? recordPath(`/api/automation/${type}`, id)
      : `/api/automation/${type}`
    return managementRequest(path, {
      method: id ? 'PUT' : 'POST',
      body: JSON.stringify(withoutId(data)),
    })
  },

  deleteAutomationWorkflow(
    type: AutomationWorkflowType,
    id: string,
  ): Promise<{ ok: boolean }> {
    return managementRequest(recordPath(`/api/automation/${type}`, id), {
      method: 'DELETE',
    })
  },

  getSystemSettings(): Promise<SystemSettings> {
    return managementRequest('/api/system/settings')
  },

  updateSystemSettings(payload: SystemSettingsUpdate): Promise<SystemSettings> {
    return managementRequest('/api/system/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },

  listManagedFileScopes(): Promise<ManagedFileScopeCatalog> {
    return managementRequest('/api/file-manager')
  },

  listManagedFiles(scope: FileManagerScope, path = ''): Promise<ManagedDirectory> {
    return managementRequest(`/api/file-manager/${scope}${buildQuery({ path })}`)
  },

  createManagedDirectory(scope: FileManagerScope, path: string): Promise<{ path: string }> {
    return managementRequest(`/api/file-manager/${scope}/directories`, jsonBody({ path }))
  },

  createManagedTextFile(scope: FileManagerScope, path: string): Promise<{ path: string }> {
    return managementRequest(`/api/file-manager/${scope}/text-files`, jsonBody({ path }))
  },

  uploadManagedFile(
    scope: FileManagerScope,
    path: string,
    file: Blob,
    overwrite: boolean,
    onProgress?: (loaded: number, total: number) => void,
  ): Promise<ManagedFileUploadResult> {
    return managementUpload(
      `/api/file-manager/${scope}/upload${buildQuery({ path, overwrite })}`,
      file,
      { onProgress },
    )
  },

  downloadManagedEntry(scope: FileManagerScope, path: string): Promise<Blob> {
    return managementDownload(
      `/api/file-manager/${scope}/download${buildQuery({ path })}`,
    )
  },

  previewManagedArchive(
    scope: FileManagerScope,
    paths: string[],
  ): Promise<ManagedArchivePreview> {
    return managementRequest(`/api/file-manager/${scope}/archive/preview`, jsonBody({ paths }))
  },

  downloadManagedArchive(scope: FileManagerScope, paths: string[]): Promise<Blob> {
    return managementDownload(`/api/file-manager/${scope}/archive`, jsonBody({ paths }))
  },

  readManagedTextFile(scope: FileManagerScope, path: string): Promise<ManagedTextFile> {
    return managementRequest(
      `/api/file-manager/${scope}/text${buildQuery({ path })}`,
    )
  },

  saveManagedTextFile(
    scope: FileManagerScope,
    path: string,
    content: string,
    revision: string,
  ): Promise<{ path: string; revision: string }> {
    return managementRequest(`/api/file-manager/${scope}/text`, {
      method: 'PUT',
      body: JSON.stringify({ path, content, revision }),
    })
  },

  renameManagedEntry(
    scope: FileManagerScope,
    path: string,
    name: string,
  ): Promise<{ path: string }> {
    return managementRequest(`/api/file-manager/${scope}`, {
      method: 'PATCH',
      body: JSON.stringify({ path, name }),
    })
  },

  deleteManagedFile(scope: FileManagerScope, path: string): Promise<{ deleted: boolean }> {
    return managementRequest(
      `/api/file-manager/${scope}${buildQuery({ path })}`,
      { method: 'DELETE' },
    )
  },

  listBlocks<TPayload extends BlockPayload = BlockPayload>(
    type: BlockType,
  ): Promise<SavedBlock<TPayload>[]> {
    return managementRequest(`/api/blocks/${type}`)
  },

  getBlock<TPayload extends BlockPayload = BlockPayload>(
    type: BlockType,
    id: string,
  ): Promise<SavedBlock<TPayload>> {
    return managementRequest(recordPath(`/api/blocks/${type}`, id))
  },

  saveBlock<TPayload extends BlockPayload>(
    type: BlockType,
    data: TPayload | SavedBlock<TPayload>,
  ): Promise<SavedBlock<TPayload>> {
    const id = 'id' in data && typeof data.id === 'string' ? data.id : ''
    const path = id ? recordPath(`/api/blocks/${type}`, id) : `/api/blocks/${type}`
    return managementRequest(path, {
      method: id ? 'PUT' : 'POST',
      body: JSON.stringify(withoutId(data)),
    })
  },

  copyBlock<TPayload extends BlockPayload = BlockPayload>(
    type: BlockType,
    id: string,
    name: string,
  ): Promise<SavedBlock<TPayload>> {
    return managementRequest(`${recordPath(`/api/blocks/${type}`, id)}/copy`, jsonBody({ name }))
  },

  deleteBlock(type: BlockType, id: string): Promise<{ ok: boolean }> {
    return managementRequest(recordPath(`/api/blocks/${type}`, id), { method: 'DELETE' })
  },

  deleteUnsupportedBlock(id: string): Promise<{ ok: boolean }> {
    return managementRequest(recordPath('/api/unsupported-blocks', id), { method: 'DELETE' })
  },

  deleteBlocks(type: BlockType, ids: string[]): Promise<{ deleted: number }> {
    return managementRequest(`/api/blocks/${type}/delete`, jsonBody({ ids }))
  },

  validateRepository(): Promise<ValidationReport> {
    return managementRequest('/api/validation/repository')
  },

  validateDraft(request: DraftValidationRequest): Promise<ValidationReport> {
    return managementRequest('/api/validation/draft', jsonBody(request))
  },

  getValidationSettings(): Promise<ConfigurationValidationSettings> {
    return managementRequest('/api/validation/settings')
  },

  updateValidationSettings(debounceMs: number): Promise<ConfigurationValidationSettings> {
    return managementRequest('/api/validation/settings', {
      method: 'PUT',
      body: JSON.stringify({ debounce_ms: debounceMs }),
    })
  },

  listPrimaryAgents(): Promise<PrimaryAgent[]> {
    return managementRequest('/api/primary-agents')
  },

  getPrimaryAgent(id: string): Promise<PrimaryAgent> {
    return managementRequest(recordPath('/api/primary-agents', id))
  },

  savePrimaryAgent(data: PrimaryAgentPayload | PrimaryAgent): Promise<PrimaryAgent> {
    const id = 'id' in data ? data.id : ''
    return managementRequest(id ? recordPath('/api/primary-agents', id) : '/api/primary-agents', {
      method: id ? 'PUT' : 'POST',
      body: JSON.stringify(withoutId(data)),
    })
  },

  copyPrimaryAgent(id: string, name: string): Promise<PrimaryAgent> {
    return managementRequest(`${recordPath('/api/primary-agents', id)}/copy`, jsonBody({ name }))
  },

  deletePrimaryAgent(id: string): Promise<{ ok: boolean }> {
    return managementRequest(recordPath('/api/primary-agents', id), { method: 'DELETE' })
  },

  deletePrimaryAgents(ids: string[]): Promise<{ deleted: number }> {
    return managementRequest('/api/primary-agents/delete', jsonBody({ ids }))
  },

  listSubagents(): Promise<Subagent[]> {
    return managementRequest('/api/subagents')
  },

  getSubagent(id: string): Promise<Subagent> {
    return managementRequest(recordPath('/api/subagents', id))
  },

  saveSubagent(
    data: SubagentPayload | Subagent,
  ): Promise<Subagent> {
    const id = 'id' in data ? data.id : ''
    return managementRequest(
      id ? recordPath('/api/subagents', id) : '/api/subagents',
      {
        method: id ? 'PUT' : 'POST',
        body: JSON.stringify(withoutId(data)),
      },
    )
  },

  copySubagent(id: string, componentName: string): Promise<Subagent> {
    return managementRequest(
      `${recordPath('/api/subagents', id)}/copy`,
      jsonBody({ component_name: componentName }),
    )
  },

  deleteSubagent(id: string): Promise<{ ok: boolean }> {
    return managementRequest(recordPath('/api/subagents', id), { method: 'DELETE' })
  },

  deleteSubagents(ids: string[]): Promise<{ deleted: number }> {
    return managementRequest('/api/subagents/delete', jsonBody({ ids }))
  },

  getApiServer(): Promise<ApiServerSettings> {
    return managementRequest('/api/api-server')
  },

  saveApiServer(update: ApiServerSettingsUpdate): Promise<ApiServerSettings> {
    return managementRequest('/api/api-server', {
      method: 'PUT',
      body: JSON.stringify(update),
    })
  },

  startApiServer(): Promise<ApiServerSettings> {
    return managementRequest('/api/api-server/start', { method: 'POST' })
  },

  stopApiServer(): Promise<ApiServerSettings> {
    return managementRequest('/api/api-server/stop', { method: 'POST' })
  },

  watchApiServerEvents(
    onEvent: (event: ManagementEvent) => void,
    onError?: (error: unknown) => void,
  ): () => void {
    return watchManagementEvents(
      '/api/api-server/events',
      onEvent,
      onError ? { onError } : {},
    )
  },

  listEventFeed(filters: EventFeedFilters): Promise<EventFeedResponse> {
    return managementRequest(`/api/event-feed${buildQuery({
      started_at: filters.started_at,
      ended_at: filters.ended_at,
      page: filters.page,
      page_size: filters.page_size,
      source: filters.source,
      level: filters.level,
      query: filters.query,
    })}`)
  },

  downloadEvent(source: EventSource, id: string, view: 'raw' | 'debug' = 'raw'): Promise<Blob> {
    const path = `/api/event-feed/${source}/${encodeURIComponent(id)}/download`
    return managementDownload(
      view === 'raw' ? path : `${path}${buildQuery({ view })}`,
    )
  },

  getApiEventPreview(id: string): Promise<EventFeedPreviewResponse> {
    return managementRequest(`/api/event-feed/api_call/${encodeURIComponent(id)}/preview`)
  },

  getSystemLogSettings(): Promise<SystemLogSettings> {
    return managementRequest('/api/event-feed/system/settings')
  },

  updateSystemLogSettings(maxSizeMib: number): Promise<SystemLogSettings> {
    return managementRequest('/api/event-feed/system/settings', {
      method: 'PUT',
      body: JSON.stringify({ max_size_mib: maxSizeMib }),
    })
  },

  deleteMatchingEventFeed(filters: EventFeedFilters): Promise<{ deleted: number }> {
    return managementRequest('/api/event-feed/delete', jsonBody({
      started_at: filters.started_at,
      ended_at: filters.ended_at,
      source: filters.source ?? [],
      level: filters.level ?? [],
      query: filters.query ?? '',
    }))
  },

  getApiHistoryRetention(): Promise<RetentionSettings> {
    return managementRequest('/api/api-server/history/retention')
  },

  updateApiHistoryRetention(retentionLimit: number): Promise<RetentionSettings> {
    return managementRequest('/api/api-server/history/retention', {
      method: 'PUT',
      body: JSON.stringify({ retention_limit: retentionLimit }),
    })
  },

  getInterceptionTest(): Promise<{ enabled: boolean }> {
    return managementRequest('/api/interception-test')
  },

  updateInterceptionTest(enabled: boolean): Promise<{ enabled: boolean }> {
    return managementRequest('/api/interception-test', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    })
  },

  getInterceptionRetention(): Promise<RetentionSettings> {
    return managementRequest('/api/interception-test/records/retention')
  },

  updateInterceptionRetention(retentionLimit: number): Promise<RetentionSettings> {
    return managementRequest('/api/interception-test/records/retention', {
      method: 'PUT',
      body: JSON.stringify({ retention_limit: retentionLimit }),
    })
  },

  getRuntimeDiagnostics(): Promise<RuntimeDiagnostics> {
    return managementRequest('/api/runtime-diagnostics')
  },

  updateRuntimeDiagnostics(verbose: boolean): Promise<RuntimeDiagnostics> {
    return managementRequest('/api/runtime-diagnostics', {
      method: 'PUT',
      body: JSON.stringify({ verbose }),
    })
  },

  updateRuntimeLogRetention(retentionLimit: number): Promise<RuntimeDiagnostics> {
    return managementRequest('/api/runtime-diagnostics/retention', {
      method: 'PUT',
      body: JSON.stringify({ retention_limit: retentionLimit }),
    })
  },

  listAgentSessions(
    filters: AgentSessionFilters = {},
  ): Promise<PaginationResponse<AgentSessionSummary>> {
    return managementRequest(`/api/agent-sessions${buildQuery({
      page: filters.page,
      page_size: filters.page_size,
      query: filters.query,
      agent: filters.agent,
      status: filters.status,
    })}`)
  },

  getAgentSession(sessionId: string): Promise<Record<string, unknown>> {
    return managementRequest(recordPath('/api/agent-sessions', sessionId))
  },

  getAgentSessionTimeline(sessionId: string): Promise<AgentSessionTimeline> {
    return managementRequest(`${recordPath('/api/agent-sessions', sessionId)}/timeline`)
  },

  getAgentSessionStep(
    sessionId: string,
    runId: string,
    stepId: string,
  ): Promise<Record<string, unknown>> {
    return managementRequest(
      `${recordPath('/api/agent-sessions', sessionId)}/runs/${encodeURIComponent(runId)}/steps/${encodeURIComponent(stepId)}`,
    )
  },

  deleteAgentSession(sessionId: string): Promise<{ deleted: boolean }> {
    return managementRequest(recordPath('/api/agent-sessions', sessionId), {
      method: 'DELETE',
    })
  },

  deleteMatchingAgentSessions(
    filters: AgentSessionFilters,
  ): Promise<{ deleted: number }> {
    return managementRequest('/api/agent-sessions/delete', jsonBody({
      query: filters.query ?? '',
      agent: filters.agent ?? '',
      status: filters.status ?? '',
    }))
  },

  getAgentSessionRetention(): Promise<RetentionSettings> {
    return managementRequest('/api/agent-sessions/retention')
  },

  updateAgentSessionRetention(retentionLimit: number): Promise<RetentionSettings> {
    return managementRequest('/api/agent-sessions/retention', {
      method: 'PUT',
      body: JSON.stringify({ retention_limit: retentionLimit }),
    })
  },
}
