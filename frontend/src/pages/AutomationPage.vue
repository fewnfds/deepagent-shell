<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  managementApi,
  type AutomationScriptResource,
  type CapabilityManifest,
} from '@/api'
import ConfigurationLibraryNav from '@/components/ConfigurationLibraryNav.vue'
import PageShell from '@/components/PageShell.vue'
import { useManagementError } from '@/composables/useManagementError'

const { t } = useI18n()
const managementError = useManagementError()
const plugins = ref<AutomationScriptResource[]>([])
const manifests = ref<CapabilityManifest[]>([])
const pluginErrors = ref<Record<string, unknown>>({})
const loading = ref(true)
const pageError = ref('')

const dependencyFailureCount = computed(() => plugins.value.filter(
  (plugin) => plugin.dependency_status === 'failed',
).length)
const dependencyRestartCount = computed(() => plugins.value.filter(
  (plugin) => plugin.dependency_status === 'restart_required',
).length)

function dependencyLabel(plugin: AutomationScriptResource): string {
  if (plugin.dependency_status === 'ready') {
    return t('automation.dependencies.installed')
  }
  if (plugin.dependency_status === 'failed') {
    return t('automation.dependencies.notInstalledFailed')
  }
  return t('automation.dependencies.notInstalledRestartRequired')
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

async function loadNavigation(): Promise<void> {
  try {
    const catalog = await managementApi.getCatalog()
    manifests.value = [...catalog.block_types].sort((left, right) => left.order - right.order)
  } catch {
    manifests.value = []
  }
}

onMounted(() => {
  void load()
  void loadNavigation()
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

    <ConfigurationLibraryNav :manifests="manifests" />

    <section class="card">
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead class="management-table-head">
            <tr>
              <th scope="col">{{ t('fields.name') }}</th>
              <th scope="col">{{ t('automation.plugins.requirements') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="plugin in plugins" :key="plugin.id">
              <td>
                <div class="fw-semibold">{{ plugin.name }}</div>
                <div class="small font-monospace text-body-secondary">{{ plugin.id }}</div>
                <div v-if="plugin.description" class="small text-body-secondary">{{ plugin.description }}</div>
              </td>
              <td>
                <span v-if="!plugin.python_requirements.length" class="text-body-secondary">
                  {{ t('common.none') }}
                </span>
                <div v-else>
                  <div
                    v-for="requirement in plugin.python_requirements"
                    :key="requirement"
                    class="mb-1"
                  >
                    <span
                      v-if="plugin.dependency_status === 'ready'"
                      class="badge font-monospace text-bg-success"
                    >
                      {{ requirement }} · {{ dependencyLabel(plugin) }}
                    </span>
                    <span v-else class="badge font-monospace text-bg-danger">
                      {{ requirement }} · {{ dependencyLabel(plugin) }}
                    </span>
                  </div>
                </div>
              </td>
            </tr>
            <tr v-if="!loading && !plugins.length">
              <td class="text-center text-body-secondary" colspan="2">{{ t('automation.plugins.empty') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </PageShell>
</template>
