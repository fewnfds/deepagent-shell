<script setup lang="ts">
import { LteButton, LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import type {
  WorkflowInputContextDefaults,
  WorkflowInputContextDraft,
  WorkflowInputContextRole,
  WorkflowInputContextSlotDraft,
} from '@/domain/blocks'
import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{
  modelValue: WorkflowInputContextDraft
  defaults: WorkflowInputContextDefaults
}>()
const emit = defineEmits<{ 'update:modelValue': [value: WorkflowInputContextDraft] }>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

const roles: WorkflowInputContextRole[] = ['system', 'user', 'assistant']
let slotSequence = 0

function createSlot(): WorkflowInputContextSlotDraft {
  slotSequence += 1
  return {
    _key: `new-workflow-input-slot-${slotSequence}`,
    enabled: true,
    role: 'system',
    file: '',
    fallback_files: [],
    literal: '',
    max_chars: null,
    truncate_if_missing: false,
  }
}

function addSlot(): void {
  draft.slots.push(createSlot())
}

function removeSlot(index: number): void {
  draft.slots.splice(index, 1)
}

function moveSlot(index: number, offset: number): void {
  const target = index + offset
  if (target < 0 || target >= draft.slots.length) return
  const moved = draft.slots.splice(index, 1)[0]
  if (moved) draft.slots.splice(target, 0, moved)
}

function fallbackText(slot: WorkflowInputContextSlotDraft): string {
  return slot.fallback_files.join('\n')
}

function setFallbackText(slot: WorkflowInputContextSlotDraft, value: string): void {
  slot.fallback_files = value
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean)
}

function setMaxChars(slot: WorkflowInputContextSlotDraft, event: Event): void {
  const value = (event.target as HTMLInputElement).value
  slot.max_chars = value === '' ? null : Number(value)
}

function requirementsText(): string {
  return draft.python_requirements.join('\n')
}

function setRequirements(value: string): void {
  draft.python_requirements = value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}
</script>

<template>
  <div data-editor="workflow-input-context">
    <div class="form-check form-switch mb-3">
      <input id="workflow-input-context-enabled" v-model="draft.enabled" class="form-check-input" type="checkbox">
      <label class="form-check-label" for="workflow-input-context-enabled">
        {{ draft.enabled ? t('common.enabled') : t('common.disabled') }}
      </label>
    </div>
    <p v-if="draft.dependency_status !== 'ready'" class="form-text">
      {{ t(`editors.scriptRequirements.status.${draft.dependency_status}`) }}
    </p>

    <section class="card mb-3">
      <header class="card-header">
        <h3 class="card-title h5 mb-0">{{ t('editors.workflowInputContext.transformTitle') }}</h3>
      </header>
      <div class="card-body">
        <p class="form-text">{{ t('editors.workflowInputContext.transformHint') }}</p>
        <div class="form-check form-switch mb-3">
          <input id="workflow-input-context-transform-enabled" v-model="draft.custom_transform_enabled" class="form-check-input" type="checkbox">
          <label class="form-check-label" for="workflow-input-context-transform-enabled">
            {{ t('editors.workflowInputContext.transformEnabled') }}
          </label>
        </div>
        <FormField field-path="custom_transform_source">
          <LteTextarea v-model="draft.custom_transform_source" :disabled="!draft.custom_transform_enabled" :rows="12" />
        </FormField>
        <FormField field-path="python_requirements" :hint="t('editors.scriptRequirements.hint')">
          <LteTextarea :model-value="requirementsText()" :rows="4" @update:model-value="setRequirements($event)" />
        </FormField>
      </div>
    </section>

    <section class="card mb-3">
      <header class="card-header">
        <h3 class="card-title h5 mb-0">{{ t('editors.workflowInputContext.systemTitle') }}</h3>
      </header>
      <div class="card-body">
        <div class="form-check form-switch mb-3">
          <input id="workflow-input-context-promote" v-model="draft.system_promote_enabled" class="form-check-input" type="checkbox">
          <label class="form-check-label" for="workflow-input-context-promote">{{ t('editors.workflowInputContext.promoteEnabled') }}</label>
        </div>
        <div class="row g-3" data-ui-control-row>
          <div class="col-md-6">
            <FormField field-path="system_promote_min_chars">
              <input v-model.number="draft.system_promote_min_chars" class="form-control" min="0" step="1" type="number">
            </FormField>
          </div>
          <div class="col-md-6">
            <span class="form-label d-block">{{ t('editors.workflowInputContext.demoteEnabled') }}</span>
            <div class="form-check form-switch">
              <input id="workflow-input-context-demote" v-model="draft.demote_non_top_system" class="form-check-input" type="checkbox">
              <label class="visually-hidden" for="workflow-input-context-demote">{{ t('editors.workflowInputContext.demoteEnabled') }}</label>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="card mb-3">
      <header class="card-header d-flex align-items-center justify-content-between gap-2">
        <h3 class="card-title h5 mb-0">{{ t('editors.workflowInputContext.slotsTitle') }}</h3>
        <LteButton size="sm" theme="success" type="button" @click="addSlot">
          {{ t('editors.workflowInputContext.addSlot') }}
        </LteButton>
      </header>
      <div class="list-group list-group-flush">
        <div v-for="(slot, index) in draft.slots" :key="slot._key" class="list-group-item">
          <div class="d-flex align-items-center justify-content-between gap-2 mb-3">
            <div class="form-check form-switch">
              <input :id="`workflow-input-context-slot-${index}-enabled`" v-model="slot.enabled" class="form-check-input" type="checkbox">
              <label class="form-check-label" :for="`workflow-input-context-slot-${index}-enabled`">{{ t('common.enabled') }}</label>
            </div>
            <div class="d-flex gap-1">
              <LteButton :disabled="index === 0" :aria-label="t('editors.workflowInputContext.moveUp')" size="sm" theme="secondary" type="button" @click="moveSlot(index, -1)">↑</LteButton>
              <LteButton :disabled="index === draft.slots.length - 1" :aria-label="t('editors.workflowInputContext.moveDown')" size="sm" theme="secondary" type="button" @click="moveSlot(index, 1)">↓</LteButton>
              <LteButton :aria-label="t('editors.workflowInputContext.removeSlot')" size="sm" theme="danger" type="button" @click="removeSlot(index)">×</LteButton>
            </div>
          </div>
          <div class="row g-3">
            <div class="col-lg-4">
              <FormField field-path="role">
                <select v-model="slot.role" class="form-select">
                  <option v-for="role in roles" :key="role" :value="role">{{ role }}</option>
                </select>
              </FormField>
            </div>
            <div class="col-lg-8">
              <FormField field-path="file">
                <input v-model="slot.file" class="form-control" placeholder="/path/to/file.txt" type="text">
              </FormField>
            </div>
            <div class="col-12">
              <FormField field-path="fallback_files">
                <LteTextarea :model-value="fallbackText(slot)" :rows="3" @update:model-value="setFallbackText(slot, $event)" />
              </FormField>
            </div>
            <div class="col-lg-8">
              <FormField field-path="literal">
                <LteTextarea v-model="slot.literal" :rows="3" />
              </FormField>
            </div>
            <div class="col-lg-4">
              <FormField field-path="max_chars">
                <input :value="slot.max_chars ?? ''" class="form-control" min="1" step="1" type="number" @input="setMaxChars(slot, $event)">
              </FormField>
              <div class="form-check form-switch mt-2">
                <input :id="`workflow-input-context-slot-${index}-truncate`" v-model="slot.truncate_if_missing" class="form-check-input" type="checkbox">
                <label class="form-check-label" :for="`workflow-input-context-slot-${index}-truncate`">{{ t('editors.workflowInputContext.truncateIfMissing') }}</label>
              </div>
            </div>
          </div>
        </div>
        <div v-if="draft.slots.length === 0" class="list-group-item text-body-secondary">
          {{ t('editors.workflowInputContext.noSlots') }}
        </div>
      </div>
    </section>
  </div>
</template>
