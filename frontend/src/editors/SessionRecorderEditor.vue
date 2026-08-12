<script setup lang="ts">
import { LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import type { SessionRecorderDefaults, SessionRecorderDraft } from '@/domain/blocks'
import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{ modelValue: SessionRecorderDraft; defaults: SessionRecorderDefaults }>()
const emit = defineEmits<{ 'update:modelValue': [value: SessionRecorderDraft] }>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

function setRequirements(value: string): void {
  draft.python_requirements = value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}
</script>

<template>
  <div data-editor="session-recorder">
    <div class="form-check form-switch mb-3">
      <input id="session-recorder-enabled" v-model="draft.enabled" class="form-check-input" type="checkbox">
      <label class="form-check-label" for="session-recorder-enabled">{{ t('common.enabled') }}</label>
    </div>
    <p v-if="draft.dependency_status !== 'ready'" class="form-text">
      {{ t(`editors.scriptRequirements.status.${draft.dependency_status}`) }}
    </p>
    <div class="form-check form-switch mb-3">
      <input id="session-recorder-transform-enabled" v-model="draft.custom_transform_enabled" class="form-check-input" type="checkbox">
      <label class="form-check-label" for="session-recorder-transform-enabled">{{ t('editors.sessionRecorder.transformEnabled') }}</label>
    </div>
    <FormField field-path="custom_transform_source" :hint="t('editors.sessionRecorder.transformHint')">
      <LteTextarea v-model="draft.custom_transform_source" :disabled="!draft.custom_transform_enabled" :rows="12" />
    </FormField>
    <FormField field-path="python_requirements" :hint="t('editors.scriptRequirements.hint')">
      <LteTextarea :model-value="draft.python_requirements.join('\n')" :rows="4" @update:model-value="setRequirements($event)" />
    </FormField>
  </div>
</template>
