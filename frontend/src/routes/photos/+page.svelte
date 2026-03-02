<script lang="ts">
  import { onMount } from 'svelte';
  import { format, addDays, subDays, parseISO } from 'date-fns';
  import { Camera, Upload, Trash2, ChevronLeft, ChevronRight, Image } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type ProgressPhoto, type PhotoView } from '$lib/api/client';

  const VIEWS: { value: PhotoView; label: string; emoji: string }[] = [
    { value: 'front', label: 'Front', emoji: '🧍' },
    { value: 'side', label: 'Side', emoji: '🧍‍♂️' },
    { value: 'back', label: 'Back', emoji: '🔙' },
  ];

  let selectedDate = format(new Date(), 'yyyy-MM-dd');
  let photos: ProgressPhoto[] = [];
  let loading = true;
  let uploading: PhotoView | null = null;
  let fileInputs: Record<PhotoView, HTMLInputElement | null> = {
    front: null,
    side: null,
    back: null,
  };

  async function loadPhotos() {
    loading = true;
    try {
      photos = await api.getPhotosByDate(selectedDate);
    } catch (err) {
      console.error('Failed to load photos:', err);
      photos = [];
    } finally {
      loading = false;
    }
  }

  onMount(loadPhotos);

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
  </div>

  {#if loading}
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
        <li>Photos are automatically resized and optimized for storage</li>
      </ul>
    </div>
  {/if}
</div>
