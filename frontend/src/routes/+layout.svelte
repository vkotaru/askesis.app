<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api/client';
  import { user, userLoading, loadCachedUser, cacheUser, clearCachedUser } from '$lib/stores/user';
  import { settings } from '$lib/stores/settings';
  import { routeAllowed } from '$lib/appMode';
  import Layout from '$lib/components/Layout.svelte';
  import Login from '$lib/components/Login.svelte';
  import SWUpdatePrompt from '$lib/components/SWUpdatePrompt.svelte';
  import SyncErrorToast from '$lib/components/SyncErrorToast.svelte';
  import MigrateLocalDataBanner from '$lib/components/MigrateLocalDataBanner.svelte';
  import { clearLocalSession, hydrateFromServer } from '$lib/stores/data';
  import { sync } from '$lib/sync';

  // Public routes bypass auth
  $: isPublicRoute = $page.url.pathname.startsWith('/report/');

  /**
   * Send a hidden section home.
   *
   * The sidebar already omits these in a restricted mode, but a bookmark, a
   * back button or a stale service-worker cache can still land on one — and a
   * page you were told does not exist, rendering anyway, reads as a bug rather
   * than as a setting.
   *
   * Not a security boundary and not pretending to be one: the data is the same
   * account's either way, and the API is unchanged. This is about the app being
   * coherent, so it waits for `$settings` to actually load (`app_mode` defaults
   * to 'full', so nothing is redirected while settings are in flight) and it
   * never touches a public route.
   */
  $: if (!isPublicRoute && $user && !routeAllowed($settings.app_mode, $page.url.pathname)) {
    goto('/', { replaceState: true });
  }

  onMount(async () => {
    if (isPublicRoute) {
      userLoading.set(false);
      return;
    }

    // Paint from the cached identity right away — /auth/me is a round-trip to
    // a home server over Tailscale and must not gate first render.
    const cached = await loadCachedUser();
    if (cached) {
      user.set(cached);
      userLoading.set(false);
      settings.load().catch(() => {});
    }

    // …then revalidate in the background.
    try {
      const userData = await api.getMe();

      // The session belongs to a different account than the one this device
      // cached — a sign-in that skipped our sign-out path, e.g. the cookie was
      // replaced in another tab. Drop the previous account's cache before a
      // single read can serve it. Unsent mutations are parked, not destroyed:
      // they stay tagged to their owner and only push under that account.
      if (cached && cached.id !== userData.id) {
        await clearLocalSession(true);
      }

      user.set(userData);
      await cacheUser(userData);
      await settings.load();
      // Hydrate Dexie from server (only if tables are empty)
      hydrateFromServer(userData.id).catch(() => {});
      // Sync any pending offline mutations
      sync().catch(() => {});
    } catch (err) {
      const unauthorized = err instanceof Error && err.message === 'Unauthorized';
      // Offline with a cached user: keep rendering the app. Only a real 401
      // (or having nothing cached in the first place) drops us to <Login>.
      if (unauthorized || !cached) {
        user.set(null);
        await clearCachedUser();
      }
    } finally {
      userLoading.set(false);
    }
  });
</script>

{#if isPublicRoute}
  <slot />
{:else if $userLoading}
  <div class="min-h-screen flex items-center justify-center bg-surface-light dark:bg-surface-dark">
    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
  </div>
{:else if $user}
  <Layout user={$user}>
    <!-- Mounts once per signed-in session and self-checks; renders nothing
         unless this browser is holding data from the retired local-profile
         mode that exists nowhere on the server. -->
    <MigrateLocalDataBanner userId={$user.id} />
    <slot />
  </Layout>
{:else}
  <Login />
{/if}

<SWUpdatePrompt />
<SyncErrorToast />
