<script lang="ts">
  // Import MyFitnessPal "Meals" screenshots. Round trips to one endpoint: a
  // dry run whose text is the preview, then the real write on confirmation.
  // The server's text is shown as-is -- it is written for a person -- and
  // the only decision made here is whether the double-count guard's refusal
  // is overridden with `force`. Ticking that re-runs the preview WITH force,
  // so what the overwrite would do is on screen before it happens.
  import { createEventDispatcher } from 'svelte';
  import { format } from 'date-fns';
  import { X, Image, AlertCircle, CheckCircle } from 'lucide-svelte';
  import { api, ApiError } from '$lib/api/client';

  export let show = false;

  const dispatch = createEventDispatcher<{ close: void; success: void }>();

  let step: 'pick' | 'previewing' | 'preview' | 'writing' | 'done' = 'pick';
  let files: File[] = [];
  let text = '';
  let error = '';
  let force = false;
  // "Today"/"Yesterday" in a screenshot mean the day on the device that took
  // it, so the server is told this device's date and never consults its own.
  // Captured once, at preview: a confirm after midnight must write the day
  // the user was shown.
  let today = '';
  // Bumped by every new request and by close(); a response whose generation
  // is stale (the modal was closed or re-driven meanwhile) is dropped, so a
  // reopened modal never shows a previous run's result.
  let generation = 0;

  // The guard tripped: the preview says "refused" (force off) or lists what
  // "forced" would drop (force on). Either way the checkbox belongs on screen.
  $: guardTripped = step === 'preview' && /^\s*! (refused|forced):/m.test(text);
  $: nothingToWrite = step === 'preview' && /^Would write 0\b/m.test(text);
  $: canWrite = step === 'preview' && !nothingToWrite && !(guardTripped && !force);

  function close() {
    if (step === 'writing') return; // the write is committing; closing would only hide the result
    generation += 1;
    show = false;
    step = 'pick';
    files = [];
    text = '';
    error = '';
    force = false;
    today = '';
    dispatch('close');
  }

  function handleFiles(e: Event) {
    const input = e.target as HTMLInputElement;
    if (!input.files?.length) return;
    files = Array.from(input.files);
    input.value = '';
    force = false;
    today = format(new Date(), 'yyyy-MM-dd');
    preview();
  }

  async function preview() {
    const mine = ++generation;
    step = 'previewing';
    error = '';
    try {
      const result = await api.importMfpScreenshots(files, today, { dryRun: true, force });
      if (mine !== generation) return;
      text = result;
      step = 'preview';
    } catch (err) {
      if (mine !== generation) return;
      error = describe(err);
      step = files.length && text ? 'preview' : 'pick';
    }
  }

  async function write() {
    const mine = ++generation;
    step = 'writing';
    error = '';
    try {
      const result = await api.importMfpScreenshots(files, today, { dryRun: false, force });
      if (mine !== generation) return;
      text = result;
      step = 'done';
      dispatch('success');
    } catch (err) {
      if (mine !== generation) return;
      error = describe(err);
      if (err instanceof ApiError && err.status === 409) {
        // The guard tripped between preview and write (or the preview's
        // refusal was for a different day). A fresh preview shows the
        // refusal next to the checkbox instead of a dead end.
        error += ' The preview below has been refreshed.';
        await preview();
        return;
      }
      step = 'preview';
    }
  }

  function toggleForce() {
    // bind:checked has already flipped `force`; the preview must reflect it.
    preview();
  }

  function describe(err: unknown): string {
    if (err instanceof ApiError) return err.message;
    if (err instanceof Error) return err.message;
    return 'Import failed';
  }
</script>

{#if show}
  <div class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" on:click|self={close}>
    <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-hidden flex flex-col">
      <div class="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <Image size={24} class="text-primary-500" />
          <h2 class="text-lg font-semibold">Import MyFitnessPal</h2>
        </div>
        <button
          on:click={close}
          disabled={step === 'writing'}
          class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-40"
          aria-label="Close"
        >
          <X size={20} />
        </button>
      </div>

      <div class="flex-1 overflow-y-auto p-6">
        {#if error}
          <div class="mb-4 p-3 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-lg flex items-start gap-2 text-sm">
            <AlertCircle size={18} class="shrink-0 mt-0.5" />
            <span class="whitespace-pre-wrap">{error}</span>
          </div>
        {/if}

        {#if step === 'pick'}
          <div class="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl p-8 text-center">
            <Image size={48} class="mx-auto text-gray-400 mb-4" />
            <p class="text-gray-600 dark:text-gray-400 mb-4">
              A screenshot of MyFitnessPal's <strong>Meals</strong> view, with the
              date and all four cards visible. Several screenshots may cover one
              day or several days.
            </p>
            <label class="btn-primary cursor-pointer inline-block">
              Choose screenshots
              <input type="file" accept="image/*" multiple on:change={handleFiles} class="hidden" />
            </label>
            <p class="text-xs text-gray-500 mt-4">
              Read on the server with OCR. Nothing is written until you confirm.
              "Today" and "Yesterday" are taken relative to this device's date.
            </p>
          </div>

        {:else if step === 'previewing' || step === 'writing'}
          <div class="text-center py-12">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
            <p class="text-gray-600 dark:text-gray-400">
              {step === 'previewing' ? 'Reading the screenshots…' : 'Logging meals…'}
            </p>
          </div>

        {:else if step === 'preview' || step === 'done'}
          {#if step === 'done'}
            <div class="flex items-center gap-2 text-green-600 dark:text-green-400 mb-3">
              <CheckCircle size={20} />
              <span class="font-medium">Logged</span>
            </div>
          {:else}
            <p class="text-sm text-gray-500 mb-3">
              Preview. Lines starting with <code>!</code> are warnings; nothing has been written yet.
            </p>
          {/if}
          <pre class="text-sm bg-gray-50 dark:bg-gray-900 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-words">{text}</pre>
          {#if guardTripped}
            <label class="mt-4 flex items-start gap-2 text-sm">
              <input type="checkbox" bind:checked={force} on:change={toggleForce} class="mt-1" />
              <span>
                <strong>Overwrite this day's totals.</strong> Its protein, carbs and fat were
                typed in for the whole day, so logging meals with their own macros would count
                them twice. Ticking this sets the day to what the screenshot says; the preview
                updates to show exactly what that drops.
              </span>
            </label>
          {/if}
        {/if}
      </div>

      <div class="flex items-center justify-end gap-3 p-4 border-t border-gray-200 dark:border-gray-700">
        {#if step === 'preview'}
          <button on:click={() => { generation += 1; step = 'pick'; text = ''; error = ''; force = false; }} class="btn-secondary">
            Other screenshots
          </button>
          <button on:click={write} disabled={!canWrite} class="btn-primary">
            {guardTripped && force ? 'Overwrite and log' : 'Log these meals'}
          </button>
        {:else if step === 'done'}
          <button on:click={close} class="btn-primary">Done</button>
        {:else if step === 'pick'}
          <button on:click={close} class="btn-secondary">Cancel</button>
        {/if}
      </div>
    </div>
  </div>
{/if}
