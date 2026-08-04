<script setup lang="ts">
import {
  LteButton,
  LteInput,
  LteTextarea,
} from '@adminlte/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import type { FilesystemDefaults, FilesystemDraft } from '@/domain/blocks'

import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{
  modelValue: FilesystemDraft
  defaults: FilesystemDefaults
}>()
const emit = defineEmits<{ 'update:modelValue': [value: FilesystemDraft] }>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

const toolRows = computed(() => props.defaults.tools.flatMap((tool) => {
  const config = draft.tool_configs[tool.name]
  return config ? [{ tool, config }] : []
}))
</script>

<template>
  <div data-editor="filesystem">
    <section class="card mb-3">
      <header class="card-header d-flex align-items-start justify-content-between gap-2">
        <div>
          <h3 class="h5 fw-semibold mb-1">{{ t('editors.filesystem.mappedDirectoriesTitle') }}</h3>
          <p class="small text-body-secondary mb-0">{{ t('editors.filesystem.mappedDirectoriesHint') }}</p>
        </div>
        <LteButton :aria-label="t('editors.common.add')" :title="t('editors.common.add')" class="ms-auto" data-action="add-mapped-directory" size="sm" theme="success" type="button" @click="draft.mapped_directories.push({ virtual_path: '', local_path: '' })">
          <i class="bi bi-plus-lg" aria-hidden="true" />
        </LteButton>
      </header>
      <div class="card-body">
        <div v-if="draft.mapped_directories.length" class="simple-mapping-list">
          <div v-for="(item, index) in draft.mapped_directories" :key="index" class="simple-mapping-row" data-testid="mapped-directory-row">
            <div class="simple-mapping-primary">
              <label class="visually-hidden" :for="`mapped-directory-virtual-path-${index}`">{{ t('fields.virtual_path') }}</label>
              <LteInput :id="`mapped-directory-virtual-path-${index}`" v-model="item.virtual_path" />
            </div>
            <div class="simple-mapping-secondary">
              <label class="visually-hidden" :for="`mapped-directory-local-path-${index}`">{{ t('fields.local_path') }}</label>
              <LteInput :id="`mapped-directory-local-path-${index}`" v-model="item.local_path" />
            </div>
            <div class="simple-mapping-actions">
              <LteButton :aria-label="t('editors.common.remove')" :title="t('editors.common.remove')" size="sm" theme="danger" type="button" @click="draft.mapped_directories.splice(index, 1)"><i class="bi bi-trash" aria-hidden="true" /></LteButton>
            </div>
          </div>
        </div>
        <p v-else class="text-body-secondary mb-0">{{ t('editors.filesystem.emptyMappedDirectories') }}</p>
        <div class="simple-mapping-footer">
          <LteButton :aria-label="t('editors.common.add')" :title="t('editors.common.add')" data-action="add-mapped-directory" size="sm" theme="success" type="button" @click="draft.mapped_directories.push({ virtual_path: '', local_path: '' })"><i class="bi bi-plus-lg" aria-hidden="true" /></LteButton>
        </div>
      </div>
    </section>

    <section class="card mb-3">
      <header class="card-header d-flex align-items-start justify-content-between gap-2">
        <div>
          <h3 class="h5 fw-semibold mb-1">{{ t('editors.filesystem.virtualDirectoriesTitle') }}</h3>
          <p class="small text-body-secondary mb-0">{{ t('editors.filesystem.virtualDirectoriesHint') }}</p>
        </div>
        <LteButton :aria-label="t('editors.common.add')" :title="t('editors.common.add')" class="ms-auto" data-action="add-virtual-directory" size="sm" theme="success" type="button" @click="draft.virtual_directories.push({ virtual_path: '', source_path: '' })">
          <i class="bi bi-plus-lg" aria-hidden="true" />
        </LteButton>
      </header>
      <div class="card-body">
        <div v-if="draft.virtual_directories.length" class="simple-mapping-list">
          <div v-for="(item, index) in draft.virtual_directories" :key="index" class="simple-mapping-row" data-testid="virtual-directory-row">
            <div class="simple-mapping-primary">
              <label class="visually-hidden" :for="`virtual-directory-virtual-path-${index}`">{{ t('fields.virtual_path') }}</label>
              <LteInput :id="`virtual-directory-virtual-path-${index}`" v-model="item.virtual_path" />
            </div>
            <div class="simple-mapping-secondary">
              <label class="visually-hidden" :for="`virtual-directory-source-path-${index}`">{{ t('fields.source_path') }}</label>
              <LteInput :id="`virtual-directory-source-path-${index}`" v-model="item.source_path" />
            </div>
            <div class="simple-mapping-actions">
              <LteButton :aria-label="t('editors.common.remove')" :title="t('editors.common.remove')" size="sm" theme="danger" type="button" @click="draft.virtual_directories.splice(index, 1)"><i class="bi bi-trash" aria-hidden="true" /></LteButton>
            </div>
          </div>
        </div>
        <p v-else class="text-body-secondary mb-0">{{ t('editors.filesystem.emptyVirtualDirectories') }}</p>
        <div class="simple-mapping-footer">
          <LteButton :aria-label="t('editors.common.add')" :title="t('editors.common.add')" data-action="add-virtual-directory" size="sm" theme="success" type="button" @click="draft.virtual_directories.push({ virtual_path: '', source_path: '' })"><i class="bi bi-plus-lg" aria-hidden="true" /></LteButton>
        </div>
      </div>
    </section>

    <section class="card mb-3">
      <header class="card-header d-flex align-items-start justify-content-between gap-2">
        <div>
          <h3 class="h5 fw-semibold mb-1">{{ t('editors.filesystem.virtualFilesTitle') }}</h3>
          <p class="small text-body-secondary mb-0">{{ t('editors.filesystem.virtualFilesHint') }}</p>
        </div>
        <LteButton :aria-label="t('editors.common.add')" :title="t('editors.common.add')" class="ms-auto" data-action="add-virtual-file" size="sm" theme="success" type="button" @click="draft.virtual_files.push({ virtual_path: '', source_path: '' })">
          <i class="bi bi-plus-lg" aria-hidden="true" />
        </LteButton>
      </header>
      <div class="card-body">
        <div v-if="draft.virtual_files.length" class="simple-mapping-list">
          <div v-for="(item, index) in draft.virtual_files" :key="index" class="simple-mapping-row" data-testid="virtual-file-row">
            <div class="simple-mapping-primary">
              <label class="visually-hidden" :for="`virtual-file-virtual-path-${index}`">{{ t('fields.virtual_path') }}</label>
              <LteInput :id="`virtual-file-virtual-path-${index}`" v-model="item.virtual_path" />
            </div>
            <div class="simple-mapping-secondary">
              <label class="visually-hidden" :for="`virtual-file-source-path-${index}`">{{ t('fields.source_path') }}</label>
              <LteInput :id="`virtual-file-source-path-${index}`" v-model="item.source_path" />
            </div>
            <div class="simple-mapping-actions">
              <LteButton :aria-label="t('editors.common.remove')" :title="t('editors.common.remove')" size="sm" theme="danger" type="button" @click="draft.virtual_files.splice(index, 1)"><i class="bi bi-trash" aria-hidden="true" /></LteButton>
            </div>
          </div>
        </div>
        <p v-else class="text-body-secondary mb-0">{{ t('editors.filesystem.emptyVirtualFiles') }}</p>
        <div class="simple-mapping-footer">
          <LteButton :aria-label="t('editors.common.add')" :title="t('editors.common.add')" data-action="add-virtual-file" size="sm" theme="success" type="button" @click="draft.virtual_files.push({ virtual_path: '', source_path: '' })"><i class="bi bi-plus-lg" aria-hidden="true" /></LteButton>
        </div>
      </div>
    </section>

    <section class="card mb-3">
      <header class="card-header">
        <h3 class="card-title">{{ t('editors.filesystem.systemPromptTitle') }}</h3>
      </header>
      <div class="card-body">
        <div class="d-flex justify-content-end mb-3">
          <LteButton theme="warning" @click="draft.system_prompt_override = defaults.system_prompt">{{ t('editors.common.restoreDefault') }}</LteButton>
        </div>
        <LteTextarea
          v-model="draft.system_prompt_override"
          :aria-label="t('editors.filesystem.systemPromptTitle')"
          :rows="14"
        />
      </div>
    </section>

    <section class="mb-3">
      <h3 class="h5 fw-semibold mb-3">{{ t('editors.filesystem.toolsTitle') }}</h3>
      <FormField field-path="tool_token_limit_before_evict">
        <input v-model.number="draft.tool_token_limit_before_evict" class="form-control" min="1" step="1" type="number">
      </FormField>
      <div class="row g-3">
        <div v-for="row in toolRows" :key="row.tool.name" class="col-md-6">
          <article class="card h-100" data-testid="filesystem-tool-card">
            <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
              <h4 class="card-title mb-0 font-monospace">{{ row.tool.name }}</h4>
              <div class="form-check form-switch ms-auto">
                <input
                  :id="`tool-visible-${row.tool.name}`"
                  v-model="row.config.visible"
                  class="form-check-input"
                  :disabled="!row.tool.configurable"
                  type="checkbox"
                >
                <label class="form-check-label" :for="`tool-visible-${row.tool.name}`">
                  {{ row.config.visible ? t('editors.common.enabled') : t('editors.common.disabled') }}
                </label>
              </div>
            </header>
            <div class="card-body">
              <div class="d-flex justify-content-end mb-3">
                <LteButton theme="warning" @click="row.config.description_override = row.tool.default_description">{{ t('editors.common.restoreDefault') }}</LteButton>
              </div>
              <LteTextarea
                v-model="row.config.description_override"
                :aria-label="t('editors.filesystem.toolDescriptionLabel', { tool: row.tool.name })"
                :rows="8"
              />
            </div>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>
