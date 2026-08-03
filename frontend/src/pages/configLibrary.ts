import type {
  BlockType,
  CatalogResponse,
  PrimaryAgent,
  SavedBlock,
  Subagent,
  ValidationReport,
} from '@/api'

export type LibraryCategoryId = BlockType | 'primary-agent' | 'subagent-profile'
export type LibraryItem = SavedBlock | PrimaryAgent | Subagent

export interface ConfigLibraryApi {
  getCatalog(): Promise<CatalogResponse>
  validateRepository(): Promise<ValidationReport>
  listBlocks(type: BlockType): Promise<SavedBlock[]>
  listPrimaryAgents(): Promise<PrimaryAgent[]>
  listSubagents(): Promise<Subagent[]>
  copyBlock(type: BlockType, id: string, name: string): Promise<SavedBlock>
  copyPrimaryAgent(id: string, name: string): Promise<PrimaryAgent>
  copySubagent(id: string, componentName: string): Promise<Subagent>
  deleteBlock(type: BlockType, id: string): Promise<{ ok: boolean }>
  deleteUnsupportedBlock(id: string): Promise<{ ok: boolean }>
  deletePrimaryAgent(id: string): Promise<{ ok: boolean }>
  deleteSubagent(id: string): Promise<{ ok: boolean }>
  deleteBlocks(type: BlockType, ids: string[]): Promise<{ deleted: number }>
  deletePrimaryAgents(ids: string[]): Promise<{ deleted: number }>
  deleteSubagents(ids: string[]): Promise<{ deleted: number }>
}

export const agentLibraryCategories = [
  'primary-agent',
  'subagent-profile',
] as const

export function routeCategory(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function editLocation(category: LibraryCategoryId, id: string): {
  path: string
  query: { id: string }
} {
  if (category === 'primary-agent') return { path: '/agents/primary', query: { id } }
  if (category === 'subagent-profile') return { path: '/agents/subagents', query: { id } }
  return { path: `/components/${category}`, query: { id } }
}
