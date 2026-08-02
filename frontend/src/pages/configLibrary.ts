import type {
  BlockType,
  CatalogResponse,
  PrimaryAgent,
  SavedBlock,
  SubagentOverride,
  ValidationReport,
  WorkerProfile,
} from '@/api'

export type LibraryCategoryId = BlockType | 'primary-agent' | 'subagent-override' | 'worker-profile'
export type LibraryItem = SavedBlock | PrimaryAgent | SubagentOverride | WorkerProfile

export interface ConfigLibraryApi {
  getCatalog(): Promise<CatalogResponse>
  validateRepository(): Promise<ValidationReport>
  listBlocks(type: BlockType): Promise<SavedBlock[]>
  listPrimaryAgents(): Promise<PrimaryAgent[]>
  listSubagentOverrides(): Promise<SubagentOverride[]>
  listWorkerProfiles(): Promise<WorkerProfile[]>
  copyBlock(type: BlockType, id: string, name: string): Promise<SavedBlock>
  copyPrimaryAgent(id: string, name: string): Promise<PrimaryAgent>
  copySubagentOverride(id: string, name: string): Promise<SubagentOverride>
  copyWorkerProfile(id: string, name: string): Promise<WorkerProfile>
  deleteBlock(type: BlockType, id: string): Promise<{ ok: boolean }>
  deleteUnsupportedBlock(id: string): Promise<{ ok: boolean }>
  deletePrimaryAgent(id: string): Promise<{ ok: boolean }>
  deleteSubagentOverride(id: string): Promise<{ ok: boolean }>
  deleteWorkerProfile(id: string): Promise<{ ok: boolean }>
  deleteBlocks(type: BlockType, ids: string[]): Promise<{ deleted: number }>
  deletePrimaryAgents(ids: string[]): Promise<{ deleted: number }>
  deleteSubagentOverrides(ids: string[]): Promise<{ deleted: number }>
  deleteWorkerProfiles(ids: string[]): Promise<{ deleted: number }>
}

export const agentLibraryCategories = [
  'primary-agent',
  'subagent-override',
  'worker-profile',
] as const

export function routeCategory(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function editLocation(category: LibraryCategoryId, id: string): {
  path: string
  query: { id: string }
} {
  if (category === 'primary-agent') return { path: '/agents/primary', query: { id } }
  if (category === 'subagent-override') return { path: '/agents/subagents', query: { id } }
  if (category === 'worker-profile') return { path: '/agents/workers', query: { id } }
  return { path: `/components/${category}`, query: { id } }
}
