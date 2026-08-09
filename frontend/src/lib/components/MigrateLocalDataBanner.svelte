<script lang="ts">
  /**
   * One-time offer to rescue data logged under the old local-profile mode.
   *
   * Local-profile mode is gone, but a browser that used it still holds those
   * rows in IndexedDB and nowhere else — no server ever saw them. This runs
   * once after login, and only shows anything if such rows actually exist.
   *
   * Deliberately a banner, not confirm(): a modal dialog here would block the
   * first paint of the app behind a decision the user has no context for, and
   * confirm() is suppressed outright in some installed-PWA contexts.
   */
  import { onMount } from 'svelte';
  import { Database, X } from 'lucide-svelte';
  import { db } from '$lib/db';
  import { countLocalProfileData, migrateLocalToCloud } from '$lib/sync';

  export let userId: number;

  /**
   * Dexie settings key recording that the question is settled for good —
   * set only when the data has actually moved, or when there was none to
   * move. "Not now" hides the banner for this session only; the rows are the
   * single copy of that data, so a stray tap must not bury the offer forever.
   */
  const DISMISSED_KEY = 'localProfileMigrationHandled';

  let total = 0;
  let photosSkipped = 0;
  let visible = false;
  let busy = false;
  let done = '';
  let failed = '';

  async function markHandled() {
    try {
      await db.settings.put({ key: DISMISSED_KEY, value: true });
    } catch {
      // Best effort — worst case the banner offers once more.
    }
  }

  onMount(async () => {
    try {
      const handled = await db.settings.get(DISMISSED_KEY);
      if (handled?.value) return;

      const counts = await countLocalProfileData(userId);
      total =
        counts.dailyLogs +
        counts.activities +
        counts.meals +
        counts.foods +
        counts.measurements;
      photosSkipped = counts.photosSkipped;

      if (total > 0) {
        visible = true;
      } else {
        // Nothing stranded on this device — never ask again.
        await markHandled();
      }
    } catch (err) {
      console.warn('[askesis] Local-profile migration check failed:', err);
    }
  });

  async function migrate() {
    if (busy) return;
    busy = true;
    failed = '';
    try {
      const counts = await migrateLocalToCloud(userId);
      const moved =
        counts.dailyLogs +
        counts.activities +
        counts.meals +
        counts.foods +
        counts.measurements;
      done = `${moved} ${moved === 1 ? 'entry' : 'entries'} queued for upload.`;
      await markHandled();
    } catch (err) {
      failed = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

  function dismiss() {
    visible = false;
  }
</script>

{#if visible}
  <div
    class="mb-4 rounded-xl border border-primary-200 dark:border-primary-800 bg-primary-50 dark:bg-primary-900/30 p-4"
    role="status"
  >
    <div class="flex items-start gap-3">
      <Database size={20} class="text-primary-600 dark:text-primary-400 flex-shrink-0 mt-0.5" />
      <div class="flex-1 min-w-0">
        {#if done}
          <p class="text-sm text-gray-800 dark:text-gray-100">{done}</p>
          {#if photosSkipped > 0}
            <p class="text-xs text-gray-600 dark:text-gray-400 mt-1">
              {photosSkipped} progress {photosSkipped === 1 ? 'photo' : 'photos'} can't be moved
              automatically — please re-upload {photosSkipped === 1 ? 'it' : 'them'}.
            </p>
          {/if}
        {:else}
          <p class="text-sm font-medium text-gray-900 dark:text-white">
            {total} {total === 1 ? 'entry' : 'entries'} on this device aren't in your account
          </p>
          <p class="text-xs text-gray-600 dark:text-gray-400 mt-1">
            They were logged under a local profile, which no longer exists. Moving them
            uploads them to <span class="font-medium">your account</span> — it can't be undone,
            but nothing is deleted from this device.
            {#if photosSkipped > 0}
              Progress photos ({photosSkipped}) have to be re-uploaded by hand.
            {/if}
          </p>
          {#if failed}
            <p class="text-xs text-red-600 dark:text-red-400 mt-2">Migration failed: {failed}</p>
          {/if}
          <div class="flex items-center gap-3 mt-3">
            <button
              type="button"
              on:click={migrate}
              disabled={busy}
              class="btn-primary px-3 py-1.5 text-xs disabled:opacity-60"
            >
              {busy ? 'Moving…' : 'Move them to my account'}
            </button>
            <button
              type="button"
              on:click={dismiss}
              disabled={busy}
              class="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            >
              Not now
            </button>
          </div>
        {/if}
      </div>
      <button
        type="button"
        on:click={dismiss}
        class="p-1 -m-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 flex-shrink-0"
        aria-label="Dismiss"
      >
        <X size={16} />
      </button>
    </div>
  </div>
{/if}
