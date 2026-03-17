<script lang="ts">
  import { onMount } from 'svelte';
  import { format, addDays, subDays, parseISO } from 'date-fns';
  import { Camera, Upload, Trash2, ChevronLeft, ChevronRight, Image, AlertTriangle, GitCompare, X } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type ProgressPhoto, type PhotoView, type DriveStatus } from '$lib/api/client';

  const VIEWS: { value: PhotoView; label: string; emoji: string }[] = [
    { value: 'front', label: 'Front', emoji: '🧍' },
    { value: 'side', label: 'Side', emoji: '🧍‍♂️' },
    { value: 'back', label: 'Back', emoji: '🔙' },
  ];

  let selectedDate = format(new Date(), 'yyyy-MM-dd');
  let photos: ProgressPhoto[] = [];
  let loading = true;
  let uploading: PhotoView | null = null;
  let driveStatus: DriveStatus | null = null;
  let fileInputs: Record<PhotoView, HTMLInputElement | null> = {
    front: null,
    side: null,
    back: null,
  };

  // Comparison mode
  let compareMode = false;
  let compareView: PhotoView = 'front';
  let compareLeftDate = '';
  let compareRightDate = format(new Date(), 'yyyy-MM-dd');
  let allPhotoDates: string[] = [];
  let compareLeftPhoto: ProgressPhoto | null = null;
  let compareRightPhoto: ProgressPhoto | null = null;
  let loadingCompare = false;

  async function loadAllPhotoDates() {
    try {
      // Get all photos to extract unique dates
      const allPhotos = await api.getPhotos(undefined, undefined, undefined, undefined);
      const dates = [...new Set(allPhotos.map(p => p.date))].sort();
      allPhotoDates = dates;
      // Set default comparison dates
      if (dates.length >= 2) {
        compareLeftDate = dates[0]; // Oldest
        compareRightDate = dates[dates.length - 1]; // Latest
      } else if (dates.length === 1) {
        compareLeftDate = dates[0];
        compareRightDate = dates[0];
      }
    } catch (err) {
      console.error('Failed to load photo dates:', err);
    }
  }

  async function loadComparePhotos() {
    loadingCompare = true;
    try {
      const [leftPhotos, rightPhotos] = await Promise.all([
        api.getPhotosByDate(compareLeftDate, undefined),
        api.getPhotosByDate(compareRightDate, undefined),
      ]);
      compareLeftPhoto = leftPhotos.find(p => p.view === compareView) || null;
      compareRightPhoto = rightPhotos.find(p => p.view === compareView) || null;
    } catch (err) {
      console.error('Failed to load comparison photos:', err);
    } finally {
      loadingCompare = false;
    }
  }

  function toggleCompareMode() {
    compareMode = !compareMode;
    if (compareMode) {
      loadAllPhotoDates();
    }
  }

  // Reload comparison when dates or view change
  $: if (compareMode && compareLeftDate && compareRightDate && compareView) {
    loadComparePhotos();
  }

  async function checkDriveStatus() {
    try {
      driveStatus = await api.getDriveStatus();
    } catch (err) {
      console.error('Failed to check Drive status:', err);
      driveStatus = { configured: false, working: false, message: 'Unable to check Drive status' };
    }
  }

  async function loadPhotos() {
    loading = true;
    try {
      photos = await api.getPhotosByDate(selectedDate, undefined);
    } catch (err) {
      console.error('Failed to load photos:', err);
      photos = [];
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    checkDriveStatus();
    loadPhotos();
  });

  function handleDateChange(e: Event) {
    selectedDate = (e.target as HTMLInputElement).value;
    loadPhotos();
  }

  function prevDay() {
    selectedDate = format(subDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadPhotos();
  }

  function nextDay() {
    selectedDate = format(addDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadPhotos();
  }

  function getPhotoForView(view: PhotoView): ProgressPhoto | undefined {
    return photos.find((p) => p.view === view);
  }

  function triggerUpload(view: PhotoView) {
    fileInputs[view]?.click();
  }

  async function handleFileSelect(e: Event, view: PhotoView) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    uploading = view;
    try {
      await api.uploadPhoto(file, selectedDate, view);
      await loadPhotos();
    } catch (err) {
      console.error('Failed to upload photo:', err);
    } finally {
      uploading = null;
      input.value = '';
    }
  }

  async function deletePhoto(photo: ProgressPhoto) {
    if (!confirm('Delete this photo?')) return;
    try {
      await api.deletePhoto(photo.id);
      await loadPhotos();
    } catch (err) {
      console.error('Failed to delete photo:', err);
    }
  }
</script>

<svelte:head>
  <title>Progress Photos - Askesis</title>
</svelte:head>

<div>
  <div class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-2xl font-bold flex items-center gap-2">
        <Camera size={24} class="text-accent-500" />
        Progress Photos
      </h1>
      <p class="text-gray-500 text-sm mt-1">Track your body transformation</p>
    </div>
    <div class="flex items-center gap-4">
      <!-- Compare button -->
      <button
        type="button"
        on:click={toggleCompareMode}
        class={clsx(
          'flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors',
          compareMode
            ? 'bg-primary-500 text-white'
            : 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600'
        )}
      >
        {#if compareMode}
          <X size={18} />
          Exit Compare
        {:else}
          <GitCompare size={18} />
          Compare
        {/if}
      </button>

      {#if !compareMode}
        <div class="flex items-center gap-2">
          <button
            type="button"
            on:click={prevDay}
            class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            <ChevronLeft size={20} />
          </button>
          <input
            type="date"
            value={selectedDate}
            on:change={handleDateChange}
            class="input max-w-[180px]"
          />
          <button
            type="button"
            on:click={nextDay}
            class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            <ChevronRight size={20} />
          </button>
        </div>
      {/if}
    </div>
  </div>

  {#if driveStatus && !driveStatus.working}
    <div class="mb-6 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl">
      <div class="flex items-start gap-3">
        <AlertTriangle size={20} class="text-amber-500 mt-0.5 flex-shrink-0" />
        <div>
          <p class="font-medium text-amber-800 dark:text-amber-200">Google Drive Not Connected</p>
          <p class="text-sm text-amber-700 dark:text-amber-300 mt-1">
            {driveStatus.message}
          </p>
          <a href="/auth/logout" class="inline-block mt-2 text-sm font-medium text-amber-600 dark:text-amber-400 hover:underline">
            Log out and reconnect
          </a>
        </div>
      </div>
    </div>
  {/if}

  {#if compareMode}
    <!-- Comparison View -->
    <div class="space-y-6">
      <!-- View selector -->
      <div class="flex justify-center gap-2">
        {#each VIEWS as { value, label, emoji }}
          <button
            type="button"
            on:click={() => compareView = value}
            class={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors',
              compareView === value
                ? 'bg-primary-500 text-white'
                : 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600'
            )}
          >
            <span>{emoji}</span>
            {label}
          </button>
        {/each}
      </div>

      {#if allPhotoDates.length < 2}
        <div class="card p-12 text-center text-gray-500">
          <GitCompare size={48} class="mx-auto mb-4 opacity-30" />
          <p class="font-medium">Not enough photos to compare</p>
          <p class="text-sm mt-2">Upload photos on at least 2 different dates to use comparison</p>
        </div>
      {:else}
        <!-- Side by side comparison -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <!-- Left (Before) -->
          <div class="card overflow-hidden">
            <div class="p-4 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
              <h3 class="font-semibold text-gray-600 dark:text-gray-400">Before</h3>
              <select
                bind:value={compareLeftDate}
                class="input text-sm py-1 px-2 max-w-[150px]"
              >
                {#each allPhotoDates as date}
                  <option value={date}>{format(parseISO(date), 'MMM d, yyyy')}</option>
                {/each}
              </select>
            </div>
            <div class="aspect-[3/4] relative bg-gray-50 dark:bg-gray-800">
              {#if loadingCompare}
                <div class="w-full h-full flex items-center justify-center">
                  <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
                </div>
              {:else if compareLeftPhoto}
                <img
                  src={api.getPhotoUrl(compareLeftPhoto.id)}
                  alt="Before - {compareView} view"
                  class="w-full h-full object-cover"
                />
                <div class="absolute bottom-2 left-2 bg-black/70 text-white text-xs px-2 py-1 rounded">
                  {format(parseISO(compareLeftDate), 'MMM d, yyyy')}
                </div>
              {:else}
                <div class="w-full h-full flex flex-col items-center justify-center text-gray-400">
                  <Image size={48} class="mb-3 opacity-30" />
                  <span class="text-sm">No {compareView} photo on this date</span>
                </div>
              {/if}
            </div>
          </div>

          <!-- Right (After) -->
          <div class="card overflow-hidden">
            <div class="p-4 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
              <h3 class="font-semibold text-primary-600 dark:text-primary-400">After</h3>
              <select
                bind:value={compareRightDate}
                class="input text-sm py-1 px-2 max-w-[150px]"
              >
                {#each allPhotoDates as date}
                  <option value={date}>{format(parseISO(date), 'MMM d, yyyy')}</option>
                {/each}
              </select>
            </div>
            <div class="aspect-[3/4] relative bg-gray-50 dark:bg-gray-800">
              {#if loadingCompare}
                <div class="w-full h-full flex items-center justify-center">
                  <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
                </div>
              {:else if compareRightPhoto}
                <img
                  src={api.getPhotoUrl(compareRightPhoto.id)}
                  alt="After - {compareView} view"
                  class="w-full h-full object-cover"
                />
                <div class="absolute bottom-2 left-2 bg-primary-500/90 text-white text-xs px-2 py-1 rounded">
                  {format(parseISO(compareRightDate), 'MMM d, yyyy')}
                </div>
              {:else}
                <div class="w-full h-full flex flex-col items-center justify-center text-gray-400">
                  <Image size={48} class="mb-3 opacity-30" />
                  <span class="text-sm">No {compareView} photo on this date</span>
                </div>
              {/if}
            </div>
          </div>
        </div>

        <!-- Time difference -->
        {#if compareLeftDate && compareRightDate}
          {@const daysDiff = Math.abs(Math.round((parseISO(compareRightDate).getTime() - parseISO(compareLeftDate).getTime()) / (1000 * 60 * 60 * 24)))}
          <div class="text-center text-gray-500 text-sm">
            {#if daysDiff === 0}
              Same day
            {:else if daysDiff === 1}
              1 day apart
            {:else if daysDiff < 7}
              {daysDiff} days apart
            {:else if daysDiff < 30}
              {Math.round(daysDiff / 7)} week{Math.round(daysDiff / 7) > 1 ? 's' : ''} apart
            {:else}
              {Math.round(daysDiff / 30)} month{Math.round(daysDiff / 30) > 1 ? 's' : ''} apart
            {/if}
          </div>
        {/if}
      {/if}
    </div>
  {:else if loading}
    <div class="card p-12 flex items-center justify-center">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>
  {:else}
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      {#each VIEWS as { value, label, emoji }}
        {@const photo = getPhotoForView(value)}
        {@const isUploading = uploading === value}
        <div class="card overflow-hidden">
          <div class="p-4 border-b border-gray-100 dark:border-gray-700">
            <h3 class="font-semibold flex items-center gap-2">
              <span class="text-xl">{emoji}</span>
              {label} View
            </h3>
          </div>

          <div class="aspect-[3/4] relative bg-gray-50 dark:bg-gray-800">
            {#if photo}
              <img
                src={api.getPhotoUrl(photo.id)}
                alt="{label} view"
                class="w-full h-full object-cover"
              />
              <div class="absolute inset-0 bg-black/0 hover:bg-black/40 transition-colors group">
                  <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      on:click={() => triggerUpload(value)}
                      class="p-3 bg-white/90 rounded-full mr-2 hover:bg-white transition-colors"
                      title="Replace photo"
                    >
                      <Upload size={20} class="text-gray-700" />
                    </button>
                    <button
                      on:click={() => deletePhoto(photo)}
                      class="p-3 bg-white/90 rounded-full hover:bg-white transition-colors"
                      title="Delete photo"
                    >
                      <Trash2 size={20} class="text-accent-500" />
                    </button>
                  </div>
                </div>
            {:else}
              <button
                on:click={() => triggerUpload(value)}
                disabled={isUploading}
                class="w-full h-full flex flex-col items-center justify-center text-gray-400 hover:text-primary-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                {#if isUploading}
                  <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500 mb-2"></div>
                  <span class="text-sm">Uploading...</span>
                {:else}
                  <Image size={48} class="mb-3 opacity-50" />
                  <span class="text-sm font-medium">Click to upload</span>
                  <span class="text-xs mt-1">JPEG, PNG, or HEIC</span>
                {/if}
              </button>
            {/if}
          </div>

          <input
            type="file"
            accept="image/jpeg,image/png,image/heic,image/heif,image/webp"
            class="hidden"
            bind:this={fileInputs[value]}
            on:change={(e) => handleFileSelect(e, value)}
          />
        </div>
      {/each}
    </div>

    <!-- Tips -->
    <div class="mt-8 card p-6">
      <h3 class="font-semibold text-gray-700 dark:text-gray-300 mb-3">Tips for Progress Photos</h3>
      <ul class="text-sm text-gray-500 space-y-2">
        <li>Take photos in the same location with consistent lighting</li>
        <li>Wear the same or similar clothing for accurate comparison</li>
        <li>Stand in the same position each time</li>
        <li>Take photos at the same time of day (morning is best)</li>
        <li>Photos are automatically resized, optimized, and stored in your Google Drive</li>
      </ul>
    </div>
  {/if}
</div>
