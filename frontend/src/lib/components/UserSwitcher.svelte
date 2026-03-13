<script lang="ts">
  import { onMount } from 'svelte';
  import { Users, ChevronDown, Eye } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { viewContext, isViewingOther, viewingUser, sharedWithMe } from '$lib/stores/viewContext';

  let showDropdown = false;

  onMount(() => {
    viewContext.load();
  });

  function handleSelect(user: typeof $sharedWithMe[0] | null) {
    if (user) {
      viewContext.viewAs(user);
    } else {
      viewContext.viewOwn();
    }
    showDropdown = false;
  }

  function handleClickOutside(e: MouseEvent) {
    const target = e.target as HTMLElement;
    if (!target.closest('.user-switcher')) {
      showDropdown = false;
    }
  }
</script>

<svelte:window on:click={handleClickOutside} />

{#if $sharedWithMe.length > 0}
  <div class="user-switcher relative">
    <button
      on:click|stopPropagation={() => (showDropdown = !showDropdown)}
      class={clsx(
        'flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors',
        $isViewingOther
          ? 'bg-accent-100 dark:bg-accent-900/30 text-accent-700 dark:text-accent-300'
          : 'hover:bg-gray-100 dark:hover:bg-gray-700'
      )}
    >
      {#if $isViewingOther}
        <Eye size={16} />
        <span class="font-medium">{$viewingUser?.owner_name}</span>
      {:else}
        <Users size={16} />
        <span>My Data</span>
      {/if}
      <ChevronDown size={14} class={clsx('transition-transform', showDropdown && 'rotate-180')} />
    </button>

    {#if showDropdown}
      <div
        class="absolute right-0 top-full mt-1 w-56 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 z-50"
      >
        <button
          on:click={() => handleSelect(null)}
          class={clsx(
            'w-full px-4 py-2 text-left text-sm flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700',
            !$isViewingOther && 'bg-primary-50 dark:bg-gray-700'
          )}
        >
          <div class="w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
            <span class="text-primary-600 dark:text-primary-400 font-medium text-xs">Me</span>
          </div>
          <span>My Data</span>
        </button>

        <div class="border-t border-gray-100 dark:border-gray-700 my-1"></div>
        <div class="px-4 py-1 text-xs text-gray-500 uppercase tracking-wide">Shared with me</div>

        {#each $sharedWithMe as user}
          <button
            on:click={() => handleSelect(user)}
            class={clsx(
              'w-full px-4 py-2 text-left text-sm flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700',
              $viewingUser?.owner_id === user.owner_id && 'bg-accent-50 dark:bg-accent-900/20'
            )}
          >
            {#if user.owner_picture}
              <img src={user.owner_picture} alt={user.owner_name} class="w-8 h-8 rounded-full" />
            {:else}
              <div class="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-600 flex items-center justify-center">
                <span class="text-gray-600 dark:text-gray-300 font-medium text-xs">
                  {user.owner_name?.charAt(0) || '?'}
                </span>
              </div>
            {/if}
            <div class="flex-1 min-w-0">
              <div class="font-medium truncate">{user.owner_name}</div>
              <div class="text-xs text-gray-500 truncate">{user.categories.length} categories</div>
            </div>
          </button>
        {/each}
      </div>
    {/if}
  </div>
{/if}
