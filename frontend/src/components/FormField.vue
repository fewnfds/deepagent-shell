<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { fieldLabelKeys } from '@/locales/fieldLabels'

const props = defineProps<{
  fieldPath: string
  hint?: string
  labelKey?: string
  technical?: boolean
}>()

const { t, te } = useI18n()

const label = computed(() => {
  if (props.technical) return props.fieldPath.split('.').at(-1) ?? props.fieldPath
  const keys = props.labelKey ? [props.labelKey] : fieldLabelKeys(props.fieldPath)
  const key = keys.find((candidate) => te(candidate))
  return key ? t(key) : props.fieldPath
})
</script>

<template>
  <div class="mb-3">
    <span v-if="technical" class="form-label d-block font-monospace">{{ label }}</span>
    <span v-else class="form-label d-block">{{ label }}</span>
    <slot />
    <div v-if="hint" class="form-text">{{ hint }}</div>
  </div>
</template>
