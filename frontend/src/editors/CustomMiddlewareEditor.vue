<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import type { LocalizedMessagePayload } from '@/api'
import MiddlewareConfigForm from '@/components/MiddlewareConfigForm.vue'
import {
  createMiddlewareEntry,
  type CustomMiddlewareCatalogItem,
  type CustomMiddlewareDraft,
} from '@/domain/blocks'
import { middlewareConfigDefaults } from '@/domain/middlewareConfigSchema'

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
  draft.middlewares.push(createMiddlewareEntry())
}

function move(index: number, delta: number): void {
  const target = index + delta
  if (target < 0 || target >= draft.middlewares.length) return
  const moved = draft.middlewares.splice(index, 1)[0]
  if (moved) draft.middlewares.splice(target, 0, moved)
}

function selectedPackage(packageId: string): CustomMiddlewareCatalogItem | undefined {
  return props.catalog.find((item) => item.id === packageId)
}

function selectPackage(index: number, packageId: string): void {
  const selected = selectedPackage(packageId)
  const entry = draft.middlewares[index]
  if (!entry) return
  entry.package_id = packageId
  entry.config = selected ? middlewareConfigDefaults(selected.config_schema) : {}
}

function packageLabel(item: CustomMiddlewareCatalogItem): string {
  const status = item.dependency_status === 'ready'
    ? ''
    : ` - ${t(`editors.customMiddleware.status.${item.dependency_status}`)}`
  return `${item.name} (${item.id})${status}`
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

    <div v-if="draft.middlewares.length" class="list-group list-group-flush">
      <div v-for="(entry, index) in draft.middlewares" :key="entry._key" class="list-group-item">
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
                :disabled="index === draft.middlewares.length - 1"
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
                @click="draft.middlewares.splice(index, 1)"
              ><i class="bi bi-trash" aria-hidden="true" /></LteButton>
            </div>
          </div>
          <div v-if="selectedPackage(entry.package_id)" class="col-12">
            <MiddlewareConfigForm
              :id-prefix="`middleware-config-${entry._key}`"
              v-model="entry.config"
              :schema="selectedPackage(entry.package_id)!.config_schema"
            />
          </div>
        </div>
      </div>
    </div>
    <p v-else class="text-body-secondary mb-0">{{ t('editors.customMiddleware.empty') }}</p>
  </div>
</template>
