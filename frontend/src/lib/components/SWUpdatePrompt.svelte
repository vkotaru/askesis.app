<script lang="ts">
  import { useRegisterSW } from 'virtual:pwa-register/svelte';
  import { RefreshCw, X } from 'lucide-svelte';
  import { hasLiveSession } from '$lib/stores/workout';

  const { needRefresh, updateServiceWorker } = useRegisterSW({
    onRegisteredSW(swUrl: string, registration: ServiceWorkerRegistration | undefined) {
      // Check for updates every 60 minutes
      if (registration) {
        setInterval(() => {
          registration.update();
        }, 60 * 60 * 1000);
      }
    },
  });

  let dismissed = false;

  /**
   * Never mid-workout.
   *
   * The prompt is deliberately kept — CLAUDE.md is emphatic that it is what
   * guarantees new JS lands before Dexie opens, so migrations run. But accepting
   * it reloads the page, and while a set is being typed that costs the scroll
   * position, the open keyboard and the user's attention. The draft itself
   * survives (Dexie v7 is additive and nothing upgrades it), so this only
   * defers the offer until the session is finished — the service worker still
   * installs in the background exactly as before.
   */
  $: show = $needRefresh && !dismissed && !$hasLiveSession;

  function handleUpdate() {
    updateServiceWorker(true);
  }

  function handleDismiss() {
    dismissed = true;
  }
</script>

{#if show}
  <div
    class="fixed bottom-4 left-4 right-4 z-50 mx-auto max-w-md rounded-lg border border-primary-200 bg-white p-4 shadow-lg dark:border-primary-700 dark:bg-gray-800 sm:left-auto sm:right-4"
    role="alert"
  >
    <div class="flex items-center gap-3">
      <div class="flex-shrink-0 rounded-full bg-primary-100 p-2 dark:bg-primary-900">
        <RefreshCw class="h-4 w-4 text-primary-600 dark:text-primary-400" />
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium text-gray-900 dark:text-gray-100">
          New version available
        </p>
        <p class="text-xs text-gray-500 dark:text-gray-400">
          Tap update to get the latest features.
        </p>
      </div>
      <button
        on:click={handleUpdate}
        class="flex-shrink-0 rounded-md bg-primary-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-600 transition-colors"
      >
        Update
      </button>
      <button
        on:click={handleDismiss}
        class="flex-shrink-0 rounded-md p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        aria-label="Dismiss"
      >
        <X class="h-4 w-4" />
      </button>
    </div>
  </div>
{/if}
