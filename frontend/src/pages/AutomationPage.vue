<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { managementApi, type AutomationScriptResource } from '@/api'
import PageShell from '@/components/PageShell.vue'
import { useManagementError } from '@/composables/useManagementError'

const { t } = useI18n()
const managementError = useManagementError()
const plugins = ref<AutomationScriptResource[]>([])
const pluginErrors = ref<Record<string, unknown>>({})
const loading = ref(true)
const pageError = ref('')

const dependencyFailureCount = computed(() => plugins.value.filter(
  (plugin) => plugin.dependency_status === 'failed',
).length)
const dependencyRestartCount = computed(() => plugins.value.filter(
  (plugin) => plugin.dependency_status === 'restart_required',
).length)

function statusLabel(plugin: AutomationScriptResource): string {
  if (plugin.dependency_status === 'failed') return t('automation.scripts.status.failed')
  if (plugin.dependency_status === 'restart_required') {
    return t('automation.scripts.status.restartRequired')
  }
  return t('automation.scripts.status.ready')
}

async function load(): Promise<void> {
  loading.value = true
  pageError.value = ''
  try {
    const catalog = await managementApi.listAutomationPlugins()
    plugins.value = catalog.catalog
    pluginErrors.value = catalog.errors
  } catch (error) {
    pageError.value = managementError.describe(error).display
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton
        :aria-label="t('common.refresh')"
        :disabled="loading"
        :title="t('common.refresh')"
        theme="primary"
        type="button"
        @click="load"
      >
        <i class="bi bi-arrow-clockwise" aria-hidden="true" />
      </LteButton>
    </template>

    <template #status>
      <LteAlert v-if="pageError" theme="danger" :title="pageError" />
      <LteAlert
        v-else-if="Object.keys(pluginErrors).length"
        theme="warning"
        :title="t('automation.scripts.invalid', { count: Object.keys(pluginErrors).length })"
      />
      <LteAlert
        v-else-if="dependencyFailureCount"
        theme="danger"
        :title="t('automation.scripts.dependenciesFailed', { count: dependencyFailureCount })"
      />
      <LteAlert
        v-else-if="dependencyRestartCount"
        theme="warning"
        :title="t('automation.scripts.dependenciesRestartRequired', { count: dependencyRestartCount })"
      />
    </template>

    <section class="card">
      <header class="card-header">
        <h2 class="card-title mb-0">{{ t('automation.plugins.title') }}</h2>
      </header>
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead>
            <tr>
              <th scope="col">{{ t('fields.name') }}</th>
              <th scope="col">{{ t('automation.plugins.entrypoints') }}</th>
              <th scope="col">{{ t('automation.plugins.requirements') }}</th>
              <th scope="col">{{ t('automation.plugins.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="plugin in plugins" :key="plugin.id">
              <td>
                <div class="fw-semibold">{{ plugin.name }}</div>
                <div class="small font-monospace text-body-secondary">{{ plugin.id }}</div>
                <div v-if="plugin.description" class="small text-body-secondary">{{ plugin.description }}</div>
              </td>
              <td>{{ plugin.entrypoints.map((item) => t(`automation.entrypoints.${item}`)).join(', ') }}</td>
              <td class="small font-monospace">
                {{ plugin.python_requirements.length ? plugin.python_requirements.join(', ') : t('common.none') }}
              </td>
              <td>
                <span v-if="plugin.dependency_status === 'failed'" class="badge text-bg-danger">
                  {{ statusLabel(plugin) }}
                </span>
                <span v-else-if="plugin.dependency_status === 'restart_required'" class="badge text-bg-warning">
                  {{ statusLabel(plugin) }}
                </span>
                <span v-else class="badge text-bg-success">{{ statusLabel(plugin) }}</span>
              </td>
            </tr>
            <tr v-if="!loading && !plugins.length">
              <td class="text-center text-body-secondary" colspan="4">{{ t('automation.plugins.empty') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </PageShell>
</template>
