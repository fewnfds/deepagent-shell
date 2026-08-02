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
        <LteButton class="ms-auto" theme="success" @click="draft.mapped_directories.push({ virtual_path: '', local_path: '' })">
          {{ t('editors.common.add') }}
        </LteButton>
      </header>
      <div v-if="draft.mapped_directories.length" class="list-group list-group-flush">
        <div v-for="(item, index) in draft.mapped_directories" :key="index" class="list-group-item">
          <div class="row g-3">
            <div class="col-md-6">
              <FormField :field-path="`mapped_directories.${index}.virtual_path`"><LteInput v-model="item.virtual_path" /></FormField>
            </div>
            <div class="col-md-6">
              <FormField :field-path="`mapped_directories.${index}.local_path`"><LteInput v-model="item.local_path" /></FormField>
            </div>
          </div>
          <div class="d-flex justify-content-end">
            <LteButton theme="danger" @click="draft.mapped_directories.splice(index, 1)">{{ t('editors.common.remove') }}</LteButton>
          </div>
        </div>
      </div>
      <p v-else class="card-body text-body-secondary mb-0">{{ t('editors.filesystem.emptyMappedDirectories') }}</p>
    </section>

    <section class="card mb-3">
      <header class="card-header d-flex align-items-start justify-content-between gap-2">
        <div>
          <h3 class="h5 fw-semibold mb-1">{{ t('editors.filesystem.virtualDirectoriesTitle') }}</h3>
          <p class="small text-body-secondary mb-0">{{ t('editors.filesystem.virtualDirectoriesHint') }}</p>
        </div>
        <LteButton class="ms-auto" theme="success" @click="draft.virtual_directories.push({ virtual_path: '', source_path: '' })">
          {{ t('editors.common.add') }}
        </LteButton>
      </header>
      <div v-if="draft.virtual_directories.length" class="list-group list-group-flush">
        <div v-for="(item, index) in draft.virtual_directories" :key="index" class="list-group-item">
          <div class="row g-3">
            <div class="col-md-6"><FormField :field-path="`virtual_directories.${index}.virtual_path`"><LteInput v-model="item.virtual_path" /></FormField></div>
            <div class="col-md-6"><FormField :field-path="`virtual_directories.${index}.source_path`"><LteInput v-model="item.source_path" /></FormField></div>
          </div>
          <div class="d-flex justify-content-end">
            <LteButton theme="danger" @click="draft.virtual_directories.splice(index, 1)">{{ t('editors.common.remove') }}</LteButton>
          </div>
        </div>
      </div>
      <p v-else class="card-body text-body-secondary mb-0">{{ t('editors.filesystem.emptyVirtualDirectories') }}</p>
    </section>

    <section class="card mb-3">
      <header class="card-header d-flex align-items-start justify-content-between gap-2">
        <div>
          <h3 class="h5 fw-semibold mb-1">{{ t('editors.filesystem.virtualFilesTitle') }}</h3>
          <p class="small text-body-secondary mb-0">{{ t('editors.filesystem.virtualFilesHint') }}</p>
        </div>
        <LteButton class="ms-auto" theme="success" @click="draft.virtual_files.push({ virtual_path: '', source_path: '' })">
          {{ t('editors.common.add') }}
        </LteButton>
      </header>
      <div v-if="draft.virtual_files.length" class="list-group list-group-flush">
        <div v-for="(item, index) in draft.virtual_files" :key="index" class="list-group-item">
          <div class="row g-3">
            <div class="col-md-6"><FormField :field-path="`virtual_files.${index}.virtual_path`"><LteInput v-model="item.virtual_path" /></FormField></div>
            <div class="col-md-6"><FormField :field-path="`virtual_files.${index}.source_path`"><LteInput v-model="item.source_path" /></FormField></div>
          </div>
          <div class="d-flex justify-content-end">
            <LteButton theme="danger" @click="draft.virtual_files.splice(index, 1)">{{ t('editors.common.remove') }}</LteButton>
          </div>
        </div>
      </div>
      <p v-else class="card-body text-body-secondary mb-0">{{ t('editors.filesystem.emptyVirtualFiles') }}</p>
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
