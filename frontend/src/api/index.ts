import {
  buildQuery,
  managementAuth,
  managementDownload,
  managementRequest,
  managementUpload,
  watchManagementEvents,
} from './transport'
import type {
  ApiServerSettings,
  ApiServerSettingsUpdate,
  BlockPayload,
  BlockType,
  ManagedComponentType,
  CatalogResponse,
  ConfigurationValidationSettings,
  PythonPackageTemplate,
  CustomToolResource,
  DraftValidationRequest,
  EventFeedFilters,
  EventFeedResponse,
  EventSource,
  HealthResponse,
  ManagementEvent,
  Workflow,
  WorkflowLifecyclePage,
  WorkflowLifecycleDetail,
  WorkflowRunDetail,
  WorkflowRunEventPage,
  WorkflowGraphDocument,
  WorkflowNodeCatalogItem,
  WorkflowPayload,
  WorkflowRole,
  ManagedArchivePreview,
  ManagedDirectory,
  ManagedFileScopeCatalog,
  ManagedFileUploadResult,
  ManagedTextFile,
  MessageInterception,
  FileManagerScope,
  ModelProviderCatalog,
  PaginationResponse,
  PythonPackageFiles,
  MainAgent,
  MainAgentPayload,
  ReadinessResponse,
  ResourceCatalog,
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

  listMiddlewareTemplates(): Promise<ResourceCatalog<PythonPackageTemplate>> {
    return managementRequest('/api/python-package-templates/middleware')
  },

  listConditionRouterTemplates(): Promise<ResourceCatalog<PythonPackageTemplate>> {
    return managementRequest('/api/python-package-templates/condition-router')
  },

  listTaskDispatcherTemplates(): Promise<ResourceCatalog<PythonPackageTemplate>> {
    return managementRequest('/api/python-package-templates/task-dispatcher')
  },

  listSkills(): Promise<ResourceCatalog<SkillResource>> {
    return managementRequest('/api/skills')
  },

  listWorkflows(workflowRole?: WorkflowRole): Promise<Workflow[]> {
    const query = workflowRole ? `?workflow_role=${encodeURIComponent(workflowRole)}` : ''
    return managementRequest(`/api/workflows${query}`)
  },

  listWorkflowNodeCatalog(): Promise<WorkflowNodeCatalogItem[]> {
    return managementRequest('/api/workflow-node-catalog')
  },

  getWorkflow(id: string): Promise<Workflow> {
    return managementRequest(`/api/workflows/${encodeURIComponent(id)}`)
  },

  createWorkflow(payload: WorkflowPayload): Promise<Workflow> {
    return managementRequest('/api/workflows', jsonBody(payload))
  },

  updateWorkflow(id: string, payload: WorkflowPayload): Promise<Workflow> {
    return managementRequest(`/api/workflows/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },

  deleteWorkflow(id: string): Promise<{ ok: boolean }> {
    return managementRequest(`/api/workflows/${id}`, { method: 'DELETE' })
  },

  listWorkflowLifecycles(
    request?: { page?: number; page_size?: number; query?: string },
  ): Promise<WorkflowLifecyclePage> {
    const params = new URLSearchParams()
    if (request?.page !== undefined) params.set('page', String(request.page))
    if (request?.page_size !== undefined) params.set('page_size', String(request.page_size))
    if (request?.query) params.set('query', request.query)
    const query = params.toString()
    return managementRequest(`/api/workflow-lifecycles${query ? `?${query}` : ''}`)
  },

  deleteWorkflowLifecycle(id: string): Promise<{ ok: boolean }> {
    return managementRequest(
      `/api/workflow-lifecycles/${encodeURIComponent(id)}?delete_dynamic_directories=true`,
      { method: 'DELETE' },
    )
  },

  getWorkflowLifecycle(id: string): Promise<WorkflowLifecycleDetail> {
    return managementRequest(`/api/workflow-lifecycles/${encodeURIComponent(id)}`)
  },

  getWorkflowRun(lifecycleId: string, runId: string): Promise<WorkflowRunDetail> {
    return managementRequest(
      `/api/workflow-lifecycles/${encodeURIComponent(lifecycleId)}`
      + `/runs/${encodeURIComponent(runId)}`,
    )
  },

  listWorkflowLifecycleEvents(
    id: string,
    afterSequence: number,
  ): Promise<WorkflowRunEventPage> {
    return managementRequest(
      `/api/workflow-lifecycles/${encodeURIComponent(id)}/events`
      + `?after_sequence=${afterSequence}&limit=1000`,
    )
  },

  downloadWorkflowLifecycle(id: string): Promise<Blob> {
    return managementDownload(
      `/api/workflow-lifecycles/${encodeURIComponent(id)}/download`,
    )
  },

  downloadWorkflowRun(lifecycleId: string, runId: string): Promise<Blob> {
    return managementDownload(
      `/api/workflow-lifecycles/${encodeURIComponent(lifecycleId)}`
      + `/runs/${encodeURIComponent(runId)}/download`,
    )
  },

  getWorkflowGraph(id: string): Promise<WorkflowGraphDocument> {
    return managementRequest(`/api/workflows/${encodeURIComponent(id)}/graph`)
  },

  updateWorkflowGraph(
    id: string,
    document: WorkflowGraphDocument,
  ): Promise<WorkflowGraphDocument> {
    return managementRequest(`/api/workflows/${encodeURIComponent(id)}/graph`, {
      method: 'PUT',
      body: JSON.stringify(document),
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
    type: ManagedComponentType,
  ): Promise<SavedBlock<TPayload>[]> {
    return managementRequest(`/api/blocks/${type}`)
  },

  getBlock<TPayload extends BlockPayload = BlockPayload>(
    type: ManagedComponentType,
    id: string,
  ): Promise<SavedBlock<TPayload>> {
    return managementRequest(recordPath(`/api/blocks/${type}`, id))
  },

  readPythonPackageFiles(
    type: ManagedComponentType,
    id: string,
    paths: string[],
  ): Promise<PythonPackageFiles> {
    return managementRequest(
      `${recordPath(`/api/blocks/${type}`, id)}/python-package-files`,
      jsonBody({ paths }),
    )
  },

  saveBlock<TPayload extends BlockPayload>(
    type: ManagedComponentType,
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
    type: ManagedComponentType,
    id: string,
    name: string,
  ): Promise<SavedBlock<TPayload>> {
    return managementRequest(`${recordPath(`/api/blocks/${type}`, id)}/copy`, jsonBody({ name }))
  },

  deleteBlock(type: ManagedComponentType, id: string): Promise<{ ok: boolean }> {
    return managementRequest(recordPath(`/api/blocks/${type}`, id), { method: 'DELETE' })
  },

  deleteUnsupportedBlock(id: string): Promise<{ ok: boolean }> {
    return managementRequest(recordPath('/api/unsupported-blocks', id), { method: 'DELETE' })
  },

  deleteBlocks(type: ManagedComponentType, ids: string[]): Promise<{ deleted: number }> {
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

  listMainAgents(): Promise<MainAgent[]> {
    return managementRequest('/api/main-agents')
  },

  getMainAgent(id: string): Promise<MainAgent> {
    return managementRequest(recordPath('/api/main-agents', id))
  },

  saveMainAgent(data: MainAgentPayload | MainAgent): Promise<MainAgent> {
    const id = 'id' in data ? data.id : ''
    return managementRequest(id ? recordPath('/api/main-agents', id) : '/api/main-agents', {
      method: id ? 'PUT' : 'POST',
      body: JSON.stringify(withoutId(data)),
    })
  },

  copyMainAgent(id: string, name: string): Promise<MainAgent> {
    return managementRequest(`${recordPath('/api/main-agents', id)}/copy`, jsonBody({ name }))
  },

  deleteMainAgent(id: string): Promise<{ ok: boolean }> {
    return managementRequest(recordPath('/api/main-agents', id), { method: 'DELETE' })
  },

  deleteMainAgents(ids: string[]): Promise<{ deleted: number }> {
    return managementRequest('/api/main-agents/delete', jsonBody({ ids }))
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

  getMessageInterception(): Promise<MessageInterception> {
    return managementRequest('/api/message-interception')
  },

  updateMessageInterception(enabled: boolean): Promise<MessageInterception> {
    return managementRequest('/api/message-interception', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    })
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

  downloadEvent(source: EventSource, id: string): Promise<Blob> {
    const path = `/api/event-feed/${source}/${encodeURIComponent(id)}/download`
    return managementDownload(path)
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

  getRuntimeDiagnostics(): Promise<RuntimeDiagnostics> {
    return managementRequest('/api/runtime-diagnostics')
  },

  updateRuntimeDiagnosticRetention(retentionLimit: number): Promise<RuntimeDiagnostics> {
    return managementRequest('/api/runtime-diagnostics/retention', {
      method: 'PUT',
      body: JSON.stringify({ retention_limit: retentionLimit }),
    })
  },

}
