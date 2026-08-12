import type {
  ManagedComponentType,
  CatalogResponse,
  MainAgent,
  SavedBlock,
  Subagent,
  ValidationReport,
} from '@/api'

export type LibraryCategoryId = ManagedComponentType | 'main-agent' | 'subagent-profile'
export type LibraryItem = SavedBlock | MainAgent | Subagent

export interface ConfigLibraryApi {
  getCatalog(): Promise<CatalogResponse>
  validateRepository(): Promise<ValidationReport>
  listBlocks(type: ManagedComponentType): Promise<SavedBlock[]>
  listMainAgents(): Promise<MainAgent[]>
  listSubagents(): Promise<Subagent[]>
  copyBlock(type: ManagedComponentType, id: string, name: string): Promise<SavedBlock>
  copyMainAgent(id: string, name: string): Promise<MainAgent>
  copySubagent(id: string, componentName: string): Promise<Subagent>
  deleteBlock(type: ManagedComponentType, id: string): Promise<{ ok: boolean }>
  deleteUnsupportedBlock(id: string): Promise<{ ok: boolean }>
  deleteMainAgent(id: string): Promise<{ ok: boolean }>
  deleteSubagent(id: string): Promise<{ ok: boolean }>
  deleteBlocks(type: ManagedComponentType, ids: string[]): Promise<{ deleted: number }>
  deleteMainAgents(ids: string[]): Promise<{ deleted: number }>
  deleteSubagents(ids: string[]): Promise<{ deleted: number }>
}

export const agentLibraryCategories = [
  'main-agent',
  'subagent-profile',
] as const

export function routeCategory(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function editLocation(category: LibraryCategoryId, id: string): {
  path: string
  query: { id: string }
} {
  if (category === 'main-agent') return { path: '/agents/main', query: { id } }
  if (category === 'subagent-profile') return { path: '/agents/subagents', query: { id } }
  return { path: `/components/${category}`, query: { id } }
}
