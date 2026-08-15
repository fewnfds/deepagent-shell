<script setup lang="ts">
import { LteAlert, LteButton, LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import type { LocalizedMessagePayload, PythonPackageTemplate } from '@/api'
import PythonPackageConfigForm from '@/components/PythonPackageConfigForm.vue'
import {
  applyPythonPackageTemplate,
  type PythonPackageDraftState,
} from '@/domain/blocks/pythonPackage'
import { pythonPackageConfigDefaults } from '@/domain/pythonPackageConfigSchema'
import { useEditorModel } from '@/editors/shared/useEditorModel'

const props = withDefaults(defineProps<{
  modelValue: PythonPackageDraftState
  saved: boolean
  catalog?: PythonPackageTemplate[]
  errors?: Record<string, LocalizedMessagePayload>
  loading?: boolean
  idPrefix: string
}>(), {
  catalog: () => [],
  errors: () => ({}),
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: PythonPackageDraftState]
  refresh: []
}>()

const { t } = useI18n()
const draft = useEditorModel(
  () => props.modelValue,
  (value) => emit('update:modelValue', value),
)

function selectTemplate(key: string): void {
  const selected = props.catalog.find((item) => item.key === key)
  applyPythonPackageTemplate(draft, selected)
  if (selected) {
    draft.python_package.config = pythonPackageConfigDefaults(selected.config_schema)
  }
}

function resourceError(error: LocalizedMessagePayload): string {
  return t(error.message_key, error.message_args)
}
</script>

<template>
  <section class="card mb-3">
    <header class="card-header d-flex align-items-center gap-2">
      <h3 class="card-title h5 mb-0">{{ t('editors.pythonPackage.title') }}</h3>
      <LteButton
        v-if="!saved"
        class="ms-auto"
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
      <template v-if="saved">
        <label class="form-label" :for="`${idPrefix}-folder`">
          {{ t('editors.pythonPackage.folder') }}
        </label>
        <input
          :id="`${idPrefix}-folder`"
          class="form-control font-monospace"
          :value="draft.python_package.folder"
          readonly
          type="text"
        >
      </template>
      <template v-else>
        <label class="form-label" :for="`${idPrefix}-template`">
          {{ t('editors.pythonPackage.template') }}
        </label>
        <select
          :id="`${idPrefix}-template`"
          class="form-select"
          :value="draft.python_package_files.template_key"
          @change="selectTemplate(($event.target as HTMLSelectElement).value)"
        >
          <option value="">{{ t('editors.pythonPackage.selectTemplate') }}</option>
          <option v-for="item in catalog" :key="item.key" :value="item.key">
            {{ item.name }} ({{ item.key }})
          </option>
        </select>
      </template>

      <LteAlert
        v-if="draft.python_package_error"
        class="mt-3 mb-0"
        theme="danger"
        :title="resourceError(draft.python_package_error)"
      />

      <template v-if="draft.python_package_manifest || saved">
        <div class="mt-3">
          <label class="form-label" :for="`${idPrefix}-main-source`">
            {{ t('editors.pythonPackage.mainSource') }}
          </label>
          <LteTextarea
            :id="`${idPrefix}-main-source`"
            v-model="draft.python_package_files.main_source"
            class="font-monospace"
            :rows="18"
          />
        </div>
        <div class="mt-3">
          <label class="form-label" :for="`${idPrefix}-requirements`">
            {{ t('editors.pythonPackage.requirements') }}
          </label>
          <LteTextarea
            :id="`${idPrefix}-requirements`"
            v-model="draft.python_package_files.requirements_source"
            class="font-monospace"
            :rows="5"
          />
        </div>
        <LteAlert
          v-if="saved && draft.dependency_status && draft.dependency_status !== 'ready'"
          class="mt-3 mb-0"
          theme="info"
          :title="t(`editors.pythonPackage.status.${draft.dependency_status}`)"
        />
        <div v-if="draft.python_package_manifest" class="mt-3">
          <h4 class="h5">{{ t('editors.pythonPackage.config') }}</h4>
          <PythonPackageConfigForm
            :id-prefix="`${idPrefix}-config`"
            v-model="draft.python_package.config"
            :schema="draft.python_package_manifest.config_schema"
          />
        </div>
      </template>
    </div>
    <div v-if="Object.keys(errors).length" class="card-body">
      <div class="alert alert-danger mb-0" role="alert">
        <p v-for="(error, folder) in errors" :key="folder" class="mb-1">
          <strong>{{ folder }}</strong> {{ resourceError(error) }}
        </p>
      </div>
    </div>
  </section>
</template>
