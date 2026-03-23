<script lang="ts">
  import { useRegisterSW } from 'virtual:pwa-register/svelte';
  import { RefreshCw, X } from 'lucide-svelte';

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

  $: show = $needRefresh && !dismissed;

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
