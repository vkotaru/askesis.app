<script lang="ts">
  import { Watch } from 'lucide-svelte';

  /**
   * Marks a value that arrived from a device rather than from the user.
   *
   * Renders **nothing** for `undefined` (unknown — every row predating the
   * provenance column) and for `'manual'`. That is what lets this be dropped
   * anywhere without the UI sprouting empty states on an install where no
   * importer is switched on.
   */
  export let source: string | undefined = undefined;
  export let size = 12;

  const LABELS: Record<string, string> = { garmin: 'From Garmin' };

  $: label = source ? LABELS[source] : undefined;
</script>

{#if label}
  <span
    class="inline-flex items-center text-cardio-500 dark:text-cardio-400 align-middle"
    title={label}
    aria-label={label}
  >
    <Watch size={size} aria-hidden="true" />
  </span>
{/if}
