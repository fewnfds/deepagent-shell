import type { InjectionKey } from 'vue'

import { managementApi } from '@/api'
import type {
  BlockType,
  CapabilityManifest as ApiCapabilityManifest,
  CapabilityOverride as ApiCapabilityOverride,
  CapabilityReference as ApiCapabilityReference,
  CatalogResponse,
  DraftValidationRequest as ApiDraftValidationRequest,
  PrimaryAgent,
  PrimaryAgentPayload as ApiPrimaryAgentPayload,
  SavedBlock,
  SubagentBinding as ApiSubagentBinding,
  SubagentOverride,
  SubagentOverridePayload as ApiSubagentOverridePayload,
  ValidationIssue as ApiValidationIssue,
  ValidationReport as ApiValidationReport,
  WorkerBinding as ApiWorkerBinding,
  WorkerCapabilityOverride as ApiWorkerCapabilityOverride,
  WorkerProfile,
  WorkerProfilePayload as ApiWorkerProfilePayload,
} from '@/api'

export type CapabilityType = BlockType
export type OverrideMode = 'inherit' | 'replace' | 'disabled'
export type StoredOverrideMode = Exclude<OverrideMode, 'inherit'>

export type CapabilityManifest = ApiCapabilityManifest
export type AgentCatalog = CatalogResponse
export type StoredBlock = SavedBlock
export type CapabilityReference = ApiCapabilityReference
export type SubagentBinding = ApiSubagentBinding
export type WorkerBinding = ApiWorkerBinding

export interface PrimaryAgentProfile extends Omit<PrimaryAgent, 'subagents' | 'workers'> {
  id: string
  subagents: SubagentBinding[]
  workers: WorkerBinding[]
}

export type PrimaryAgentPayload = ApiPrimaryAgentPayload
export type CapabilityOverride = ApiCapabilityOverride

export interface OverrideSelection {
  type: CapabilityType
  mode: OverrideMode
  block_id: string
}

export type SubagentOverrideProfile = SubagentOverride
export type SubagentOverridePayload = ApiSubagentOverridePayload
export type WorkerCapabilityOverride = ApiWorkerCapabilityOverride
export type WorkerProfileRecord = WorkerProfile
export type WorkerProfilePayload = ApiWorkerProfilePayload
export type ValidationIssue = ApiValidationIssue
export type ValidationReport = ApiValidationReport
export type DraftValidationRequest = ApiDraftValidationRequest

export interface AgentAuthoringService {
  getCatalog(): Promise<AgentCatalog>
  listBlocks(type: CapabilityType): Promise<StoredBlock[]>
  listPrimaryAgents(): Promise<PrimaryAgent[]>
  getPrimaryAgent(id: string): Promise<PrimaryAgent>
  createPrimaryAgent(payload: PrimaryAgentPayload): Promise<PrimaryAgent>
  updatePrimaryAgent(id: string, payload: PrimaryAgentPayload): Promise<PrimaryAgent>
  listSubagentOverrides(): Promise<SubagentOverrideProfile[]>
  getSubagentOverride(id: string): Promise<SubagentOverrideProfile>
  createSubagentOverride(payload: SubagentOverridePayload): Promise<SubagentOverrideProfile>
  updateSubagentOverride(id: string, payload: SubagentOverridePayload): Promise<SubagentOverrideProfile>
  listWorkerProfiles(): Promise<WorkerProfileRecord[]>
  getWorkerProfile(id: string): Promise<WorkerProfileRecord>
  createWorkerProfile(payload: WorkerProfilePayload): Promise<WorkerProfileRecord>
  updateWorkerProfile(id: string, payload: WorkerProfilePayload): Promise<WorkerProfileRecord>
  validateDraft(request: DraftValidationRequest): Promise<ValidationReport>
}

export const agentAuthoringServiceKey: InjectionKey<AgentAuthoringService> = Symbol('agent-authoring-service')

export const managementAgentAuthoringService: AgentAuthoringService = {
  getCatalog: () => managementApi.getCatalog(),
  listBlocks: (type) => managementApi.listBlocks(type),
  listPrimaryAgents: () => managementApi.listPrimaryAgents(),
  getPrimaryAgent: (id) => managementApi.getPrimaryAgent(id),
  createPrimaryAgent: (payload) => managementApi.savePrimaryAgent(payload),
  updatePrimaryAgent: (id, payload) => managementApi.savePrimaryAgent({ id, ...payload }),
  listSubagentOverrides: () => managementApi.listSubagentOverrides(),
  getSubagentOverride: (id) => managementApi.getSubagentOverride(id),
  createSubagentOverride: (payload) => managementApi.saveSubagentOverride(payload),
  updateSubagentOverride: (id, payload) => managementApi.saveSubagentOverride({ id, ...payload }),
  listWorkerProfiles: () => managementApi.listWorkerProfiles(),
  getWorkerProfile: (id) => managementApi.getWorkerProfile(id),
  createWorkerProfile: (payload) => managementApi.saveWorkerProfile(payload),
  updateWorkerProfile: (id, payload) => managementApi.saveWorkerProfile({ id, ...payload }),
  validateDraft: (request) => managementApi.validateDraft(request),
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

export function blankSubagentBinding(): SubagentBinding {
  return {
    name: '',
    description: '',
    subagent_override_id: '',
  }
}

export function normalizeSubagentBinding(value: unknown): SubagentBinding {
  const source = record(value)
  return {
    name: text(source.name),
    description: text(source.description),
    subagent_override_id: text(source.subagent_override_id),
  }
}

export function blankWorkerBinding(): WorkerBinding {
  return {
    name: '',
    description: '',
    worker_profile_id: '',
  }
}

export function normalizeWorkerBinding(value: unknown): WorkerBinding {
  const source = record(value)
  return {
    name: text(source.name),
    description: text(source.description),
    worker_profile_id: text(source.worker_profile_id),
  }
}

export function blankPrimaryAgent(): PrimaryAgentProfile {
  return {
    id: '',
    name: '',
    capability_refs: [],
    subagents: [],
    workers: [],
  }
}

export function normalizePrimaryAgent(value: unknown): PrimaryAgentProfile {
  const source = record(value)
  const references = Array.isArray(source.capability_refs) ? source.capability_refs : []
  const subagents = Array.isArray(source.subagents) ? source.subagents : []
  const workers = Array.isArray(source.workers) ? source.workers : []
  return {
    id: text(source.id),
    name: text(source.name),
    capability_refs: references.map((item) => {
      const reference = record(item)
      return { type: text(reference.type) as CapabilityType, block_id: text(reference.block_id) }
    }),
    subagents: subagents.map(normalizeSubagentBinding),
    workers: workers.map(normalizeWorkerBinding),
  }
}

export function primaryAgentPayload(
  value: PrimaryAgentProfile,
): PrimaryAgentPayload {
  return {
    name: value.name.trim(),
    capability_refs: value.capability_refs
      .map((reference) => ({ type: reference.type, block_id: reference.block_id })),
    subagents: value.subagents.map((binding) => ({
      name: binding.name.trim(),
      description: binding.description,
      subagent_override_id: binding.subagent_override_id,
    })),
    workers: value.workers.map((binding) => ({
      name: binding.name.trim(),
      description: binding.description,
      worker_profile_id: binding.worker_profile_id,
    })),
  }
}

export function referenceId(value: PrimaryAgentProfile, type: CapabilityType): string {
  return value.capability_refs.find((item) => item.type === type)?.block_id ?? ''
}

export function setReference(value: PrimaryAgentProfile, type: CapabilityType, blockId: string): void {
  value.capability_refs = value.capability_refs.filter((item) => item.type !== type)
  if (blockId) value.capability_refs.push({ type, block_id: blockId })
}

export function blankSubagentOverride(): SubagentOverrideProfile {
  return {
    id: '',
    name: '',
    capability_overrides: [],
  }
}

export function normalizeSubagentOverride(value: unknown): SubagentOverrideProfile {
  const source = record(value)
  const overrides = Array.isArray(source.capability_overrides) ? source.capability_overrides : []
  return {
    id: text(source.id),
    name: text(source.name),
    capability_overrides: overrides.map((item): CapabilityOverride => {
      const override = record(item)
      return {
        type: text(override.type) as CapabilityType,
        mode: text(override.mode) as StoredOverrideMode,
        block_id: text(override.block_id),
      }
    }),
  }
}

export function overrideSelection(value: SubagentOverrideProfile, type: CapabilityType): OverrideSelection {
  return value.capability_overrides.find((item) => item.type === type)
    ?? { type, mode: 'inherit', block_id: '' }
}

export function setOverrideSelection(
  value: SubagentOverrideProfile,
  type: CapabilityType,
  mode: OverrideMode,
  blockId = '',
): void {
  value.capability_overrides = value.capability_overrides.filter((item) => item.type !== type)
  if (mode !== 'inherit') {
    value.capability_overrides.push({
      type,
      mode,
      block_id: mode === 'replace' ? blockId : '',
    })
  }
}

export function subagentOverridePayload(
  value: SubagentOverrideProfile,
): SubagentOverridePayload {
  return {
    name: value.name.trim(),
    capability_overrides: value.capability_overrides
      .map((selection) => ({ ...selection })),
  }
}

export function blankWorkerProfile(): WorkerProfileRecord {
  return {
    id: '',
    name: '',
    include_client_messages: true,
    capability_overrides: [],
  }
}

export function normalizeWorkerProfile(value: unknown): WorkerProfileRecord {
  const source = record(value)
  const overrides = Array.isArray(source.capability_overrides) ? source.capability_overrides : []
  return {
    id: text(source.id),
    name: text(source.name),
    include_client_messages: typeof source.include_client_messages === 'boolean'
      ? source.include_client_messages
      : true,
    capability_overrides: overrides.map((item): WorkerCapabilityOverride => {
      const override = record(item)
      return {
        type: text(override.type) as CapabilityType,
        mode: text(override.mode) as StoredOverrideMode,
        block_id: text(override.block_id),
      }
    }),
  }
}

export function workerOverrideSelection(
  value: WorkerProfileRecord,
  type: CapabilityType,
): OverrideSelection {
  return value.capability_overrides.find((item) => item.type === type)
    ?? { type, mode: 'inherit', block_id: '' }
}

export function setWorkerOverrideSelection(
  value: WorkerProfileRecord,
  type: CapabilityType,
  mode: OverrideMode,
  blockId = '',
): void {
  value.capability_overrides = value.capability_overrides.filter((item) => item.type !== type)
  if (mode !== 'inherit') {
    value.capability_overrides.push({
      type,
      mode,
      block_id: mode === 'replace' ? blockId : '',
    })
  }
}

export function workerProfilePayload(value: WorkerProfileRecord): WorkerProfilePayload {
  return {
    name: value.name.trim(),
    include_client_messages: value.include_client_messages,
    capability_overrides: value.capability_overrides.map((selection) => ({ ...selection })),
  }
}
