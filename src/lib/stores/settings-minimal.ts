import { writable, derived } from 'svelte/store';

export interface MinimalSettings {
  temperature: number;
  maxTokens: number;
  topP: number;
  topK: number;
  repeatPenalty: number;
  theme: 'light' | 'dark' | 'system';
  developerMode: boolean;
}

const defaultSettings: MinimalSettings = {
  temperature: 0.7,
  maxTokens: 2048,
  topP: 0.9,
  topK: 40,
  repeatPenalty: 1.1,
  theme: 'dark',
  developerMode: false,
};

function createSettingsStore() {
  const { subscribe, set, update } = writable<MinimalSettings>(defaultSettings);

  return {
    subscribe,
    set,
    update,
    reset: () => set(defaultSettings),
    updateParam: (key: keyof MinimalSettings, value: any) =>
      update((s) => ({ ...s, [key]: value })),
  };
}

export const settings = createSettingsStore();

export const visibleSettings = derived(settings, ($s) => ({
  temperature: $s.temperature,
  maxTokens: $s.maxTokens,
  theme: $s.theme,
}));

export const advancedSettings = derived(settings, ($s) => ({
  topP: $s.topP,
  topK: $s.topK,
  repeatPenalty: $s.repeatPenalty,
  developerMode: $s.developerMode,
}));