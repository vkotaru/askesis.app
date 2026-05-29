<script lang="ts">
  // Image loader that works for both web (cookie auth) and Capacitor native
  // (bearer-token auth). Blob URLs and data URLs render directly; relative
  // API paths get fetched with auth headers and turned into object URLs.
  //
  // Browsers don't let you attach an Authorization header to <img src=...>,
  // so on native the only way to load /api/photos/file/<id> is to fetch the
  // bytes ourselves.
  import { onDestroy } from 'svelte';
  import { apiUrl, IS_NATIVE } from '$lib/config';
  import { authHeaders } from '$lib/auth';

  export let src: string | undefined | null = '';
  export let alt = '';
  let extraClass = '';
  export { extraClass as class };

  let resolvedSrc = '';
  let blobUrl: string | null = null;
  let loading = false;
  let errored = false;

  function isAlreadyResolvable(url: string): boolean {
    return (
      url.startsWith('blob:') ||
      url.startsWith('data:') ||
      url.startsWith('http://') ||
      url.startsWith('https://')
    );
  }

  function releaseBlob() {
    if (blobUrl) {
      URL.revokeObjectURL(blobUrl);
      blobUrl = null;
    }
  }

  async function resolve(src: string) {
    releaseBlob();
    errored = false;

    if (!src) {
      resolvedSrc = '';
      return;
    }

    if (isAlreadyResolvable(src)) {
      resolvedSrc = src;
      return;
    }

    // On web, the cookie does the work and the relative path loads fine.
    // Skip the fetch hop to keep the existing browser cache behavior.
    if (!IS_NATIVE) {
      resolvedSrc = src;
      return;
    }

    loading = true;
    try {
      const res = await fetch(apiUrl(src), {
        credentials: 'include',
        headers: await authHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      blobUrl = URL.createObjectURL(blob);
      resolvedSrc = blobUrl;
    } catch {
      errored = true;
      resolvedSrc = '';
    } finally {
      loading = false;
    }
  }

  $: resolve(src ?? '');

  onDestroy(releaseBlob);
</script>

{#if errored}
  <div class="flex items-center justify-center w-full h-full text-gray-400 text-xs {extraClass}">
    Image unavailable
  </div>
{:else if loading && !resolvedSrc}
  <div class="flex items-center justify-center w-full h-full {extraClass}">
    <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-500"></div>
  </div>
{:else if resolvedSrc}
  <img src={resolvedSrc} {alt} class={extraClass} />
{/if}
