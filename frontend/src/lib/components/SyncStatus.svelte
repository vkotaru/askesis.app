<script lang="ts">
  import { Wifi, WifiOff, RefreshCw } from 'lucide-svelte';
  import { syncStatus } from '$lib/sync';
</script>

<div class="flex items-center gap-1.5">
  {#if $syncStatus.syncing}
    <RefreshCw class="h-3.5 w-3.5 text-primary-500 animate-spin" />
  {:else if $syncStatus.online}
    <Wifi class="h-3.5 w-3.5 text-green-500" />
  {:else}
    <WifiOff class="h-3.5 w-3.5 text-red-500" />
  {/if}

  {#if $syncStatus.pending > 0}
    <span
      class="inline-flex items-center justify-center rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900 dark:text-amber-300"
      title="{$syncStatus.pending} change{$syncStatus.pending === 1 ? '' : 's'} pending sync"
    >
      {$syncStatus.pending}
    </span>
  {/if}
</div>
