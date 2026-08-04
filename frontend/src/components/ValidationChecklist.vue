<script setup lang="ts">
import { LteAccordion, LteAccordionItem, LteAlert } from '@adminlte/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ConfigurationValidationState } from '@/composables/useConfigurationValidation'
import { useValidationIssuePresentation } from '@/composables/useValidationIssuePresentation'

const props = defineProps<{
  title: string
  validation: Readonly<ConfigurationValidationState>
}>()

const { t } = useI18n()
const issuePresentation = useValidationIssuePresentation()

const validationStatus = computed(() => props.validation.status)
const issueCount = computed(() => props.validation.report?.issues.length ?? 0)
const warningCount = computed(() => props.validation.report?.issues.filter(
  (issue) => issue.severity === 'warning',
).length ?? 0)
const hasWarnings = computed(() => warningCount.value > 0)
</script>

<template>
  <section
    v-if="validationStatus === 'invalid' || validationStatus === 'unavailable' || hasWarnings"
    class="card card-outline mb-3"
    aria-live="polite"
    :data-status="validationStatus"
    data-testid="validation-checklist"
  >
    <header class="card-header d-flex align-items-center gap-2">
      <i v-if="validationStatus === 'invalid' || validationStatus === 'unavailable'" class="bi bi-exclamation-triangle text-danger" aria-hidden="true" />
      <i v-else class="bi bi-info-circle" aria-hidden="true" />
      <div class="lh-sm">
        <h2 class="h5 mb-1 fw-semibold">{{ title }}</h2>
        <p v-if="validationStatus === 'invalid'" class="small text-body-secondary mb-0">
          {{ t('validation.issueSummary', { count: issueCount }) }}
        </p>
        <p v-else-if="hasWarnings" class="small text-body-secondary mb-0">
          {{ t('validation.warningSummary', { count: warningCount }) }}
        </p>
      </div>
    </header>

    <div v-if="validationStatus === 'unavailable'" class="card-body">
      <LteAlert
        theme="danger"
        :title="validation.error || t('validation.unavailableDetail')"
      />
    </div>
    <LteAccordion v-else always-open flush>
      <LteAccordionItem
        v-for="(issue, index) in validation.report?.issues ?? []"
        :key="`${issue.scope}:${issue.owner_id}:${issue.path}:${issue.code}:${index}`"
        :id="`validation-issue-${index}`"
        :title="issuePresentation.message(issue)"
        data-testid="validation-issue"
      >
        <dl class="row g-3 mb-0">
            <div class="col-md-6">
              <dt class="small text-uppercase text-body-secondary mb-1">
                {{ t('validation.location.owner') }}
              </dt>
              <dd class="mb-0 fw-semibold" data-testid="validation-owner">
                {{ issuePresentation.ownerLabel(issue) }}
              </dd>
            </div>
            <div class="col-md-6">
              <dt class="small text-uppercase text-body-secondary mb-1">
                {{ t('validation.location.problemLocation') }}
              </dt>
              <dd class="mb-0 fw-semibold" data-testid="validation-location">
                {{ issuePresentation.location(issue) }}
              </dd>
            </div>
            <div v-if="issue.path" class="col-md-6">
              <dt class="small text-uppercase text-body-secondary mb-1">
                {{ t('validation.location.technicalPath') }}
              </dt>
              <dd class="mb-0 font-monospace text-break" data-testid="validation-technical-path">
                {{ issue.path }}
              </dd>
            </div>
            <div class="col-12">
              <dt class="small text-uppercase text-body-secondary mb-1">
                {{ t('validation.location.reason') }}
              </dt>
              <dd class="mb-0" data-testid="validation-reason">
                {{ issuePresentation.message(issue) }}
              </dd>
            </div>
            <div class="col-12">
              <dt class="small text-uppercase text-body-secondary mb-1">
                {{ t('validation.location.resolution') }}
              </dt>
              <dd class="mb-0" data-testid="validation-resolution">
                {{ issuePresentation.resolution(issue) }}
              </dd>
            </div>
            <div v-if="$slots['issue-actions']" class="col-12 d-flex flex-wrap gap-2">
              <slot name="issue-actions" :issue="issue" />
            </div>
        </dl>
      </LteAccordionItem>
    </LteAccordion>
  </section>

  <section
    v-else
    class="card mb-3"
    :aria-busy="validationStatus === 'validating'"
    aria-live="polite"
    :data-status="validationStatus"
    data-testid="validation-checklist"
  >
    <header class="card-header d-flex align-items-center gap-2">
      <i
        v-if="validationStatus === 'valid'"
        class="bi bi-check-circle text-success"
        aria-hidden="true"
      />
      <i v-else class="bi bi-arrow-clockwise" aria-hidden="true" />
      <h2 class="h5 mb-0 fw-semibold">{{ title }}</h2>
    </header>
    <div v-if="validationStatus === 'validating'" class="card-body">
      <LteAlert theme="info" :title="t('validation.validatingDetail')" />
    </div>
  </section>
</template>
