import {
  createMiddlewareEntry,
  customMiddlewareAdapter,
} from './blocks/customMiddleware'
import { customToolAdapter } from './blocks/customTool'
import { exceptionRetryAdapter } from './blocks/exceptionRetry'
import { filesystemAdapter } from './blocks/filesystem'
import { filesystemPermissionsAdapter } from './blocks/filesystemPermissions'
import { modelAdapter } from './blocks/model'
import { outputModeAdapter } from './blocks/outputMode'
import { promptCachingAdapter } from './blocks/promptCaching'
import { skillAdapter } from './blocks/skill'
import { subagentAdapter } from './blocks/subagent'
import { summarizationAdapter } from './blocks/summarization'
import { systemPromptAdapter } from './blocks/systemPrompt'
import { todoListAdapter } from './blocks/todoList'
import { workflowInputContextAdapter } from './blocks/workflowInputContext'
import { workflowPrepareAdapter } from './blocks/workflowPrepare'

export type {
  CustomMiddlewareCatalogItem,
  CustomMiddlewareDraft,
} from './blocks/customMiddleware'
export type {
  CustomToolCatalogItem,
  CustomToolDraft,
} from './blocks/customTool'
export type {
  ExceptionRetryCondition,
  ExceptionRetryDefaults,
  ExceptionRetryDraft,
} from './blocks/exceptionRetry'
export type {
  FilesystemDefaults,
  FilesystemDraft,
  FilesystemImportSource,
  FilesystemToolDefault,
  MappedDirectory,
  VirtualSource,
} from './blocks/filesystem'
export type {
  FilesystemPermissionEntryDraft,
  FilesystemPermissionsDefaults,
  FilesystemPermissionsDraft,
  FilesystemPermissionValue,
} from './blocks/filesystemPermissions'
export type {
  ModelApiRecord,
  ModelDraft,
  ModelProviderSettingInput,
} from './blocks/model'
export type { OutputModeDefaults, OutputModeDraft } from './blocks/outputMode'
export type {
  PromptCachingDefaults,
  PromptCachingDraft,
} from './blocks/promptCaching'
export type { BlockDraftBase } from './blocks/shared'
export type { SkillCatalogItem, SkillDefaults, SkillDraft } from './blocks/skill'
export type { SubagentDefaults, SubagentDraft } from './blocks/subagent'
export type {
  SummarizationDefaults,
  SummarizationDraft,
  SummarizationThresholdDraft,
  SummarizationThresholdType,
} from './blocks/summarization'
export type { SystemPromptDraft } from './blocks/systemPrompt'
export type { TodoListDefaults, TodoListDraft } from './blocks/todoList'
export type {
  WorkflowInputContextDefaults,
  WorkflowInputContextDraft,
  WorkflowInputContextRole,
  WorkflowInputContextSlotDraft,
} from './blocks/workflowInputContext'
export type { WorkflowPrepareDefaults, WorkflowPrepareDraft } from './blocks/workflowPrepare'

export {
  createMiddlewareEntry,
  customMiddlewareAdapter,
  customToolAdapter,
  exceptionRetryAdapter,
  filesystemAdapter,
  filesystemPermissionsAdapter,
  modelAdapter,
  outputModeAdapter,
  promptCachingAdapter,
  skillAdapter,
  subagentAdapter,
  summarizationAdapter,
  systemPromptAdapter,
  todoListAdapter,
  workflowInputContextAdapter,
  workflowPrepareAdapter,
}

export const blockTypes = [
  'model',
  'custom-tool',
  'custom-middleware',
  'output-mode',
  'exception-retry',
  'filesystem',
  'filesystem-permissions',
  'skill',
  'system-prompt',
  'subagent',
  'todo-list',
  'summarization',
  'prompt-caching',
  'workflow-input-context',
] as const

export const managedComponentTypes = [...blockTypes, 'workflow-prepare'] as const

export const blockAdapters = {
  model: modelAdapter,
  'custom-tool': customToolAdapter,
  'custom-middleware': customMiddlewareAdapter,
  'output-mode': outputModeAdapter,
  'exception-retry': exceptionRetryAdapter,
  filesystem: filesystemAdapter,
  'filesystem-permissions': filesystemPermissionsAdapter,
  skill: skillAdapter,
  'system-prompt': systemPromptAdapter,
  subagent: subagentAdapter,
  'todo-list': todoListAdapter,
  summarization: summarizationAdapter,
  'prompt-caching': promptCachingAdapter,
  'workflow-input-context': workflowInputContextAdapter,
  'workflow-prepare': workflowPrepareAdapter,
} as const
