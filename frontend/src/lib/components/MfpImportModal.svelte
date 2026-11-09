<script lang="ts">
  // Import MyFitnessPal "Meals" screenshots. Two round trips to the same
  // endpoint: a dry run whose text is the preview, then the real write on
  // confirmation. The server's text is shown as-is -- it is written for a
  // person and already short -- and the only decision made here is whether
  // the "refused" line (the double-count guard) gets overridden with force.
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
  let fileInput: HTMLInputElement | null = null;

  $: refused = step === 'preview' && /^\s*! refused:/m.test(text);
  $: nothingToWrite = step === 'preview' && /^Would write 0\b/m.test(text);

  function close() {
    show = false;
    step = 'pick';
    files = [];
    text = '';
    error = '';
    force = false;
    dispatch('close');
  }

  function handleFiles(e: Event) {
    const input = e.target as HTMLInputElement;
    if (!input.files?.length) return;
    files = Array.from(input.files);
    input.value = '';
    preview();
  }

  async function preview() {
    step = 'previewing';
    error = '';
    force = false;
    try {
      text = await api.importMfpScreenshots(files, todayOnThisDevice(), { dryRun: true });
      step = 'preview';
    } catch (err) {
      error = describe(err);
      step = 'pick';
    }
  }

  async function write() {
    step = 'writing';
    error = '';
    try {
      text = await api.importMfpScreenshots(files, todayOnThisDevice(), { dryRun: false, force });
      step = 'done';
      dispatch('success');
    } catch (err) {
      error = describe(err);
      step = 'preview';
    }
  }

  // "Today"/"Yesterday" in a screenshot mean the day on the phone that took
  // it, so the server is told this device's date and never consults its own.
  function todayOnThisDevice(): string {
    return format(new Date(), 'yyyy-MM-dd');
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
        <button on:click={close} class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg" aria-label="Close">
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
              <input
                bind:this={fileInput}
                type="file"
                accept="image/*"
                multiple
                on:change={handleFiles}
                class="hidden"
              />
            </label>
            <p class="text-xs text-gray-500 mt-4">
              Read on the server with OCR. Nothing is written until you confirm.
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
          {#if refused}
            <label class="mt-4 flex items-start gap-2 text-sm">
              <input type="checkbox" bind:checked={force} class="mt-1" />
              <span>
                <strong>Overwrite this day's totals.</strong> Its protein, carbs and fat were
                typed in for the whole day, so logging meals with their own macros would count
                them twice. Ticking this sets the day to what the screenshot says.
              </span>
            </label>
          {/if}
        {/if}
      </div>

      <div class="flex items-center justify-end gap-3 p-4 border-t border-gray-200 dark:border-gray-700">
        {#if step === 'preview'}
          <button on:click={() => { step = 'pick'; text = ''; }} class="btn-secondary">Other screenshots</button>
          <button
            on:click={write}
            disabled={(refused && !force) || (nothingToWrite && !force)}
            class="btn-primary"
          >
            {refused && force ? 'Overwrite and log' : 'Log these meals'}
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
