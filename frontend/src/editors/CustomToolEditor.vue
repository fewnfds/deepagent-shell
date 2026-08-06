<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import type { LocalizedMessagePayload } from '@/api'
import type { CustomToolCatalogItem, CustomToolDraft } from '@/domain/blocks'

import { useEditorModel } from './shared/useEditorModel'

const props = withDefaults(defineProps<{
  modelValue: CustomToolDraft
  catalog?: CustomToolCatalogItem[]
  errors?: Record<string, LocalizedMessagePayload>
  loading?: boolean
}>(), {
  catalog: () => [],
  errors: () => ({}),
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: CustomToolDraft]
  refresh: []
}>()

const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

function resourceError(error: LocalizedMessagePayload): string {
  return t(error.message_key, error.message_args)
}

function identifiers(tool: CustomToolCatalogItem): Array<{ label: string, value: string }> {
  return [
    { label: 'tool_name', value: tool.tool_name ?? 'unresolved' },
    { label: 'function', value: tool.function ?? '' },
    { label: 'resource_name', value: tool.name },
    { label: 'filename', value: tool.filename ?? '' },
  ]
}
</script>

<template>
  <div data-editor="custom-tool">
    <section class="card mb-3">
      <header class="card-header d-flex align-items-center justify-content-between gap-2">
        <h3 class="card-title">{{ t('editors.customTool.catalogTitle') }}</h3>
        <LteButton class="ms-auto" data-action="refresh" :disabled="loading" theme="info" @click="emit('refresh')">
          <span v-if="loading" class="spinner-border spinner-border-sm" aria-hidden="true" />
          {{ t('editors.common.refresh') }}
        </LteButton>
      </header>
      <div v-if="catalog.length" class="list-group list-group-flush">
        <label v-for="tool in catalog" :key="tool.name" class="list-group-item" data-testid="custom-tool-item">
          <span class="d-flex align-items-start gap-2">
            <input v-model="draft.tools" class="form-check-input" type="checkbox" :value="tool.name">
            <span class="w-100">
              <dl data-testid="tool-identifiers">
                <div v-for="identifier in identifiers(tool)" :key="identifier.label">
                  <dt>{{ identifier.label }}</dt>
                  <dd class="text-break">{{ identifier.value }}</dd>
                </div>
              </dl>
              <span v-if="tool.description" class="text-body-secondary">{{ tool.description }}</span>
            </span>
          </span>
        </label>
      </div>
      <p v-else class="card-body text-body-secondary mb-0">{{ t('editors.customTool.emptyCatalog') }}</p>
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
