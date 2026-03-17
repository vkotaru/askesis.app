<script lang="ts">
  import { page } from '$app/stores';
  import { Home, ClipboardList, Utensils, Apple, Activity, CalendarDays, Settings, LogOut, Ruler, Camera, MoreHorizontal, Menu, Users } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import type { User } from '$lib/api/client';
  import { settings } from '$lib/stores/settings';

  export let user: User;

  // All nav items
  const navItems = [
    { href: '/', icon: Home, label: 'Dashboard', color: 'text-primary-500' },
    { href: '/shared', icon: Users, label: 'Shared', color: 'text-accent-500' },
    { href: '/daily-log', icon: ClipboardList, label: 'Daily Log', color: 'text-rest-500' },
    { href: '/nutrition', icon: Utensils, label: 'Nutrition', color: 'text-nutrition-500' },
    { href: '/activities', icon: Activity, label: 'Activities', color: 'text-cardio-500' },
    { href: '/measurements', icon: Ruler, label: 'Measurements', color: 'text-strength-500' },
    { href: '/photos', icon: Camera, label: 'Photos', color: 'text-accent-500' },
    { href: '/calendar', icon: CalendarDays, label: 'Calendar', color: 'text-mood-4' },
    { href: '/nutrition/foods', icon: Apple, label: 'Foods', color: 'text-nutrition-500' },
    { href: '/settings', icon: Settings, label: 'Settings', color: 'text-gray-500' },
  ];

  // Mobile bottom nav: first 4 items + More
  const mobileNavItems = navItems.slice(0, 4);
  const moreMenuItems = navItems.slice(4);

  let showMoreMenu = false;
  let showMobileMenu = false;

  const widthClasses = {
    narrow: 'max-w-3xl',
    medium: 'max-w-5xl',
    wide: 'max-w-7xl',
    full: 'max-w-none',
  } as const;

  $: currentPath = $page.url.pathname;
  $: widthClass = widthClasses[$settings.content_width];
  $: isMoreActive = moreMenuItems.some(item => currentPath === item.href);

  function closeMenus() {
    showMoreMenu = false;
    showMobileMenu = false;
  }
</script>

<svelte:window on:click={closeMenus} />

<div class="min-h-screen flex flex-col md:flex-row bg-surface-light dark:bg-surface-dark">
  <!-- Mobile Header -->
  <header class="md:hidden fixed top-0 left-0 right-0 z-40 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3">
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-bold bg-gradient-to-r from-primary-600 to-primary-400 bg-clip-text text-transparent">
        Askesis
      </h1>
      <div class="flex items-center gap-3">
        <button
          on:click|stopPropagation={() => (showMobileMenu = !showMobileMenu)}
          class="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
        >
          <Menu size={20} class="text-gray-600 dark:text-gray-400" />
        </button>
      </div>
    </div>
  </header>

  <!-- Mobile slide-out menu -->
  {#if showMobileMenu}
    <div
      class="md:hidden fixed inset-0 z-50 bg-black/50"
      on:click={closeMenus}
      on:keydown={(e) => e.key === 'Escape' && closeMenus()}
      role="button"
      tabindex="0"
    >
      <div
        class="absolute right-0 top-0 h-full w-72 bg-white dark:bg-gray-800 shadow-xl"
        on:click|stopPropagation
        on:keydown|stopPropagation
        role="dialog"
      >
        <div class="p-4 border-b border-gray-200 dark:border-gray-700">
          <div class="flex items-center gap-3 p-2 rounded-lg bg-gray-50 dark:bg-gray-700/50">
            {#if user.picture}
              <img
                src={user.picture}
                alt={user.name}
                class="w-10 h-10 rounded-full ring-2 ring-primary-200 dark:ring-primary-800"
              />
            {:else}
              <div class="w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
                <span class="text-primary-600 dark:text-primary-400 font-semibold">
                  {user.name?.charAt(0) || 'U'}
                </span>
              </div>
            {/if}
            <div class="flex-1 min-w-0">
              <p class="font-medium truncate text-sm">{user.name}</p>
              <p class="text-xs text-gray-500 truncate">{user.email}</p>
            </div>
          </div>
        </div>
        <nav class="p-3">
          {#each navItems as { href, icon: Icon, label, color }}
            {@const isActive = currentPath === href}
            <a
              {href}
              on:click={closeMenus}
              class={clsx(
                'flex items-center gap-3 px-4 py-3 rounded-xl mb-1 transition-all',
                isActive
                  ? 'bg-primary-50 dark:bg-gray-700'
                  : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
              )}
            >
              <Icon size={20} class={clsx(isActive ? color : 'text-gray-400')} />
              <span class={clsx('font-medium', isActive ? 'text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400')}>
                {label}
              </span>
            </a>
          {/each}
        </nav>
        <div class="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-200 dark:border-gray-700">
          <a
            href="/auth/logout"
            class="flex items-center gap-2 text-sm text-gray-500 hover:text-accent-500 transition-colors px-2"
          >
            <LogOut size={16} />
            Sign out
          </a>
        </div>
      </div>
    </div>
  {/if}

  <!-- Desktop Sidebar -->
  <aside class="hidden md:flex w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex-col shadow-soft sticky top-0 h-screen">
    <div class="p-6">
      <h1 class="text-2xl font-bold bg-gradient-to-r from-primary-600 to-primary-400 bg-clip-text text-transparent">
        Askesis
      </h1>
      <p class="text-xs text-gray-400 mt-1">Health & Fitness Tracker</p>
    </div>

    <nav class="flex-1 px-3 overflow-y-auto">
      {#each navItems as { href, icon: Icon, label, color }}
        {@const isActive = currentPath === href}
        <a
          {href}
          class={clsx(
            'flex items-center gap-3 px-4 py-3 rounded-xl mb-1 transition-all duration-200',
            isActive
              ? 'bg-primary-50 dark:bg-gray-700 shadow-sm'
              : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
          )}
        >
          <Icon
            size={20}
            class={clsx(isActive ? color : 'text-gray-400')}
          />
          <span
            class={clsx(
              'font-medium',
              isActive ? 'text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400'
            )}
          >
            {label}
          </span>
        </a>
      {/each}
    </nav>

    <!-- User section -->
    <div class="p-4 border-t border-gray-100 dark:border-gray-700">
      <div class="flex items-center gap-3 mb-3 p-2 rounded-lg bg-gray-50 dark:bg-gray-700/50">
        {#if user.picture}
          <img
            src={user.picture}
            alt={user.name}
            class="w-10 h-10 rounded-full ring-2 ring-primary-200 dark:ring-primary-800"
          />
        {:else}
          <div class="w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
            <span class="text-primary-600 dark:text-primary-400 font-semibold">
              {user.name?.charAt(0) || 'U'}
            </span>
          </div>
        {/if}
        <div class="flex-1 min-w-0">
          <p class="font-medium truncate text-sm">{user.name}</p>
          <p class="text-xs text-gray-500 truncate">{user.email}</p>
        </div>
      </div>
      <a
        href="/auth/logout"
        class="flex items-center gap-2 text-sm text-gray-500 hover:text-accent-500 transition-colors px-2"
      >
        <LogOut size={16} />
        Sign out
      </a>
    </div>
  </aside>

  <!-- Main content -->
  <main class="flex-1 overflow-auto pt-14 pb-20 md:pt-0 md:pb-0">
    <div class={clsx('mx-auto transition-all duration-300 p-4 md:p-8 content-area', widthClass)}>
      <slot />
    </div>
  </main>

  <!-- Mobile Bottom Navigation -->
  <nav class="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 px-2 pb-safe">
    <div class="flex items-center justify-around py-2">
      {#each mobileNavItems as { href, icon: Icon, label, color }}
        {@const isActive = currentPath === href}
        <a
          {href}
          class={clsx(
            'flex flex-col items-center gap-1 px-3 py-2 rounded-xl transition-all min-w-[60px]',
            isActive ? 'text-primary-600 dark:text-primary-400' : 'text-gray-500'
          )}
        >
          <Icon size={22} class={isActive ? color : ''} />
          <span class="text-xs font-medium">{label.split(' ')[0]}</span>
        </a>
      {/each}

      <!-- More button -->
      <div class="relative">
        <button
          on:click|stopPropagation={() => (showMoreMenu = !showMoreMenu)}
          class={clsx(
            'flex flex-col items-center gap-1 px-3 py-2 rounded-xl transition-all min-w-[60px]',
            isMoreActive ? 'text-primary-600 dark:text-primary-400' : 'text-gray-500'
          )}
        >
          <MoreHorizontal size={22} />
          <span class="text-xs font-medium">More</span>
        </button>

        <!-- More menu popup -->
        {#if showMoreMenu}
          <div
            class="absolute bottom-full right-0 mb-2 w-48 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 py-2 overflow-hidden"
            on:click|stopPropagation
            on:keydown|stopPropagation
            role="menu"
          >
            {#each moreMenuItems as { href, icon: Icon, label, color }}
              {@const isActive = currentPath === href}
              <a
                {href}
                on:click={closeMenus}
                class={clsx(
                  'flex items-center gap-3 px-4 py-3 transition-all',
                  isActive
                    ? 'bg-primary-50 dark:bg-gray-700'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                )}
              >
                <Icon size={18} class={clsx(isActive ? color : 'text-gray-400')} />
                <span class={clsx('font-medium text-sm', isActive ? 'text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400')}>
                  {label}
                </span>
              </a>
            {/each}
          </div>
        {/if}
      </div>
    </div>
  </nav>
</div>

<style>
  /* Safe area for devices with home indicator */
  .pb-safe {
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }
</style>
