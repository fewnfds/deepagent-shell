<script setup lang="ts">
import { LteButton, LteInput, LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import type { LocalizedMessagePayload } from '@/api'
import FormField from '@/components/FormField.vue'
import {
  createMiddlewareEntry,
  type CustomMiddlewareCatalogItem,
  type CustomMiddlewareDraft,
} from '@/domain/blocks'

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

function resourceError(error: LocalizedMessagePayload): string {
  return t(error.message_key, error.message_args)
}

function addBlank(): void {
  draft.middlewares.push(createMiddlewareEntry())
}

function addTemplate(template: CustomMiddlewareCatalogItem): void {
  draft.middlewares.push(createMiddlewareEntry({
    name: template.description ?? template.name ?? '',
    source: template.source ?? '',
  }))
}

function move(index: number, delta: number): void {
  const target = index + delta
  if (target < 0 || target >= draft.middlewares.length) return
  const moved = draft.middlewares.splice(index, 1)[0]
  if (moved) draft.middlewares.splice(target, 0, moved)
}
</script>

<template>
  <div data-editor="custom-middleware">
    <section class="mb-3">
      <header class="d-flex align-items-center justify-content-between gap-2 mb-3">
        <div>
          <h3 class="h5 fw-semibold mb-0">{{ t('editors.customMiddleware.entriesTitle') }}</h3>
        </div>
        <LteButton class="ms-auto" theme="success" @click="addBlank">{{ t('editors.customMiddleware.addBlank') }}</LteButton>
      </header>
      <div>
        <div v-if="draft.middlewares.length">
          <article v-for="(entry, index) in draft.middlewares" :key="entry._key" class="card mb-3">
            <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
              <div class="form-check form-switch">
                <input :id="`middleware-enabled-${entry._key}`" v-model="entry.enabled" class="form-check-input" type="checkbox">
                <label class="form-check-label" :for="`middleware-enabled-${entry._key}`">{{ t('editors.common.enabled') }}</label>
              </div>
              <div class="d-flex flex-wrap gap-2 ms-auto">
                <LteButton :disabled="index === 0" size="sm" theme="warning" @click="move(index, -1)">{{ t('editors.common.moveUp') }}</LteButton>
                <LteButton :disabled="index === draft.middlewares.length - 1" size="sm" theme="warning" @click="move(index, 1)">{{ t('editors.common.moveDown') }}</LteButton>
                <LteButton size="sm" theme="danger" @click="draft.middlewares.splice(index, 1)">{{ t('editors.common.remove') }}</LteButton>
              </div>
            </header>
            <div class="card-body">
              <FormField :field-path="`middlewares.${index}.name`">
                <LteInput v-model="entry.name" :placeholder="t('editors.customMiddleware.entryNamePlaceholder')" />
              </FormField>
              <FormField :field-path="`middlewares.${index}.source`" :hint="t('editors.customMiddleware.sourceHint')">
                <LteTextarea
                  v-model="entry.source"
                  :placeholder="t('editors.customMiddleware.sourcePlaceholder')"
                  :rows="12"
                  spellcheck="false"
                />
              </FormField>
            </div>
          </article>
        </div>
        <p v-else class="text-body-secondary">{{ t('editors.customMiddleware.emptyEntries') }}</p>
      </div>
    </section>

    <section class="card mb-3">
      <header class="card-header d-flex align-items-center justify-content-between gap-2">
        <div>
          <h3 class="card-title">{{ t('editors.customMiddleware.catalogTitle') }}</h3>
        </div>
        <LteButton class="ms-auto" :disabled="loading" theme="info" @click="emit('refresh')">
          <span v-if="loading" class="spinner-border spinner-border-sm" aria-hidden="true" />
          {{ t('editors.common.refresh') }}
        </LteButton>
      </header>
      <div v-if="catalog.length" class="list-group list-group-flush">
        <article v-for="template in catalog" :key="template.filename" class="list-group-item">
          <div class="d-flex flex-wrap align-items-center justify-content-between gap-2">
            <span>
              <strong class="d-block">{{ template.name ?? template.filename }}</strong>
              <span v-if="template.description" class="d-block text-body-secondary">{{ template.description }}</span>
              <span class="font-monospace text-break">{{ template.filename }}</span>
            </span>
            <LteButton theme="success" @click="addTemplate(template)">{{ t('editors.customMiddleware.addTemplate') }}</LteButton>
          </div>
        </article>
      </div>
      <p v-else class="card-body text-body-secondary mb-0">{{ t('editors.customMiddleware.emptyCatalog') }}</p>
      <div v-if="Object.keys(errors).length" class="card-body">
        <div class="alert alert-danger" role="alert">
          <p v-for="(error, filename) in errors" :key="filename">
            <strong>{{ filename }}</strong> {{ resourceError(error) }}
          </p>
        </div>
      </div>
    </section>
  </div>
</template>
