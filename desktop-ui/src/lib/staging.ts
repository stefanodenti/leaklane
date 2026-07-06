import { browser } from '$app/environment';
import { writable } from 'svelte/store';
import type { SearchResult, StagedRepository } from './types';

const STORAGE_KEY = 'leaklane-staging';

function initialValue(): StagedRepository[] {
  if (!browser) return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function createStagingStore() {
  const store = writable<StagedRepository[]>(initialValue());

  if (browser) {
    store.subscribe((items) => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    });
  }

  return {
    subscribe: store.subscribe,
    add(repo: SearchResult | StagedRepository) {
      store.update((items) => {
        if (!repo.url || items.some((item) => item.url === repo.url)) return items;
        return [
          ...items,
          {
            name: repo.name || repoNameFromUrl(repo.url),
            url: repo.url,
            description: repo.description,
            provider: repo.provider,
            language: repo.language,
            stars: repo.stars
          }
        ];
      });
    },
    remove(url: string) {
      store.update((items) => items.filter((item) => item.url !== url));
    },
    clear() {
      store.set([]);
    }
  };
}

function repoNameFromUrl(url: string) {
  try {
    const parsed = new URL(url);
    return parsed.pathname.replace(/^\/|\.git$/g, '') || url;
  } catch {
    return url;
  }
}

export const staging = createStagingStore();
