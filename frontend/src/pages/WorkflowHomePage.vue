<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { managementApi, type Workflow } from '@/api'
import PageShell from '@/components/PageShell.vue'
import { useManagementError } from '@/composables/useManagementError'

const { t } = useI18n()
const router = useRouter()
const managementError = useManagementError()
const workflows = ref<Workflow[]>([])
const loading = ref(true)
const error = ref('')

async function load(): Promise<void> {
  loading.value = true
  try { workflows.value = await managementApi.listWorkflows() } catch (cause) { error.value = managementError.describe(cause).display } finally { loading.value = false }
}

function open(id: string): void { void router.push(`/workflows/${encodeURIComponent(id)}`) }
function create(): void { void router.push('/workflows/new') }

onMounted(() => { void load() })
</script>

<template>
  <PageShell>
    <template #actions><LteButton theme="secondary" type="button" @click="void router.push('/library/entry-scripts')">{{ t('workflow.entryScripts') }}</LteButton><LteButton theme="success" type="button" @click="create">{{ t('common.new') }}</LteButton></template>
    <template #status><LteAlert v-if="error" theme="danger" :title="error" /></template>
    <section class="card">
      <div class="card-header d-flex align-items-center justify-content-between"><div><h2 class="card-title h5 mb-1">{{ t('workflow.listTitle') }}</h2><p class="card-text text-body-secondary mb-0">在这里管理 Graph Definition；点击后进入独立画布。</p></div><span class="badge text-bg-secondary">{{ workflows.length }}</span></div>
      <div class="list-group list-group-flush">
        <button v-for="item in workflows" :key="item.id" class="list-group-item list-group-item-action text-start d-flex align-items-center justify-content-between" type="button" @click="open(item.id)"><span><strong class="d-block">{{ item.name || '未命名 Workflow' }}</strong><small class="font-monospace text-body-secondary">{{ item.id }}</small></span><span class="d-flex align-items-center gap-2"><span class="badge" :data-enabled="item.enabled || undefined">{{ item.enabled ? 'enabled' : 'disabled' }}</span><i class="bi bi-chevron-right" aria-hidden="true" /></span></button>
        <div v-if="!loading && !workflows.length" class="list-group-item text-body-secondary">{{ t('workflow.empty') }}</div>
        <div v-if="loading" class="list-group-item text-body-secondary">正在加载…</div>
      </div>
    </section>
  </PageShell>
</template>
