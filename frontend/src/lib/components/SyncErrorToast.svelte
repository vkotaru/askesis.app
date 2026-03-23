<script lang="ts">
  import { AlertTriangle, X } from 'lucide-svelte';
  import { syncErrors } from '$lib/sync';

  function dismiss() {
    syncErrors.set([]);
  }
</script>

{#if $syncErrors.length > 0}
  <div
    class="fixed top-4 left-4 right-4 z-50 mx-auto max-w-md rounded-lg bg-red-50 border border-red-200 p-4 shadow-lg dark:bg-red-900/50 dark:border-red-700"
    role="alert"
  >
    <div class="flex items-start gap-3">
      <AlertTriangle class="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium text-red-800 dark:text-red-200">
          Sync had {$syncErrors.length} error{$syncErrors.length === 1 ? '' : 's'}
        </p>
        <ul class="mt-1 text-xs text-red-600 dark:text-red-300 space-y-0.5">
          {#each $syncErrors.slice(0, 3) as error}
            <li class="truncate">{error}</li>
          {/each}
          {#if $syncErrors.length > 3}
            <li>...and {$syncErrors.length - 3} more</li>
          {/if}
        </ul>
      </div>
      <button
        on:click={dismiss}
        class="flex-shrink-0 rounded-md p-1 text-red-400 hover:text-red-600 dark:hover:text-red-300"
        aria-label="Dismiss"
      >
        <X class="h-4 w-4" />
      </button>
    </div>
  </div>
{/if}
