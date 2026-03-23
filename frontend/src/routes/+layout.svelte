<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';
  import { user, userLoading } from '$lib/stores/user';
  import { settings } from '$lib/stores/settings';
  import Layout from '$lib/components/Layout.svelte';
  import Login from '$lib/components/Login.svelte';
  import SWUpdatePrompt from '$lib/components/SWUpdatePrompt.svelte';
  import { hydrateFromServer } from '$lib/stores/data';
  import { sync } from '$lib/sync';

  onMount(async () => {
    try {
      const userData = await api.getMe();
      user.set(userData);
      await settings.load();
      // Hydrate Dexie from server (only if tables are empty)
      hydrateFromServer(userData.id).catch(() => {});
      // Sync any pending offline mutations
      sync().catch(() => {});
    } catch {
      user.set(null);
    } finally {
      userLoading.set(false);
    }
  });
</script>

{#if $userLoading}
  <div class="min-h-screen flex items-center justify-center bg-surface-light dark:bg-surface-dark">
    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
  </div>
{:else if $user}
  <Layout user={$user}>
    <slot />
  </Layout>
{:else}
  <Login />
{/if}

<SWUpdatePrompt />
