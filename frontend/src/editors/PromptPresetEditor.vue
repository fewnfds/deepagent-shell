<script setup lang="ts">
import { LteButton, LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import {
  createPromptStartupMessage,
  createPromptTagReplacement,
  type PromptPresetDefaults,
  type PromptPresetDraft,
} from '@/domain/blocks'

import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{
  modelValue: PromptPresetDraft
  defaults: PromptPresetDefaults
}>()
const emit = defineEmits<{ 'update:modelValue': [value: PromptPresetDraft] }>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

function moveMessage(index: number, delta: number): void {
  const target = index + delta
  if (target < 0 || target >= draft.startup_messages.length) return
  const moved = draft.startup_messages.splice(index, 1)[0]
  if (moved) draft.startup_messages.splice(target, 0, moved)
}
</script>

<template>
  <div data-editor="prompt-preset">
    <section class="mb-3" aria-labelledby="prompt-preset-tags-title">
      <header class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
        <div>
          <h3 id="prompt-preset-tags-title" class="h5 fw-semibold mb-0">
            {{ t('editors.promptPreset.tagsTitle') }}
          </h3>
          <p class="small text-body-secondary mb-0">{{ t('editors.promptPreset.tagsHint') }}</p>
        </div>
        <LteButton class="ms-auto" data-action="add-tag" theme="success" type="button" @click="draft.tag_replacements.push(createPromptTagReplacement())">
          {{ t('editors.promptPreset.addTag') }}
        </LteButton>
      </header>
      <article v-for="(entry, index) in draft.tag_replacements" :key="entry._key" class="card mb-3">
        <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
          <h4 class="card-title mb-0">{{ entry.tag || t('editors.promptPreset.unnamedTag') }}</h4>
          <LteButton class="ms-auto" size="sm" theme="danger" type="button" @click="draft.tag_replacements.splice(index, 1)">
            {{ t('editors.common.remove') }}
          </LteButton>
        </header>
        <div class="card-body">
          <FormField :field-path="`tag_replacements.${index}.tag`" :hint="t('editors.promptPreset.tagHint')">
            <input v-model="entry.tag" autocomplete="off" class="form-control">
          </FormField>
          <FormField :field-path="`tag_replacements.${index}.replacement`" :hint="t('editors.promptPreset.replacementHint')">
            <LteTextarea v-model="entry.replacement" :rows="6" />
          </FormField>
        </div>
      </article>
      <p v-if="draft.tag_replacements.length === 0" class="text-body-secondary">
        {{ t('editors.promptPreset.noTags') }}
      </p>
    </section>

    <section class="mb-3" aria-labelledby="prompt-preset-startup-title">
      <header class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
        <div>
          <h3 id="prompt-preset-startup-title" class="h5 fw-semibold mb-0">
            {{ t('editors.promptPreset.startupTitle') }}
          </h3>
          <p class="small text-body-secondary mb-0">{{ t('editors.promptPreset.startupHint') }}</p>
        </div>
        <LteButton class="ms-auto" data-action="add-message" theme="success" type="button" @click="draft.startup_messages.push(createPromptStartupMessage())">
          {{ t('editors.promptPreset.addMessage') }}
        </LteButton>
      </header>
      <div v-if="defaults.template_variables.length" class="d-flex flex-wrap gap-2 mb-3" :aria-label="t('editors.promptPreset.variablesTitle')">
        <span v-for="variable in defaults.template_variables" :key="variable" class="badge text-bg-secondary font-monospace">
          {{ variable }}
        </span>
      </div>
      <article v-for="(message, index) in draft.startup_messages" :key="message._key" class="card mb-3">
        <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
          <h4 class="card-title mb-0">{{ t('editors.promptPreset.messageTitle', { index: index + 1 }) }}</h4>
          <div class="d-flex flex-wrap gap-2 ms-auto">
            <LteButton :disabled="index === 0" size="sm" theme="warning" type="button" @click="moveMessage(index, -1)">
              {{ t('editors.common.moveUp') }}
            </LteButton>
            <LteButton :disabled="index === draft.startup_messages.length - 1" size="sm" theme="warning" type="button" @click="moveMessage(index, 1)">
              {{ t('editors.common.moveDown') }}
            </LteButton>
            <LteButton size="sm" theme="danger" type="button" @click="draft.startup_messages.splice(index, 1)">
              {{ t('editors.common.remove') }}
            </LteButton>
          </div>
        </header>
        <div class="card-body">
          <div class="row g-3">
            <div class="col-md-6">
              <FormField :field-path="`startup_messages.${index}.role`">
                <select v-model="message.role" class="form-select">
                  <option value="user">{{ 'user' }}</option>
                  <option value="assistant">{{ 'assistant' }}</option>
                </select>
              </FormField>
            </div>
            <div class="col-md-6">
              <FormField :field-path="`startup_messages.${index}.name`" :hint="t('editors.promptPreset.nameHint')">
                <input v-model="message.name" autocomplete="off" class="form-control">
              </FormField>
            </div>
          </div>
          <FormField :field-path="`startup_messages.${index}.content_template`">
            <LteTextarea v-model="message.content_template" :rows="7" />
          </FormField>
        </div>
      </article>
      <p v-if="draft.startup_messages.length === 0" class="text-body-secondary">
        {{ t('editors.promptPreset.noMessages') }}
      </p>
    </section>
  </div>
</template>
