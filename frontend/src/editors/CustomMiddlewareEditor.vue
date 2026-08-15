<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import type { LocalizedMessagePayload } from '@/api'
import PythonPackageConfigForm from '@/components/PythonPackageConfigForm.vue'
import {
  createMiddlewareEntry,
  type CustomMiddlewareCatalogItem,
  type CustomMiddlewareDraft,
} from '@/domain/blocks'
import { pythonPackageConfigDefaults } from '@/domain/pythonPackageConfigSchema'

import { useEditorModel } from './shared/useEditorModel'

const props = withDefaults(defineProps<{
  modelValue: CustomMiddlewareDraft
  catalog?: CustomMiddlewareCatalogItem[]
  errors?: Record<string, LocalizedMessagePayload>
  loading?: boolean
}>(), {
  catalog: () => [],
  errors: () => ({}),
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: CustomMiddlewareDraft]
  refresh: []
}>()

const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

function addPackage(): void {
  draft.python_package_bindings.push(createMiddlewareEntry())
}

function move(index: number, delta: number): void {
  const target = index + delta
  if (target < 0 || target >= draft.python_package_bindings.length) return
  const moved = draft.python_package_bindings.splice(index, 1)[0]
  if (moved) draft.python_package_bindings.splice(target, 0, moved)
}

function selectedPackage(packageId: string): CustomMiddlewareCatalogItem | undefined {
  return props.catalog.find((item) => item.id === packageId)
}

function selectPackage(index: number, packageId: string): void {
  const selected = selectedPackage(packageId)
  const entry = draft.python_package_bindings[index]
  if (!entry) return
  entry.package_id = packageId
  entry.config = selected ? pythonPackageConfigDefaults(selected.config_schema) : {}
}

function packageLabel(item: CustomMiddlewareCatalogItem): string {
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
  <div data-editor="custom-middleware">
    <div class="d-flex align-items-center justify-content-between gap-2 mb-3">
      <h3 class="h5 fw-semibold mb-0">{{ t('editors.customMiddleware.entriesTitle') }}</h3>
      <div class="d-flex gap-2 ms-auto">
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
        <LteButton
          :aria-label="t('editors.customMiddleware.add')"
          size="sm"
          theme="success"
          type="button"
          @click="addPackage"
        >
          <i class="bi bi-plus-lg" aria-hidden="true" />
        </LteButton>
      </div>
    </div>

    <div v-if="draft.python_package_bindings.length" class="list-group list-group-flush">
      <div v-for="(entry, index) in draft.python_package_bindings" :key="entry._key" class="list-group-item">
        <div class="row g-3 align-items-end">
          <div class="col-12 col-lg-8">
            <label class="form-label" :for="`middleware-package-${entry._key}`">
              {{ t('editors.customMiddleware.package') }}
            </label>
            <select
              :id="`middleware-package-${entry._key}`"
              class="form-select"
              :value="entry.package_id"
              @change="selectPackage(index, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">{{ t('agents.capability.notAttached') }}</option>
              <option v-for="item in catalog" :key="item.id" :value="item.id">
                {{ packageLabel(item) }}
              </option>
            </select>
          </div>
          <div class="col-12 col-lg-4">
            <div class="d-flex align-items-center gap-2">
              <div class="form-check form-switch">
                <input
                  :id="`middleware-enabled-${entry._key}`"
                  v-model="entry.enabled"
                  class="form-check-input"
                  type="checkbox"
                >
                <label class="visually-hidden" :for="`middleware-enabled-${entry._key}`">
                  {{ t('editors.common.enabled') }}
                </label>
              </div>
              <LteButton
                :aria-label="t('editors.common.moveUp')"
                :disabled="index === 0"
                size="sm"
                theme="secondary"
                type="button"
                @click="move(index, -1)"
              ><i class="bi bi-arrow-up" aria-hidden="true" /></LteButton>
              <LteButton
                :aria-label="t('editors.common.moveDown')"
                :disabled="index === draft.python_package_bindings.length - 1"
                size="sm"
                theme="secondary"
                type="button"
                @click="move(index, 1)"
              ><i class="bi bi-arrow-down" aria-hidden="true" /></LteButton>
              <LteButton
                :aria-label="t('editors.common.remove')"
                size="sm"
                theme="danger"
                type="button"
                @click="draft.python_package_bindings.splice(index, 1)"
              ><i class="bi bi-trash" aria-hidden="true" /></LteButton>
            </div>
          </div>
          <div v-if="selectedPackage(entry.package_id)" class="col-12">
            <PythonPackageConfigForm
              :id-prefix="`middleware-config-${entry._key}`"
              v-model="entry.config"
              :schema="selectedPackage(entry.package_id)!.config_schema"
            />
          </div>
        </div>
      </div>
    </div>
    <p v-else class="text-body-secondary mb-0">{{ t('editors.customMiddleware.empty') }}</p>
    <div v-if="Object.keys(errors).length" class="alert alert-danger mt-3 mb-0" role="alert">
      <p v-for="(error, folder) in errors" :key="folder" class="mb-1">
        <strong>{{ folder }}</strong> {{ resourceError(error) }}
      </p>
    </div>
  </div>
</template>
