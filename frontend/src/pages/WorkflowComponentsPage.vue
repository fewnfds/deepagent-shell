<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  managementApi,
  type JsonValue,
  type WorkflowComponentDefinition,
  type WorkflowComponentDefinitionPayload,
  type WorkflowComponentInputEndpoint,
  type WorkflowComponentInstance,
  type WorkflowComponentInstancePayload,
  type WorkflowComponentOutputEndpoint,
} from '@/api'
import PageShell from '@/components/PageShell.vue'
import { useConfirmation } from '@/composables/useConfirmation'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'

interface DefinitionDraft {
  id: string
  name: string
  description: string
  inputEndpointsJson: string
  outputEndpointsJson: string
  configSchemaJson: string
  pythonSource: string
  pythonRequirements: string
}

interface InstanceDraft {
  id: string
  name: string
  description: string
  configJson: string
}

const { t } = useI18n()
const managementError = useManagementError()
const confirmation = useConfirmation()
const { notify } = useToasts()

const definitions = ref<WorkflowComponentDefinition[]>([])
const instances = ref<WorkflowComponentInstance[]>([])
const selectedDefinitionId = ref('')
const selectedInstanceId = ref('')
const definitionDraft = ref<DefinitionDraft>(blankDefinition())
const instanceDraft = ref<InstanceDraft>(blankInstance())
const loading = ref(true)
const savingDefinition = ref(false)
const savingInstance = ref(false)
const pageError = ref('')

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function blankDefinition(): DefinitionDraft {
  return {
    id: '',
    name: '',
    description: '',
    inputEndpointsJson: pretty([{
      id: 'in',
      label: 'Input',
      activation: 'any',
      accepted_edge_types: ['normal', 'conditional'],
      max_connections: null,
    }]),
    outputEndpointsJson: pretty([{
      id: 'next',
      label: 'Next',
      edge_type: 'conditional',
      max_connections: 1,
    }]),
    configSchemaJson: pretty({
      type: 'object',
      properties: {},
      additionalProperties: false,
    }),
    pythonSource: 'async def run(input):\n    return {"update": {}, "route": "next"}\n',
    pythonRequirements: '',
  }
}

function blankInstance(): InstanceDraft {
  return { id: '', name: '', description: '', configJson: '{}\n' }
}

function definitionToDraft(value: WorkflowComponentDefinition): DefinitionDraft {
  return {
    id: value.id,
    name: value.name,
    description: value.description,
    inputEndpointsJson: pretty(value.input_endpoints),
    outputEndpointsJson: pretty(value.output_endpoints),
    configSchemaJson: pretty(value.config_schema),
    pythonSource: value.python_source,
    pythonRequirements: value.python_requirements.join('\n'),
  }
}

function instanceToDraft(value: WorkflowComponentInstance): InstanceDraft {
  return {
    id: value.id,
    name: value.name,
    description: value.description,
    configJson: pretty(value.config),
  }
}

function parseArray<T>(source: string): T[] {
  const value: unknown = JSON.parse(source)
  if (!Array.isArray(value)) throw new Error(t('workflowComponents.invalidJson'))
  return value as T[]
}

function parseObject(source: string): Record<string, JsonValue> {
  const value: unknown = JSON.parse(source)
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(t('workflowComponents.invalidJson'))
  }
  return value as Record<string, JsonValue>
}

function definitionPayload(): WorkflowComponentDefinitionPayload & { id?: string } {
  return {
    ...(definitionDraft.value.id ? { id: definitionDraft.value.id } : {}),
    name: definitionDraft.value.name,
    description: definitionDraft.value.description,
    runtime_kind: 'python-command',
    state_contract: 'agent-shell.workflow.agent-invocations.v1',
    input_endpoints: parseArray<WorkflowComponentInputEndpoint>(
      definitionDraft.value.inputEndpointsJson,
    ),
    output_endpoints: parseArray<WorkflowComponentOutputEndpoint>(
      definitionDraft.value.outputEndpointsJson,
    ),
    config_schema: parseObject(definitionDraft.value.configSchemaJson),
    python_source: definitionDraft.value.pythonSource,
    python_requirements: definitionDraft.value.pythonRequirements.split(/\r?\n/),
  }
}

function instancePayload(): WorkflowComponentInstancePayload & { id?: string } {
  return {
    ...(instanceDraft.value.id ? { id: instanceDraft.value.id } : {}),
    definition_id: selectedDefinitionId.value,
    name: instanceDraft.value.name,
    description: instanceDraft.value.description,
    config: parseObject(instanceDraft.value.configJson),
  }
}

async function loadDefinitions(preferredId = ''): Promise<void> {
  definitions.value = await managementApi.listWorkflowComponentDefinitions()
  const selected = definitions.value.find((item) => item.id === preferredId)
    ?? definitions.value[0]
  selectedDefinitionId.value = selected?.id ?? ''
  definitionDraft.value = selected ? definitionToDraft(selected) : blankDefinition()
  await loadInstances()
}

async function loadInstances(preferredId = ''): Promise<void> {
  if (!selectedDefinitionId.value) {
    instances.value = []
    selectedInstanceId.value = ''
    instanceDraft.value = blankInstance()
    return
  }
  instances.value = await managementApi.listWorkflowComponentInstances(
    selectedDefinitionId.value,
  )
  const selected = instances.value.find((item) => item.id === preferredId)
    ?? instances.value[0]
  selectedInstanceId.value = selected?.id ?? ''
  instanceDraft.value = selected ? instanceToDraft(selected) : blankInstance()
}

async function selectDefinition(): Promise<void> {
  const selected = definitions.value.find(
    (item) => item.id === selectedDefinitionId.value,
  )
  definitionDraft.value = selected ? definitionToDraft(selected) : blankDefinition()
  pageError.value = ''
  await loadInstances()
}

function newDefinition(): void {
  selectedDefinitionId.value = ''
  definitionDraft.value = blankDefinition()
  instances.value = []
  selectedInstanceId.value = ''
  instanceDraft.value = blankInstance()
  pageError.value = ''
}

async function saveDefinition(): Promise<void> {
  savingDefinition.value = true
  pageError.value = ''
  try {
    const saved = await managementApi.saveWorkflowComponentDefinition(
      definitionPayload(),
    )
    await loadDefinitions(saved.id)
    notify({ tone: 'success', title: t('workflowComponents.definitionSaved') })
  } catch (error) {
    pageError.value = error instanceof SyntaxError
      ? t('workflowComponents.invalidJson')
      : managementError.describe(error).display
  } finally {
    savingDefinition.value = false
  }
}

async function deleteDefinition(): Promise<void> {
  if (!definitionDraft.value.id) return
  const accepted = await confirmation.confirm({
    title: t('workflowComponents.deleteDefinitionTitle'),
    description: t('workflowComponents.deleteDefinitionDescription', {
      name: definitionDraft.value.name,
    }),
    confirmLabel: t('common.delete'),
    cancelLabel: t('common.cancel'),
    dangerous: true,
  })
  if (!accepted) return
  pageError.value = ''
  try {
    await managementApi.deleteWorkflowComponentDefinition(definitionDraft.value.id)
    await loadDefinitions()
  } catch (error) {
    pageError.value = managementError.describe(error).display
  }
}

function selectInstance(): void {
  const selected = instances.value.find((item) => item.id === selectedInstanceId.value)
  instanceDraft.value = selected ? instanceToDraft(selected) : blankInstance()
  pageError.value = ''
}

function newInstance(): void {
  selectedInstanceId.value = ''
  instanceDraft.value = blankInstance()
  pageError.value = ''
}

async function saveInstance(): Promise<void> {
  if (!selectedDefinitionId.value) return
  savingInstance.value = true
  pageError.value = ''
  try {
    const saved = await managementApi.saveWorkflowComponentInstance(instancePayload())
    await loadInstances(saved.id)
    notify({ tone: 'success', title: t('workflowComponents.instanceSaved') })
  } catch (error) {
    pageError.value = error instanceof SyntaxError
      ? t('workflowComponents.invalidJson')
      : managementError.describe(error).display
  } finally {
    savingInstance.value = false
  }
}

async function deleteInstance(): Promise<void> {
  if (!instanceDraft.value.id) return
  const accepted = await confirmation.confirm({
    title: t('workflowComponents.deleteInstanceTitle'),
    description: t('workflowComponents.deleteInstanceDescription', {
      name: instanceDraft.value.name,
    }),
    confirmLabel: t('common.delete'),
    cancelLabel: t('common.cancel'),
    dangerous: true,
  })
  if (!accepted) return
  pageError.value = ''
  try {
    await managementApi.deleteWorkflowComponentInstance(instanceDraft.value.id)
    await loadInstances()
  } catch (error) {
    pageError.value = managementError.describe(error).display
  }
}

onMounted(async () => {
  try {
    await loadDefinitions()
  } catch (error) {
    pageError.value = managementError.describe(error).display
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <PageShell>
    <template #actions>
      <RouterLink class="btn btn-outline-secondary" to="/workflow-components/prepare">
        {{ t('workflowComponents.workflowPrepare') }}
      </RouterLink>
    </template>

    <LteAlert v-if="pageError" class="mb-3" theme="danger">
      {{ pageError }}
    </LteAlert>

    <div class="configuration-loading-surface" :aria-busy="loading" :inert="loading || undefined">
      <section aria-labelledby="workflow-component-definition-heading">
        <div class="d-flex flex-wrap align-items-end gap-2 mb-3">
          <div class="flex-grow-1">
            <label class="form-label" for="workflow-component-definition-picker">
              {{ t('workflowComponents.definition') }}
            </label>
            <select
              id="workflow-component-definition-picker"
              v-model="selectedDefinitionId"
              class="form-select"
              @change="selectDefinition"
            >
              <option value="">{{ t('workflowComponents.newDefinition') }}</option>
              <option v-for="item in definitions" :key="item.id" :value="item.id">
                {{ item.name }}
              </option>
            </select>
          </div>
          <LteButton theme="success" type="button" @click="newDefinition">
            {{ t('common.new') }}
          </LteButton>
          <LteButton
            :disabled="!definitionDraft.id"
            theme="danger"
            type="button"
            @click="deleteDefinition"
          >
            {{ t('common.delete') }}
          </LteButton>
        </div>

        <h2 id="workflow-component-definition-heading" class="h5 mb-3">
          {{ t('workflowComponents.definition') }}
        </h2>
        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label" for="workflow-component-definition-name">
              {{ t('fields.name') }}
            </label>
            <input
              id="workflow-component-definition-name"
              v-model="definitionDraft.name"
              class="form-control"
            >
          </div>
          <div class="col-md-6">
            <label class="form-label" for="workflow-component-runtime-kind">
              {{ t('workflowComponents.runtimeKind') }}
            </label>
            <select id="workflow-component-runtime-kind" class="form-select" disabled>
              <option>python-command</option>
            </select>
          </div>
          <div class="col-12">
            <label class="form-label" for="workflow-component-definition-description">
              {{ t('fields.description') }}
            </label>
            <textarea
              id="workflow-component-definition-description"
              v-model="definitionDraft.description"
              class="form-control"
              rows="2"
            />
          </div>
          <div class="col-lg-6">
            <label class="form-label" for="workflow-component-input-endpoints">
              {{ t('workflowComponents.inputEndpoints') }}
            </label>
            <textarea
              id="workflow-component-input-endpoints"
              v-model="definitionDraft.inputEndpointsJson"
              class="form-control font-monospace"
              rows="10"
            />
          </div>
          <div class="col-lg-6">
            <label class="form-label" for="workflow-component-output-endpoints">
              {{ t('workflowComponents.outputEndpoints') }}
            </label>
            <textarea
              id="workflow-component-output-endpoints"
              v-model="definitionDraft.outputEndpointsJson"
              class="form-control font-monospace"
              rows="10"
            />
          </div>
          <div class="col-lg-6">
            <label class="form-label" for="workflow-component-config-schema">
              {{ t('workflowComponents.configSchema') }}
            </label>
            <textarea
              id="workflow-component-config-schema"
              v-model="definitionDraft.configSchemaJson"
              class="form-control font-monospace"
              rows="14"
            />
          </div>
          <div class="col-lg-6">
            <label class="form-label" for="workflow-component-python-source">
              {{ t('workflowComponents.pythonSource') }}
            </label>
            <textarea
              id="workflow-component-python-source"
              v-model="definitionDraft.pythonSource"
              class="form-control font-monospace"
              rows="14"
              spellcheck="false"
            />
          </div>
          <div class="col-12">
            <label class="form-label" for="workflow-component-python-requirements">
              {{ t('workflowComponents.pythonRequirements') }}
            </label>
            <textarea
              id="workflow-component-python-requirements"
              v-model="definitionDraft.pythonRequirements"
              class="form-control font-monospace"
              rows="4"
              spellcheck="false"
            />
          </div>
        </div>
        <div class="d-flex justify-content-end mt-3">
          <LteButton :disabled="savingDefinition" theme="primary" type="button" @click="saveDefinition">
            {{ t('common.save') }}
          </LteButton>
        </div>
      </section>

      <section class="border-top mt-4 pt-4" aria-labelledby="workflow-component-instance-heading">
        <div class="d-flex flex-wrap align-items-end gap-2 mb-3">
          <div class="flex-grow-1">
            <label class="form-label" for="workflow-component-instance-picker">
              {{ t('workflowComponents.instance') }}
            </label>
            <select
              id="workflow-component-instance-picker"
              v-model="selectedInstanceId"
              class="form-select"
              :disabled="!selectedDefinitionId"
              @change="selectInstance"
            >
              <option value="">{{ t('workflowComponents.newInstance') }}</option>
              <option v-for="item in instances" :key="item.id" :value="item.id">
                {{ item.name }}
              </option>
            </select>
          </div>
          <LteButton :disabled="!selectedDefinitionId" theme="success" type="button" @click="newInstance">
            {{ t('common.new') }}
          </LteButton>
          <LteButton
            :disabled="!instanceDraft.id"
            theme="danger"
            type="button"
            @click="deleteInstance"
          >
            {{ t('common.delete') }}
          </LteButton>
        </div>

        <h2 id="workflow-component-instance-heading" class="h5 mb-3">
          {{ t('workflowComponents.instance') }}
        </h2>
        <fieldset :disabled="!selectedDefinitionId">
          <div class="row g-3">
            <div class="col-md-6">
              <label class="form-label" for="workflow-component-instance-name">
                {{ t('fields.name') }}
              </label>
              <input
                id="workflow-component-instance-name"
                v-model="instanceDraft.name"
                class="form-control"
              >
            </div>
            <div class="col-md-6">
              <label class="form-label" for="workflow-component-instance-description">
                {{ t('fields.description') }}
              </label>
              <input
                id="workflow-component-instance-description"
                v-model="instanceDraft.description"
                class="form-control"
              >
            </div>
            <div class="col-12">
              <label class="form-label" for="workflow-component-instance-config">
                {{ t('workflowComponents.instanceConfig') }}
              </label>
              <textarea
                id="workflow-component-instance-config"
                v-model="instanceDraft.configJson"
                class="form-control font-monospace"
                rows="10"
              />
            </div>
          </div>
          <div class="d-flex justify-content-end mt-3">
            <LteButton :disabled="savingInstance" theme="primary" type="button" @click="saveInstance">
              {{ t('common.save') }}
            </LteButton>
          </div>
        </fieldset>
      </section>
    </div>
  </PageShell>
</template>
