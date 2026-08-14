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
  MiddlewarePackageResource,
  CustomToolResource,
  DraftValidationRequest,
  EventFeedFilters,
  EventFeedResponse,
  EventSource,
  HealthResponse,
  ManagementEvent,
  Workflow,
  WorkflowComponentDefinition,
  WorkflowComponentDefinitionPayload,
  WorkflowComponentInstance,
  WorkflowComponentInstancePayload,
  WorkflowEventOutputSettings,
  WorkflowGraphDocument,
  WorkflowNodeCatalogItem,
  WorkflowPayload,
  ManagedArchivePreview,
  ManagedDirectory,
  ManagedFileScopeCatalog,
  ManagedFileUploadResult,
  ManagedTextFile,
  FileManagerScope,
  ModelProviderCatalog,
  PaginationResponse,
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

  listCustomMiddlewares(): Promise<ResourceCatalog<MiddlewarePackageResource>> {
    return managementRequest('/api/middlewares/custom')
  },

  listSkills(): Promise<ResourceCatalog<SkillResource>> {
    return managementRequest('/api/skills')
  },

  listWorkflows(): Promise<Workflow[]> {
    return managementRequest('/api/workflows')
  },

  getWorkflowEventOutput(): Promise<WorkflowEventOutputSettings> {
    return managementRequest('/api/workflow-event-output')
  },

  updateWorkflowEventOutput(
    payload: WorkflowEventOutputSettings,
  ): Promise<WorkflowEventOutputSettings> {
    return managementRequest('/api/workflow-event-output', {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
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

  listWorkflowComponentDefinitions(): Promise<WorkflowComponentDefinition[]> {
    return managementRequest('/api/workflow-component-definitions')
  },

  saveWorkflowComponentDefinition(
    data: WorkflowComponentDefinitionPayload & { id?: string },
  ): Promise<WorkflowComponentDefinition> {
    const id = data.id ?? ''
    const payload = { ...data }
    delete payload.id
    return managementRequest(
      id
        ? recordPath('/api/workflow-component-definitions', id)
        : '/api/workflow-component-definitions',
      {
        method: id ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      },
    )
  },

  deleteWorkflowComponentDefinition(id: string): Promise<{ ok: boolean }> {
    return managementRequest(
      recordPath('/api/workflow-component-definitions', id),
      { method: 'DELETE' },
    )
  },

  listWorkflowComponentInstances(definitionId?: string): Promise<WorkflowComponentInstance[]> {
    return managementRequest(
      `/api/workflow-component-instances${buildQuery({ definition_id: definitionId })}`,
    )
  },

  saveWorkflowComponentInstance(
    data: WorkflowComponentInstancePayload & { id?: string },
  ): Promise<WorkflowComponentInstance> {
    const id = data.id ?? ''
    const payload = { ...data }
    delete payload.id
    return managementRequest(
      id
        ? recordPath('/api/workflow-component-instances', id)
        : '/api/workflow-component-instances',
      {
        method: id ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      },
    )
  },

  deleteWorkflowComponentInstance(id: string): Promise<{ ok: boolean }> {
    return managementRequest(
      recordPath('/api/workflow-component-instances', id),
      { method: 'DELETE' },
    )
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

  updateRuntimeLogRetention(retentionLimit: number): Promise<RuntimeDiagnostics> {
    return managementRequest('/api/runtime-diagnostics/retention', {
      method: 'PUT',
      body: JSON.stringify({ retention_limit: retentionLimit }),
    })
  },

  updateRuntimeDebug(enabled: boolean): Promise<RuntimeDiagnostics> {
    return managementRequest('/api/runtime-diagnostics/debug', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    })
  },

}
