<script setup lang="ts">
import { LteAlert, LteButton, LteCard } from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  managementApi,
  type AgentSessionFilters,
  type AgentSessionSummary,
  type AgentSessionTimeline,
  type ManagementEvent,
  type PaginationResponse,
  type RetentionSettings,
  type TerminalStatus,
} from '@/api'
import DataTableWorkbench from '@/components/data-table/DataTableWorkbench.vue'
import type {
  DataTableConfig,
  DataTableFilterValue,
} from '@/components/data-table/types'
import ModalHost from '@/components/ModalHost.vue'
import PageShell from '@/components/PageShell.vue'
import { useConfirmation } from '@/composables/useConfirmation'
import {
  useManagementEvents,
  type ManagementEventSource,
} from '@/composables/useManagementEvents'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import {
  buildSessionTimeline,
  type SessionTimelineEntry,
} from '@/domain/sessionTimeline'
import { triggerBrowserDownload } from '@/utils/download'

export interface AgentSessionsApi extends ManagementEventSource {
  listAgentSessions(filters: AgentSessionFilters): Promise<PaginationResponse<AgentSessionSummary>>
  getAgentSession(sessionId: string): Promise<Record<string, unknown>>
  getAgentSessionTimeline(sessionId: string): Promise<AgentSessionTimeline>
  getAgentSessionStep(sessionId: string, runId: string, stepId: string): Promise<Record<string, unknown>>
  deleteAgentSession(sessionId: string): Promise<{ deleted: boolean }>
  deleteMatchingAgentSessions(filters: AgentSessionFilters): Promise<{ deleted: number }>
  getAgentSessionRetention(): Promise<RetentionSettings>
  updateAgentSessionRetention(retentionLimit: number): Promise<RetentionSettings>
}

const props = defineProps<{ api?: AgentSessionsApi }>()
const { locale, t } = useI18n()
const managementError = useManagementError()
const api: AgentSessionsApi = props.api ?? managementApi
const { confirm } = useConfirmation()
const { notify } = useToasts()

const sessionTable = ref<{
  reload: () => Promise<void>
  reloadFirst: () => Promise<void>
} | null>(null)
const retentionLimit = ref(20)
const savedRetentionLimit = ref(20)
const retentionSaving = ref(false)
const retentionError = ref('')
const detailSessionId = ref<string | null>(null)
const detail = ref<AgentSessionTimeline | null>(null)
const detailLoading = ref(false)
const detailError = ref('')
const expandedStepIds = ref(new Set<string>())
const stepJson = ref<Record<string, string>>({})
const stepLoading = ref<Record<string, boolean>>({})
const stepErrors = ref<Record<string, string>>({})
let detailSequence = 0

async function loadRetention(): Promise<void> {
  retentionError.value = ''
  try {
    const loaded = (await api.getAgentSessionRetention()).retention_limit
    retentionLimit.value = loaded
    savedRetentionLimit.value = loaded
  } catch (error) {
    retentionError.value = managementError.describe(error).display
  }
}

async function saveRetention(): Promise<void> {
  const nextLimit = retentionLimit.value
  retentionSaving.value = true
  retentionError.value = ''
  if (nextLimit < savedRetentionLimit.value) {
    const accepted = await confirm({
      title: t('agentSessions.retention.confirmTitle'),
      description: t('agentSessions.retention.confirmDescription', {
        count: nextLimit,
      }),
      confirmLabel: t('common.save'),
      cancelLabel: t('common.cancel'),
      dangerous: true,
    })
    if (!accepted) {
      retentionSaving.value = false
      return
    }
  }
  try {
    const saved = (await api.updateAgentSessionRetention(nextLimit)).retention_limit
    retentionLimit.value = saved
    savedRetentionLimit.value = saved
    notify({ tone: 'success', title: t('agentSessions.retention.saved') })
    await sessionTable.value?.reloadFirst()
  } catch (error) {
    retentionError.value = managementError.describe(error).display
  } finally {
    retentionSaving.value = false
  }
}

async function loadDetail(sessionId: string): Promise<void> {
  const sequence = ++detailSequence
  detailLoading.value = true
  detailError.value = ''
  try {
    const loaded = await api.getAgentSessionTimeline(sessionId)
    if (sequence === detailSequence && detailSessionId.value === sessionId) detail.value = loaded
  } catch (error) {
    if (sequence === detailSequence && detailSessionId.value === sessionId) {
      detail.value = null
      detailError.value = managementError.describe(error).display
    }
  } finally {
    if (sequence === detailSequence && detailSessionId.value === sessionId) {
      detailLoading.value = false
    }
  }
}

function showDetail(sessionId: string): void {
  detailSessionId.value = sessionId
  detail.value = null
  expandedStepIds.value = new Set()
  stepJson.value = {}
  stepLoading.value = {}
  stepErrors.value = {}
  void loadDetail(sessionId)
}

function closeDetail(): void {
  detailSequence += 1
  detailSessionId.value = null
  detail.value = null
  detailLoading.value = false
  detailError.value = ''
  expandedStepIds.value = new Set()
  stepJson.value = {}
  stepLoading.value = {}
  stepErrors.value = {}
}

function isStepExpanded(entry: SessionTimelineEntry): boolean {
  return expandedStepIds.value.has(entry.id)
}

async function loadStep(entry: SessionTimelineEntry): Promise<void> {
  const sessionId = detailSessionId.value
  if (!sessionId) return
  stepLoading.value = { ...stepLoading.value, [entry.id]: true }
  stepErrors.value = { ...stepErrors.value, [entry.id]: '' }
  try {
    const loaded = await api.getAgentSessionStep(sessionId, entry.run.id, entry.stepId)
    if (detailSessionId.value !== sessionId) return
    stepJson.value = {
      ...stepJson.value,
      [entry.id]: JSON.stringify(loaded, null, 2),
    }
  } catch (error) {
    if (detailSessionId.value !== sessionId) return
    stepErrors.value = {
      ...stepErrors.value,
      [entry.id]: managementError.describe(error).display,
    }
  } finally {
    if (detailSessionId.value === sessionId) {
      stepLoading.value = { ...stepLoading.value, [entry.id]: false }
    }
  }
}

function toggleStep(entry: SessionTimelineEntry): void {
  const next = new Set(expandedStepIds.value)
  if (next.has(entry.id)) {
    next.delete(entry.id)
  } else {
    next.add(entry.id)
    if (!stepJson.value[entry.id] && !stepLoading.value[entry.id]) void loadStep(entry)
  }
  expandedStepIds.value = next
}

async function downloadSession(row: AgentSessionSummary): Promise<void> {
  const session = await api.getAgentSession(row.session_id)
  const safeId = row.session_id.replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 120) || 'session'
  const blob = new Blob([JSON.stringify(session, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  triggerBrowserDownload(blob, `agent-session-${safeId}.json`)
}

function filterText(value: DataTableFilterValue | undefined): string {
  return typeof value === 'string' ? value : ''
}

function deletedCount(result: unknown): number {
  if (!result || typeof result !== 'object' || !('deleted' in result)) return 0
  return Number((result as { deleted: unknown }).deleted) || 0
}

const sessionTableConfig: DataTableConfig<AgentSessionSummary> = {
  id: 'agent-sessions',
  title: () => t('agentSessions.listTitle'),
  ariaLabel: () => t('agentSessions.pagination.ariaLabel'),
  emptyMessage: () => t('agentSessions.empty'),
  loadErrorTitle: () => t('agentSessions.loadFailed'),
  rowKey: (row) => row.session_id,
  provider: {
    mode: 'numbered',
    load: async (request) => {
      const status = filterText(request.filters.status) as TerminalStatus | ''
      const response = await api.listAgentSessions({
        page: request.page,
        page_size: request.pageSize,
        query: request.query,
        agent: filterText(request.filters.agent),
        ...(status ? { status } : {}),
      })
      return { rows: response.items, total: response.total }
    },
  },
  search: {
    label: () => t('agentSessions.filters.query'),
    placeholder: () => t('agentSessions.filters.query'),
  },
  filters: [
    {
      key: 'agent',
      kind: 'text',
      label: () => t('agentSessions.filters.agent'),
    },
    {
      key: 'status',
      kind: 'single',
      label: () => t('agentSessions.filters.status'),
      options: (['completed', 'failed', 'client_disconnected'] as const).map((status) => ({
        value: status,
        label: () => statusLabel(status),
      })),
    },
  ],
  columns: [
    { key: 'updatedAt', label: () => t('agentSessions.fields.updatedAt'), value: (row) => formatTime(row.updated_at) },
    { key: 'agent', label: () => t('agentSessions.fields.agent'), value: (row) => row.agent_name || t('common.notAvailable') },
    { key: 'modelCalls', label: () => t('agentSessions.fields.modelCallCount'), value: (row) => row.model_call_count },
  ],
  rowActions: [
    {
      key: 'show-session',
      label: () => t('common.view'),
      tone: 'info',
      run: (row) => showDetail(row.session_id),
    },
    {
      key: 'download-session',
      label: () => t('agentSessions.download'),
      tone: 'info',
      run: downloadSession,
      failureTitle: () => t('agentSessions.downloadFailed'),
    },
    {
      key: 'delete-session',
      label: () => t('common.delete'),
      busyLabel: () => t('common.deleting'),
      tone: 'danger',
      confirm: (row) => ({
        title: t('agentSessions.delete.title'),
        description: t('agentSessions.delete.description', { id: row.session_id }),
        confirmLabel: t('common.delete'),
        cancelLabel: t('common.cancel'),
        dangerous: true,
      }),
      run: async (row) => {
        await api.deleteAgentSession(row.session_id)
        if (detailSessionId.value === row.session_id) closeDetail()
      },
      successTitle: () => t('agentSessions.delete.succeeded'),
      failureTitle: () => t('agentSessions.delete.failed'),
      reloadAfter: 'first',
    },
  ],
  bulkAction: {
    label: () => t('agentSessions.deleteFiltered.action'),
    busyLabel: () => t('common.deleting'),
    enabled: (context) => context.hasAppliedFilters && context.total > 0,
    confirm: (context) => ({
      title: t('agentSessions.deleteFiltered.title'),
      description: t('agentSessions.deleteFiltered.description', { count: context.total }),
      confirmLabel: t('common.delete'),
      cancelLabel: t('common.cancel'),
      dangerous: true,
    }),
    run: async (context) => {
      const result = await api.deleteMatchingAgentSessions({
        query: context.applied.query,
        agent: filterText(context.applied.filters.agent),
        status: filterText(context.applied.filters.status) as TerminalStatus | '',
      })
      closeDetail()
      return result
    },
    successTitle: (result) => t('agentSessions.deleteFiltered.succeeded', { count: deletedCount(result) }),
    failureTitle: () => t('agentSessions.deleteFiltered.failed'),
  },
  pageSize: 20,
  pageSizeOptions: [20, 50, 100],
}

function formatTime(value: string | null | undefined): string {
  if (!value) return t('common.notAvailable')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(locale.value, {
    dateStyle: 'medium',
    timeStyle: 'medium',
    hour12: false,
  }).format(date)
}

function statusLabel(value: TerminalStatus): string {
  return t(`agentSessions.status.${value}`)
}

function formatTokenCount(value: number | null): string {
  if (value === null) return t('agentSessions.detail.tokenUsageUnreported')
  return t('agentSessions.detail.tokenCount', {
    count: new Intl.NumberFormat(locale.value).format(value),
  })
}

function textValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function numberValue(value: unknown): number {
  return typeof value === 'number' ? value : 0
}

function compactText(value: unknown, limit = 96): string {
  const normalized = textValue(value).replace(/\s+/g, ' ').trim()
  return normalized.length > limit ? `${normalized.slice(0, limit)}…` : normalized
}

function modelName(entry: SessionTimelineEntry): string {
  const name = textValue(entry.data.model_name)
  if (name) return name
  return entry.run.model || t('common.notAvailable')
}

function sequenceLabel(entry: SessionTimelineEntry): string {
  return entry.modelRequestNumber === null
    ? t('agentSessions.timeline.requestExecution')
    : t('agentSessions.timeline.modelRequestSequence', { number: entry.modelRequestNumber })
}

function summarySuffix(key: 'arguments' | 'result' | 'response', value: unknown): string {
  const summary = compactText(value)
  return summary ? t(`agentSessions.timeline.${key}Summary`, { summary }) : ''
}

function timelineTitle(entry: SessionTimelineEntry): string {
  const sequence = sequenceLabel(entry)
  const tool = textValue(entry.data.tool_name) || t('agentSessions.timeline.unknownTool')
  switch (entry.kind) {
    case 'request_input':
      return t('agentSessions.timeline.requestInputTitle', {
        agent: entry.run.agent_name,
        requestId: entry.run.request_id,
        count: entry.run.input_message_count,
      })
    case 'agent_input':
      return t('agentSessions.timeline.agentInputTitle', {
        agent: textValue(entry.data.agent_name) || entry.run.agent_name,
        messages: numberValue(entry.data.message_count),
        tags: numberValue(entry.data.matched_tag_count),
        startup: numberValue(entry.data.startup_message_count),
      })
    case 'model_request':
      return t('agentSessions.timeline.modelRequestTitle', {
        sequence,
        agent: textValue(entry.data.agent_name) || entry.run.agent_name,
        model: modelName(entry),
        messages: numberValue(entry.data.message_count),
        tools: numberValue(entry.data.tool_count),
      })
    case 'model_response':
      return t('agentSessions.timeline.modelResponseTitle', {
        sequence,
        agent: textValue(entry.data.agent_name) || entry.run.agent_name,
        reason: textValue(entry.data.provider_finish_reason) || t('common.notAvailable'),
        input: numberValue(entry.data.input_tokens),
        output: numberValue(entry.data.output_tokens),
      })
    case 'tool_call':
      return t('agentSessions.timeline.toolCallTitle', { sequence, tool })
    case 'tool_result':
      return t('agentSessions.timeline.toolResultTitle', { sequence, tool })
    case 'tool_error':
      return t('agentSessions.timeline.toolErrorTitle', { sequence, tool })
    case 'subagent': {
      const phase = textValue(entry.data.phase)
      const subagent = textValue(entry.data.subagent_name) || t('agentSessions.timeline.unknownSubagent')
      const state = phase === 'start' ? 'started' : phase === 'error' ? 'failed' : 'finished'
      return t(`agentSessions.timeline.subagent.${state}`, { sequence, subagent })
    }
    case 'request_output':
      if (entry.run.status === 'failed') {
        return t('agentSessions.timeline.requestFailedTitle', {
          sequence,
          code: entry.run.error_code || t('common.notAvailable'),
        })
      }
      if (entry.run.status === 'client_disconnected') {
        return t('agentSessions.timeline.requestDisconnectedTitle', { sequence })
      }
      return t('agentSessions.timeline.requestCompletedTitle', {
        sequence,
        agent: entry.run.agent_name,
        summary: summarySuffix('response', entry.run.response_summary),
      })
  }
}

const timelineEntries = computed(() => detail.value ? buildSessionTimeline(detail.value) : [])
const sessionAgents = computed(() => [
  ...new Set((detail.value?.runs ?? []).map((run) => run.agent_name).filter(Boolean)),
].join(t('common.detailSeparator')))
const sessionModels = computed(() => [
  ...new Set((detail.value?.runs ?? []).map((run) => run.model).filter(Boolean)),
].join(t('common.detailSeparator')))
const sessionModelRequestCount = computed(() => timelineEntries.value.filter(
  (entry) => entry.kind === 'model_request',
).length)
const sessionStatus = computed(() => detail.value?.runs[detail.value.runs.length - 1]?.status ?? null)

function onManagementEvent(event: ManagementEvent): void {
  if (event.type !== 'agent_session_changed') return
  void sessionTable.value?.reload()
  if (detailSessionId.value === event.session_id) void loadDetail(event.session_id)
}

useManagementEvents(
  onManagementEvent,
  api,
  () => {
    void Promise.all([
      sessionTable.value?.reload(),
      loadRetention(),
      ...(detailSessionId.value ? [loadDetail(detailSessionId.value)] : []),
    ])
  },
)

onMounted(() => {
  void loadRetention()
})
</script>

<template>
  <PageShell>
    <LteCard class="mb-3" :title="t('agentSessions.retention.title')">
      <form
        class="col-lg-6"
        data-testid="retention-form"
        @submit.prevent="saveRetention"
      >
          <label class="form-label" for="session-retention">{{ t('agentSessions.retention.label') }}</label>
          <div class="input-group">
            <input
              id="session-retention"
              v-model.number="retentionLimit"
              class="form-control"
              max="10000"
              min="1"
              required
              step="1"
              type="number"
            >
            <LteButton :disabled="retentionSaving" theme="primary" type="submit">
              <span v-if="retentionSaving" class="spinner-border spinner-border-sm" aria-hidden="true" />
              {{ t('common.save') }}
            </LteButton>
          </div>
          <LteAlert
            v-if="retentionError"
            class="mt-3"
            data-testid="retention-error"
            :title="t('agentSessions.retention.saveFailed')"
            theme="danger"
          >
            {{ retentionError }}
          </LteAlert>
      </form>
    </LteCard>

    <DataTableWorkbench ref="sessionTable" :config="sessionTableConfig" />
  </PageShell>

  <ModalHost
    :open="detailSessionId !== null"
    size="wide"
    :title="t('agentSessions.detail.title')"
    @close="closeDetail"
  >
    <div v-if="detailLoading" class="d-flex align-items-center gap-2 p-3" role="status">
      <span class="spinner-border" aria-hidden="true" />
      <span>{{ t('common.loading') }}</span>
    </div>
    <div v-else-if="detailError" data-testid="detail-error" role="alert">
      <LteAlert :title="t('agentSessions.loadFailed')" theme="danger">{{ detailError }}</LteAlert>
      <LteButton v-if="detailSessionId" theme="info" type="button" @click="loadDetail(detailSessionId)">
        {{ t('common.retry') }}
      </LteButton>
    </div>
    <div v-else-if="detail">
      <LteCard v-if="detail.runs.length" class="mb-3" :title="t('agentSessions.detail.overviewTitle')">
        <dl class="row g-3">
          <div class="col-md-6"><dt>{{ t('agentSessions.fields.agent') }}</dt><dd>{{ sessionAgents || t('common.notAvailable') }}</dd></div>
          <div class="col-md-6"><dt>{{ t('agentSessions.fields.model') }}</dt><dd class="font-monospace text-break">{{ sessionModels || t('common.notAvailable') }}</dd></div>
          <div class="col-md-6"><dt>{{ t('agentSessions.fields.startedAt') }}</dt><dd>{{ formatTime(detail.runs[0]?.started_at) }}</dd></div>
          <div class="col-md-6"><dt>{{ t('agentSessions.fields.finishedAt') }}</dt><dd>{{ formatTime(detail.runs[detail.runs.length - 1]?.finished_at) }}</dd></div>
          <div class="col-md-6"><dt>{{ t('agentSessions.fields.requestCount') }}</dt><dd>{{ detail.runs.length }}</dd></div>
          <div class="col-md-6"><dt>{{ t('agentSessions.fields.modelCallCount') }}</dt><dd>{{ sessionModelRequestCount }}</dd></div>
          <div class="col-md-6" data-testid="session-input-tokens">
            <dt>{{ t('agentSessions.fields.inputTokens') }}</dt>
            <dd>{{ formatTokenCount(detail.token_usage.input_tokens) }}</dd>
          </div>
          <div class="col-md-6" data-testid="session-output-content-tokens">
            <dt>{{ t('agentSessions.fields.outputContentTokens') }}</dt>
            <dd>{{ formatTokenCount(detail.token_usage.non_reasoning_output_tokens) }}</dd>
          </div>
          <div class="col-md-6" data-testid="session-output-reasoning-tokens">
            <dt>{{ t('agentSessions.fields.outputReasoningTokens') }}</dt>
            <dd>{{ formatTokenCount(detail.token_usage.reasoning_output_tokens) }}</dd>
          </div>
          <div v-if="sessionStatus" class="col-md-6">
            <dt>{{ t('agentSessions.fields.status') }}</dt>
            <dd>
              <span v-if="sessionStatus === 'failed'" class="badge text-bg-danger">{{ statusLabel(sessionStatus) }}</span>
              <span v-else-if="sessionStatus === 'client_disconnected'" class="badge text-bg-warning">{{ statusLabel(sessionStatus) }}</span>
              <span v-else>{{ statusLabel(sessionStatus) }}</span>
            </dd>
          </div>
        </dl>
      </LteCard>

      <h4 class="h5 fw-semibold">{{ t('agentSessions.timeline.title') }}</h4>
      <div v-if="timelineEntries.length" class="timeline" data-testid="session-timeline">
        <div v-for="entry in timelineEntries" :key="entry.id" data-testid="timeline-step">
          <i
            v-if="entry.kind === 'agent_input' || entry.kind === 'model_request' || entry.kind === 'model_response' || entry.kind === 'subagent'"
            class="bi bi-robot bg-primary"
            aria-hidden="true"
          />
          <i
            v-else-if="entry.kind === 'tool_call'"
            class="bi bi-gear bg-info"
            aria-hidden="true"
          />
          <i
            v-else-if="entry.kind === 'tool_error' || (entry.kind === 'request_output' && entry.run.status === 'failed')"
            class="bi bi-x-circle bg-danger"
            aria-hidden="true"
          />
          <i
            v-else-if="entry.kind === 'tool_result' || (entry.kind === 'request_output' && entry.run.status === 'completed')"
            class="bi bi-check-circle bg-success"
            aria-hidden="true"
          />
          <i
            v-else-if="entry.kind === 'request_output' && entry.run.status === 'client_disconnected'"
            class="bi bi-info-circle bg-warning"
            aria-hidden="true"
          />
          <i v-else class="bi bi-info-circle bg-info" aria-hidden="true" />
          <div class="timeline-item">
            <span class="time">{{ formatTime(entry.timestamp) }}</span>
            <h3 class="timeline-header">{{ timelineTitle(entry) }}</h3>
            <div class="timeline-footer">
              <LteButton
                :data-step-id="entry.id"
                size="sm"
                theme="info"
                type="button"
                @click="toggleStep(entry)"
              >
                {{ isStepExpanded(entry) ? t('agentSessions.timeline.hideJson') : t('agentSessions.timeline.viewJson') }}
              </LteButton>
            </div>
            <div v-if="isStepExpanded(entry)" class="timeline-body">
              <div v-if="stepLoading[entry.id]" class="d-flex align-items-center gap-2" role="status">
                <span class="spinner-border spinner-border-sm" aria-hidden="true" />
                <span>{{ t('common.loading') }}</span>
              </div>
              <div v-else-if="stepErrors[entry.id]" role="alert">
                <LteAlert :title="t('agentSessions.timeline.jsonLoadFailed')" theme="danger">
                  {{ stepErrors[entry.id] }}
                </LteAlert>
                <LteButton size="sm" theme="info" type="button" @click="loadStep(entry)">
                  {{ t('common.retry') }}
                </LteButton>
              </div>
              <template v-else>
                <label class="visually-hidden" :for="`timeline-json-${entry.id}`">
                  {{ t('agentSessions.timeline.jsonLabel') }}
                </label>
                <textarea
                  :id="`timeline-json-${entry.id}`"
                  class="form-control font-monospace session-timeline-json"
                  data-testid="timeline-step-json"
                  readonly
                  :value="stepJson[entry.id]"
                  wrap="off"
                />
              </template>
            </div>
          </div>
        </div>
      </div>
      <p v-else class="text-center text-body-secondary p-3">
        {{ t('agentSessions.detail.emptyRuns') }}
      </p>
    </div>
  </ModalHost>
</template>
