<script lang="ts">
  // Thin <img> wrapper that swaps in a placeholder if the image fails to load.
  //
  // Requests are always same-origin and cookie-authenticated, so the browser
  // loads API paths like /api/photos/file/<id> directly — no fetch hop needed.
  //
  // Sizing is entirely the caller's: both the <img> and the placeholder get
  // exactly `extraClass` and nothing else. Adding w-full/h-full here would
  // override callers that size the element themselves (e.g. the w-16 h-16
  // meal thumbnails on /nutrition).
  export let src: string | undefined | null = '';
  export let alt = '';
  let extraClass = '';
  export { extraClass as class };

  let errored = false;

  // Clear the error state whenever the source changes.
  $: src, (errored = false);
</script>

{#if src && !errored}
  <img {src} {alt} class={extraClass} on:error={() => (errored = true)} />
{:else if src}
  <div class="flex items-center justify-center text-gray-400 text-xs {extraClass}">
    Image unavailable
  </div>
{/if}
