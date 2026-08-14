import { create } from 'zustand'
import type { Range } from './lib/types'

export type Tab = 'dashboard' | 'routes' | 'map' | 'path' | 'data'

interface UiState {
  range: Range
  network: string // "current" | "all" | numeric id
  tab: Tab
  setRange: (range: Range) => void
  setNetwork: (network: string) => void
  setTab: (tab: Tab) => void
}

export const useUi = create<UiState>((set) => ({
  range: '6h',
  network: 'current',
  tab: 'dashboard',
  setRange: (range) => set({ range }),
  setNetwork: (network) => set({ network }),
  setTab: (tab) => set({ tab }),
}))
