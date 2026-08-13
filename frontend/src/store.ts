import { create } from 'zustand'
import type { Range } from './lib/types'

interface UiState {
  range: Range
  network: string // "current" | "all" | numeric id
  setRange: (range: Range) => void
  setNetwork: (network: string) => void
}

export const useUi = create<UiState>((set) => ({
  range: '6h',
  network: 'current',
  setRange: (range) => set({ range }),
  setNetwork: (network) => set({ network }),
}))
