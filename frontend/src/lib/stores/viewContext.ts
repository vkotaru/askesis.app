import { writable, derived, get } from 'svelte/store';
import { api, type SharedWithMe, type DataCategory } from '$lib/api/client';

interface ViewContextState {
  viewingUserId: number | null;
  viewingUser: SharedWithMe | null;
  sharedWithMe: SharedWithMe[];
  loading: boolean;
}

function createViewContextStore() {
  const { subscribe, set, update } = writable<ViewContextState>({
    viewingUserId: null,
    viewingUser: null,
    sharedWithMe: [],
    loading: false,
  });

  return {
    subscribe,

    async load() {
      update((s) => ({ ...s, loading: true }));
      try {
        const sharedWithMe = await api.getSharedWithMe();
        update((s) => ({ ...s, sharedWithMe, loading: false }));
      } catch {
        update((s) => ({ ...s, sharedWithMe: [], loading: false }));
      }
    },

    viewAs(user: SharedWithMe) {
      update((s) => ({
        ...s,
        viewingUserId: user.owner_id,
        viewingUser: user,
      }));
    },

    viewOwn() {
      update((s) => ({
        ...s,
        viewingUserId: null,
        viewingUser: null,
      }));
    },

    hasAccess(category: DataCategory): boolean {
      const state = get({ subscribe });
      if (!state.viewingUser) return true;
      return state.viewingUser.categories.includes(category);
    },
  };
}

export const viewContext = createViewContextStore();

// Derived stores for convenience
export const isViewingOther = derived(viewContext, ($ctx) => $ctx.viewingUserId !== null);
export const viewingUserId = derived(viewContext, ($ctx) => $ctx.viewingUserId);
export const viewingUser = derived(viewContext, ($ctx) => $ctx.viewingUser);
export const sharedWithMe = derived(viewContext, ($ctx) => $ctx.sharedWithMe);
