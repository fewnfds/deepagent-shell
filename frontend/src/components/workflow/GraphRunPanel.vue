<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { managementApi, watchManagementEvents, type GraphRun, type ManagementEvent } from '@/api'
import { useManagementError } from '@/composables/useManagementError'

const props = defineProps<{ graphId: string; statuses: Record<string, string>; entryScriptId?: string }>()
const emit = defineEmits<{ status: [nodeId: string, value: string]; reset: [] }>()
const { t } = useI18n()
const managementError = useManagementError()
const input = ref('hello')
const run = ref<GraphRun | null>(null)
const error = ref('')
const output = ref<Record<string, unknown>[]>([])
let stopStream: (() => void) | null = null

const active = computed(() => Boolean(run.value && ['queued', 'running', 'paused'].includes(run.value.status)))

async function start(): Promise<void> {
  error.value = ''
  output.value = []
  emit('reset')
  try {
    run.value = await managementApi.startGraphRun(props.graphId, [{ role: 'user', content: input.value }], props.entryScriptId)
    subscribe()
  } catch (cause) {
    error.value = managementError.describe(cause).display
  }
}

function subscribe(): void {
  if (!run.value) return
  stopStream?.()
  stopStream = watchManagementEvents(`/api/graph-runs/${encodeURIComponent(run.value.id)}/events`, (event: ManagementEvent) => {
    const payload = event as Record<string, any>
    if ((payload.event === 'node_update' || payload.event === 'node_started' || payload.event === 'node_completed') && typeof payload.node_id === 'string') {
      const update = payload.update as Record<string, unknown> | undefined
      const rawStatus = payload.event === 'node_started' ? 'running' : String(payload.status ?? update?.status ?? 'completed')
      const status = rawStatus === 'success' || rawStatus === 'command' ? 'completed' : rawStatus
      emit('status', payload.node_id, status)
    }
    if (payload.event === 'state' && payload.state) output.value.push(payload.state)
    if (payload.event === 'completed' || payload.event === 'failed' || payload.event === 'cancelled') {
      void refresh()
      stopStream?.()
      stopStream = null
    }
  }, { onError: (cause) => { error.value = managementError.describe(cause).display } })
}

async function refresh(): Promise<void> {
  if (!run.value) return
  try {
    run.value = await managementApi.getGraphRun(run.value.id)
  } catch (cause) {
    error.value = managementError.describe(cause).display
  }
}

async function control(action: 'pause' | 'resume' | 'cancel'): Promise<void> {
  if (!run.value) return
  try {
    run.value = action === 'pause'
      ? await managementApi.pauseGraphRun(run.value.id)
      : action === 'resume'
        ? await managementApi.resumeGraphRun(run.value.id)
        : await managementApi.cancelGraphRun(run.value.id)
    if (action === 'resume' && !stopStream) subscribe()
  } catch (cause) {
    error.value = managementError.describe(cause).display
  }
}

onBeforeUnmount(() => stopStream?.())
</script>

<template>
  <div class="card">
    <div class="card-header d-flex justify-content-between align-items-center">
      <h2 class="card-title h5 mb-0">{{ t('workflow.runTitle') }}</h2>
      <span v-if="run" class="badge text-bg-secondary">{{ run.status }}</span>
    </div>
    <div class="card-body">
      <LteAlert v-if="error" theme="danger" :title="error" />
      <label class="form-label" for="graph-run-input">{{ t('workflow.runInput') }}</label>
      <textarea id="graph-run-input" v-model="input" class="form-control mb-2" rows="3" />
      <div class="d-flex flex-wrap gap-2">
        <LteButton :disabled="active || !graphId" theme="primary" type="button" @click="void start">{{ t('workflow.run') }}</LteButton>
        <LteButton v-if="run?.status === 'running'" theme="warning" type="button" @click="void control('pause')">{{ t('workflow.pause') }}</LteButton>
        <LteButton v-if="run?.status === 'paused'" theme="success" type="button" @click="void control('resume')">{{ t('workflow.resume') }}</LteButton>
        <LteButton v-if="active" theme="danger" type="button" @click="void control('cancel')">{{ t('workflow.cancelRun') }}</LteButton>
      </div>
      <pre v-if="output.length" class="border rounded overflow-auto p-3 mt-3 mb-0"><code>{{ JSON.stringify(output.at(-1), null, 2) }}</code></pre>
    </div>
  </div>
</template>
