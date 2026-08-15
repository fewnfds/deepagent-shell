<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import type { LocalizedMessagePayload } from '@/api'
import PythonPackageConfigForm from '@/components/PythonPackageConfigForm.vue'
import {
  type ConditionRouterCatalogItem,
  type ConditionRouterDefaults,
  type ConditionRouterDraft,
} from '@/domain/blocks'
import { pythonPackageConfigDefaults } from '@/domain/pythonPackageConfigSchema'
import { useEditorModel } from './shared/useEditorModel'

const props = withDefaults(defineProps<{
  modelValue: ConditionRouterDraft
  defaults?: ConditionRouterDefaults
  catalog?: ConditionRouterCatalogItem[]
  errors?: Record<string, LocalizedMessagePayload>
  loading?: boolean
}>(), {
  catalog: () => [],
  errors: () => ({}),
  loading: false,
})
const emit = defineEmits<{
  'update:modelValue': [value: ConditionRouterDraft]
  refresh: []
}>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

function selectedPackage(): ConditionRouterCatalogItem | undefined {
  const packageId = draft.python_package_bindings[0]?.package_id ?? ''
  return props.catalog.find((item) => item.id === packageId)
}

function selectPackage(packageId: string): void {
  const selected = props.catalog.find((item) => item.id === packageId)
  draft.python_package_bindings = selected ? [{
    package_id: packageId,
    enabled: true,
    config: pythonPackageConfigDefaults(selected.config_schema),
  }] : []
}

function packageLabel(item: ConditionRouterCatalogItem): string {
  const status = item.dependency_status === 'ready'
    ? ''
    : ` - ${t(`editors.pythonPackage.status.${item.dependency_status}`)}`
  return `${item.name} (${item.id})${status}`
}

function resourceError(error: LocalizedMessagePayload): string {
  return t(error.message_key, error.message_args)
}
</script>

<template>
  <div data-editor="condition-router">
    <section class="card mb-3">
      <header class="card-header d-flex align-items-center justify-content-between gap-2">
        <h3 class="card-title h5 mb-0">{{ t('editors.conditionRouter.packageTitle') }}</h3>
        <LteButton
          :aria-label="t('editors.common.refresh')"
          :disabled="loading"
          size="sm"
          theme="info"
          type="button"
          @click="emit('refresh')"
        >
          <i class="bi bi-arrow-clockwise" aria-hidden="true" />
        </LteButton>
      </header>
      <div class="card-body">
        <label class="form-label" for="condition-router-package">
          {{ t('editors.conditionRouter.package') }}
        </label>
        <select
          id="condition-router-package"
          class="form-select"
          :value="draft.python_package_bindings[0]?.package_id ?? ''"
          @change="selectPackage(($event.target as HTMLSelectElement).value)"
        >
          <option value="">{{ t('agents.capability.notAttached') }}</option>
          <option v-for="item in catalog" :key="item.id" :value="item.id">
            {{ packageLabel(item) }}
          </option>
        </select>
        <div v-if="selectedPackage()" class="mt-3">
          <PythonPackageConfigForm
            id-prefix="condition-router-config"
            v-model="draft.python_package_bindings[0]!.config"
            :schema="selectedPackage()!.config_schema"
          />
        </div>
      </div>
      <div v-if="Object.keys(errors).length" class="card-body">
        <div class="alert alert-danger mb-0" role="alert">
          <p v-for="(error, folder) in errors" :key="folder" class="mb-1">
            <strong>{{ folder }}</strong> {{ resourceError(error) }}
          </p>
        </div>
      </div>
    </section>
  </div>
</template>
