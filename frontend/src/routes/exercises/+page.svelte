<script lang="ts">
  /**
   * The shared movement library.
   *
   * Everything here belongs to the install rather than to an account: whatever
   * one of you adds, the other sees, and an edit here changes what the other
   * person's picker says. That is deliberate — two people training out of one
   * library is the whole point — but it is surprising enough that the page says
   * so out loud rather than letting someone discover it by renaming "Squat".
   *
   * This is also the only place `video_url` and the form notes can be set. The
   * logger can create an entry mid-workout, but only by name; the rest is
   * typed once, here, and then shows up next to the movement forever.
   *
   * Entries are archived, never deleted: sessions reference them by id, and
   * removing one would strand the other person's history as well as your own.
   */
  import { onMount } from 'svelte';
  import { Search, Pencil, Archive, ArchiveRestore, ExternalLink, Dumbbell, X } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type CatalogEntry } from '$lib/api/client';

  let entries: CatalogEntry[] = [];
  let loading = true;
  let error = '';
  let query = '';
  let showArchived = false;

  let editing: CatalogEntry | null = null;
  let formName = '';
  let formMuscle = '';
  let formVideo = '';
  let formNotes = '';
  let saving = false;

  onMount(load);

  async function load() {
    loading = true;
    try {
      entries = await api.getCatalog(query || undefined, showArchived);
      error = '';
    } catch {
      error = navigator.onLine
        ? 'Could not load the exercise library.'
        : 'The library needs a connection. Logging a session still works offline.';
    } finally {
      loading = false;
    }
  }

  function openEdit(entry: CatalogEntry) {
    editing = entry;
    formName = entry.name;
    formMuscle = entry.muscle_group ?? '';
    formVideo = entry.video_url ?? '';
    formNotes = entry.notes ?? '';
    error = '';
  }

  async function save() {
    if (!editing || !formName.trim() || saving) return;
    saving = true;
    try {
      await api.updateCatalogEntry(editing.id, {
        name: formName.trim(),
        muscle_group: formMuscle.trim() || null,
        video_url: formVideo.trim() || null,
        notes: formNotes.trim() || null,
      });
      editing = null;
      await load();
    } catch (e) {
      // The server refuses a name that already exists and a link that is not
      // http(s); both are worth showing verbatim rather than "could not save".
      error = e instanceof Error ? e.message : 'Could not save the exercise.';
    } finally {
      saving = false;
    }
  }

  async function archive(entry: CatalogEntry) {
    if (
      !confirm(
        `Archive "${entry.name}"?\n\nIt disappears from the picker for everyone on this install. ` +
          `Past sessions keep it, and you can restore it here.`
      )
    )
      return;
    try {
      await api.archiveCatalogEntry(entry.id);
      await load();
    } catch {
      error = 'Could not archive that exercise.';
    }
  }

  /** Restoring is re-adding by name: the server revives the archived row. */
  async function restore(entry: CatalogEntry) {
    try {
      await api.createCatalogEntry({ name: entry.name });
      await load();
    } catch {
      error = 'Could not restore that exercise.';
    }
  }
</script>

<svelte:head><title>Exercises · Askesis</title></svelte:head>

<div>
  <div class="mb-4">
    <h1 class="text-2xl font-bold">Exercises</h1>
    <p class="text-sm text-gray-500">
      The shared movement library — everyone on this install sees the same list
    </p>
  </div>

  <div class="flex items-center gap-2 mb-4">
    <div class="relative flex-1">
      <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
      <input
        bind:value={query}
        on:input={load}
        placeholder="Search exercises"
        aria-label="Search exercises"
        class="input pl-9"
      />
    </div>
    <label class="flex items-center gap-1.5 text-xs text-gray-500 whitespace-nowrap">
      <input type="checkbox" bind:checked={showArchived} on:change={load} class="rounded" />
      Archived
    </label>
  </div>

  {#if error}
    <p class="mb-4 text-sm text-red-500">{error}</p>
  {/if}

  {#if loading}
    <div class="flex justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>
  {:else if entries.length === 0}
    <div class="card p-8 text-center">
      <Dumbbell size={32} class="mx-auto text-gray-300 mb-3" />
      <p class="text-gray-500">
        {query ? 'Nothing matches that' : 'No exercises yet'}
      </p>
      <p class="text-sm text-gray-400">
        Movements are added while logging a session — the picker there has an
        “add” option. Come back here to give one a video link or form notes.
      </p>
    </div>
  {:else}
    <div class="space-y-2">
      {#each entries as entry}
        <div
          class={clsx(
            'card p-3 flex items-start gap-3',
            entry.is_archived && 'opacity-60'
          )}
        >
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <p class="font-medium truncate">{entry.name}</p>
              {#if entry.is_archived}
                <span class="text-[10px] uppercase tracking-wide text-gray-400">archived</span>
              {/if}
            </div>
            {#if entry.muscle_group}
              <p class="text-xs text-gray-400">{entry.muscle_group}</p>
            {/if}
            {#if entry.notes}
              <p class="text-xs text-gray-500 mt-1 line-clamp-2">{entry.notes}</p>
            {/if}
          </div>

          {#if entry.video_url}
            <a
              href={entry.video_url}
              target="_blank"
              rel="noopener noreferrer"
              title="How to do this"
              aria-label="How to do {entry.name}"
              class="p-1 text-gray-400 hover:text-primary-500"
            >
              <ExternalLink size={16} />
            </a>
          {/if}
          <button
            type="button"
            title="Edit"
            aria-label="Edit {entry.name}"
            class="p-1 text-gray-400 hover:text-primary-500"
            on:click={() => openEdit(entry)}
          >
            <Pencil size={16} />
          </button>
          {#if entry.is_archived}
            <button
              type="button"
              title="Restore"
              aria-label="Restore {entry.name}"
              class="p-1 text-gray-400 hover:text-primary-500"
              on:click={() => restore(entry)}
            >
              <ArchiveRestore size={16} />
            </button>
          {:else}
            <button
              type="button"
              title="Archive"
              aria-label="Archive {entry.name}"
              class="p-1 text-gray-400 hover:text-amber-500"
              on:click={() => archive(entry)}
            >
              <Archive size={16} />
            </button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if editing}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div
    class="fixed inset-0 z-[70] bg-black/50 flex items-end sm:items-center justify-center"
    on:click={() => (editing = null)}
  >
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="bg-white dark:bg-gray-800 w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-4 space-y-3 max-h-[85vh] overflow-y-auto"
      on:click|stopPropagation
    >
      <div class="flex items-center gap-2">
        <h2 class="font-semibold flex-1">Edit exercise</h2>
        <button type="button" class="p-1 text-gray-400" on:click={() => (editing = null)}>
          <X size={18} />
        </button>
      </div>

      <div>
        <label for="ex-name" class="label">Name</label>
        <input id="ex-name" bind:value={formName} class="input" />
      </div>
      <div>
        <label for="ex-muscle" class="label">
          Muscle group <span class="text-gray-400 font-normal">(optional)</span>
        </label>
        <input id="ex-muscle" bind:value={formMuscle} placeholder="Chest" class="input" />
      </div>
      <div>
        <label for="ex-video" class="label">
          Video link <span class="text-gray-400 font-normal">(optional)</span>
        </label>
        <input
          id="ex-video"
          type="url"
          bind:value={formVideo}
          placeholder="https://youtube.com/…"
          class="input"
        />
      </div>
      <div>
        <label for="ex-notes" class="label">
          Form notes <span class="text-gray-400 font-normal">(optional)</span>
        </label>
        <textarea
          id="ex-notes"
          bind:value={formNotes}
          rows="3"
          placeholder="Brace first, then unrack…"
          class="input"
        ></textarea>
      </div>

      <p class="text-[10px] text-gray-400 border-t border-gray-200 dark:border-gray-700 pt-2">
        This library is shared. Renaming or re-describing an exercise changes it for
        everyone on this install; past sessions keep the name they were logged with.
      </p>

      <div class="flex justify-end gap-2">
        <button type="button" class="btn-secondary" on:click={() => (editing = null)}>
          Cancel
        </button>
        <button type="button" class="btn-primary" disabled={saving} on:click={save}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  </div>
{/if}
