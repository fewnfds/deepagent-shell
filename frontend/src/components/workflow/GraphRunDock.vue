<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { managementApi, watchManagementEvents, type GraphRun, type ManagementEvent } from '@/api'
import { useManagementError } from '@/composables/useManagementError'

const props = defineProps<{ graphId: string; entryScriptId?: string; statuses: Record<string, string> }>()
const emit = defineEmits<{ status: [nodeId: string, value: string]; reset: []; activity: [active: boolean] }>()
const { t } = useI18n()
const managementError = useManagementError()
const input = ref('hello')
const run = ref<GraphRun | null>(null)
const error = ref('')
const output = ref<Record<string, unknown>[]>([])
const expanded = ref(false)
let stopStream: (() => void) | null = null

const active = computed(() => Boolean(run.value && ['queued', 'running', 'paused'].includes(run.value.status)))
const status = computed(() => run.value?.status ?? 'idle')

async function start(): Promise<void> {
  error.value = ''
  output.value = []
  emit('reset')
  try {
    run.value = await managementApi.startGraphRun(props.graphId, [{ role: 'user', content: input.value }], props.entryScriptId)
    emit('activity', true)
    subscribe()
  } catch (cause) {
    error.value = managementError.describe(cause).display
  }
}

function subscribe(): void {
  if (!run.value) return
  stopStream?.()
  stopStream = watchManagementEvents(`/api/graph-runs/${encodeURIComponent(run.value.id)}/events`, (event: ManagementEvent) => {
    const payload = event as Record<string, unknown>
    if ((payload.event === 'node_update' || payload.event === 'node_started' || payload.event === 'node_completed') && typeof payload.node_id === 'string') {
      const update = payload.update as Record<string, unknown> | undefined
      const rawStatus = payload.event === 'node_started' ? 'running' : String(payload.status ?? update?.status ?? 'completed')
      const normalized = rawStatus === 'success' || rawStatus === 'command' ? 'completed' : rawStatus
      emit('status', payload.node_id, normalized)
    }
    if (payload.event === 'state' && payload.state && typeof payload.state === 'object') output.value.push(payload.state as Record<string, unknown>)
    if (payload.event === 'completed' || payload.event === 'failed' || payload.event === 'cancelled') {
      emit('activity', false)
      void refresh()
      stopStream?.()
      stopStream = null
    }
  }, { onError: (cause) => { error.value = managementError.describe(cause).display } })
}

async function refresh(): Promise<void> {
  if (!run.value) return
  try { run.value = await managementApi.getGraphRun(run.value.id) } catch (cause) { error.value = managementError.describe(cause).display }
}

async function control(action: 'pause' | 'resume' | 'cancel'): Promise<void> {
  if (!run.value) return
  try {
    run.value = action === 'pause'
      ? await managementApi.pauseGraphRun(run.value.id)
      : action === 'resume'
        ? await managementApi.resumeGraphRun(run.value.id)
        : await managementApi.cancelGraphRun(run.value.id)
    emit('activity', run.value.status === 'queued' || run.value.status === 'running' || run.value.status === 'paused')
    if (action === 'resume' && !stopStream) subscribe()
  } catch (cause) { error.value = managementError.describe(cause).display }
}

onBeforeUnmount(() => stopStream?.())

defineExpose({ start })
</script>

<template>
  <section class="run-dock" :data-expanded="expanded || undefined">
    <div class="run-dock__summary">
      <div class="run-dock__identity"><span class="run-dock__eyebrow">GRAPH RUN</span><strong>{{ status }}</strong><span v-if="run" class="font-monospace">{{ run.id }}</span></div>
      <div class="run-dock__actions">
        <button class="btn btn-sm btn-outline-secondary" type="button" @click="expanded = !expanded">{{ expanded ? '收起' : '展开运行面板' }}</button>
        <button class="btn btn-sm btn-success" type="button" :disabled="active || !graphId" @click="void start"><i class="bi bi-play-fill" aria-hidden="true" /> {{ t('workflow.run') }}</button>
        <button v-if="run?.status === 'running'" class="btn btn-sm btn-warning" type="button" @click="void control('pause')">暂停</button>
        <button v-if="run?.status === 'paused'" class="btn btn-sm btn-primary" type="button" @click="void control('resume')">继续</button>
        <button v-if="active" class="btn btn-sm btn-danger" type="button" @click="void control('cancel')">停止</button>
      </div>
    </div>
    <div v-if="expanded" class="run-dock__body">
      <div class="run-dock__input"><label class="form-label" for="graph-run-input">{{ t('workflow.runInput') }}</label><textarea id="graph-run-input" v-model="input" class="form-control form-control-sm" rows="2" /></div>
      <p v-if="error" class="text-danger small mb-2">{{ error }}</p>
      <div v-if="output.length" class="run-dock__state"><span class="small text-body-secondary">最新 State 快照</span><pre class="font-monospace mb-0"><code>{{ JSON.stringify(output.at(-1), null, 2) }}</code></pre></div>
      <div v-if="run" class="run-dock__meta small text-body-secondary">thread: {{ run.thread_id }} · updated: {{ run.updated_at }}</div>
    </div>
  </section>
</template>
