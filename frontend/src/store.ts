import { create } from 'zustand'
import type { Range } from './lib/types'

interface UiState {
  range: Range
  setRange: (range: Range) => void
}

export const useUi = create<UiState>((set) => ({
  range: '6h',
  setRange: (range) => set({ range }),
}))
