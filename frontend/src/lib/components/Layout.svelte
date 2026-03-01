<script lang="ts">
  import { page } from '$app/stores';
  import { Home, ClipboardList, Utensils, Activity, CalendarDays, Settings, LogOut } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import type { User } from '$lib/api/client';
  import { settings } from '$lib/stores/settings';

  export let user: User;

  const navItems = [
    { href: '/', icon: Home, label: 'Dashboard', color: 'text-primary-500' },
    { href: '/daily-log', icon: ClipboardList, label: 'Daily Log', color: 'text-rest-500' },
    { href: '/nutrition', icon: Utensils, label: 'Nutrition', color: 'text-nutrition-500' },
    { href: '/activities', icon: Activity, label: 'Activities', color: 'text-cardio-500' },
    { href: '/calendar', icon: CalendarDays, label: 'Calendar', color: 'text-strength-500' },
    { href: '/settings', icon: Settings, label: 'Settings', color: 'text-gray-500' },
  ];

  const widthClasses = {
    narrow: 'max-w-3xl',
    medium: 'max-w-5xl',
    wide: 'max-w-7xl',
    full: 'max-w-none',
  } as const;

  $: currentPath = $page.url.pathname;
  $: widthClass = widthClasses[$settings.content_width];
</script>

<div class="min-h-screen flex bg-surface-light dark:bg-surface-dark">
  <!-- Sidebar -->
  <aside class="w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col shadow-soft sticky top-0 h-screen">
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
              ? 'bg-primary-50 dark:bg-primary-900/20 shadow-sm'
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
  <main class="flex-1 p-8 overflow-auto">
    <div class={clsx('mx-auto transition-all duration-300', widthClass)}>
      <slot />
    </div>
  </main>
</div>
