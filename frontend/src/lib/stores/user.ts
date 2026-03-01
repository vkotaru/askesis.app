import { writable } from 'svelte/store';
import type { User } from '$lib/api/client';

export const user = writable<User | null>(null);
export const userLoading = writable(true);
