<script setup lang="ts">
import { LteButton, LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import type { LocalizedMessagePayload } from '@/api'
import type { SkillCatalogItem, SkillDefaults, SkillDraft } from '@/domain/blocks'

import { useEditorModel } from './shared/useEditorModel'

const props = withDefaults(defineProps<{
  modelValue: SkillDraft
  defaults: SkillDefaults
  catalog?: SkillCatalogItem[]
  errors?: Record<string, LocalizedMessagePayload>
  loading?: boolean
}>(), {
  catalog: () => [],
  errors: () => ({}),
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: SkillDraft]
  refresh: []
}>()

const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

function resourceError(error: LocalizedMessagePayload): string {
  return t(error.message_key, error.message_args)
}
</script>

<template>
  <div data-editor="skill">
    <section class="card mb-3">
      <header class="card-header">
        <h3 class="card-title">{{ t('editors.skill.instructionTitle') }}</h3>
      </header>
      <div class="card-body">
        <div class="form-check form-switch mb-3">
          <input
            id="skill-system-prompt-enabled"
            v-model="draft.system_prompt_enabled"
            class="form-check-input"
            data-testid="skill-system-prompt-enabled"
            type="checkbox"
          >
          <label class="form-check-label" for="skill-system-prompt-enabled">
            {{ t('editors.skill.systemPromptEnabled') }}
          </label>
        </div>
        <div class="d-flex justify-content-end mb-3">
          <LteButton
            :disabled="!draft.system_prompt_enabled"
            theme="warning"
            @click="draft.instruction_override = defaults.system_prompt"
          >
            {{ t('editors.common.restoreDefault') }}
          </LteButton>
        </div>
        <LteTextarea
          v-model="draft.instruction_override"
          :aria-label="t('editors.skill.instructionTitle')"
          :disabled="!draft.system_prompt_enabled"
          :rows="16"
        />
        <p
          v-if="draft.system_prompt_enabled && defaults.required_placeholders?.length"
          class="form-text"
          data-testid="skill-required-placeholders"
        >
          {{ t('editors.skill.requiredPlaceholdersHint', {
            placeholders: defaults.required_placeholders.join(' '),
          }) }}
        </p>
      </div>
    </section>
    <section class="card mb-3">
      <header class="card-header d-flex align-items-center justify-content-between gap-2">
        <div>
          <h3 class="card-title">{{ t('editors.skill.catalogTitle') }}</h3>
          <p class="small text-body-secondary mb-0">{{ t('editors.skill.catalogHint') }}</p>
        </div>
        <LteButton class="ms-auto" :disabled="loading" theme="info" @click="emit('refresh')">
          <span v-if="loading" class="spinner-border spinner-border-sm" aria-hidden="true" />
          {{ t('editors.common.refresh') }}
        </LteButton>
      </header>
      <div v-if="catalog.length" class="list-group list-group-flush">
        <label v-for="skill in catalog" :key="skill.name" class="list-group-item" data-testid="skill-catalog-item">
          <span class="d-flex align-items-start gap-2">
            <input v-model="draft.skills" class="form-check-input" type="checkbox" :value="skill.name">
            <span class="w-100">
              <strong class="d-block">{{ skill.name }}</strong>
              <span v-if="skill.description" class="text-body-secondary">{{ skill.description }}</span>
            </span>
          </span>
        </label>
      </div>
      <p v-else class="card-body text-body-secondary mb-0">{{ t('editors.skill.emptyCatalog') }}</p>
      <div v-if="Object.keys(errors).length" class="card-body">
        <div class="alert alert-danger" role="alert">
          <p v-for="(error, folder) in errors" :key="folder">
            <strong>{{ folder }}</strong> {{ resourceError(error) }}
          </p>
        </div>
      </div>
    </section>
  </div>
</template>
