<script lang="ts">
  import { page } from '$app/stores';
  import { Home, ClipboardList, Utensils, Apple, Activity, CalendarDays, Settings, LogOut, Ruler, Camera, Menu, Users, Target, ListChecks, Dumbbell, LineChart, MoreHorizontal } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type User } from '$lib/api/client';
  import { settings } from '$lib/stores/settings';
  import { routeAllowed, isPrimaryNav } from '$lib/appMode';
  import { user as userStore } from '$lib/stores/user';
  import { clearLocalSession, prepareSignOut } from '$lib/stores/data';
  import { deployedVersion, formatVersionLabel, formatVersionTitle } from '$lib/version';
  import SyncStatus from './SyncStatus.svelte';
  import GarminSyncButton from './GarminSyncButton.svelte';
  import LiveSessionBar from './LiveSessionBar.svelte';

  export let user: User;

  // Every section the app has. What an account actually sees is this list
  // filtered by its mode — see lib/appMode.ts, which is where the decision
  // lives so the sidebar, the route guard and the dashboard cannot disagree.
  const navItems = [
    { href: '/', icon: Home, label: 'Dashboard', color: 'text-primary-500' },
    { href: '/shared', icon: Users, label: 'Shared', color: 'text-accent-500' },
    { href: '/daily-log', icon: ClipboardList, label: 'Daily Log', color: 'text-rest-500' },
    { href: '/nutrition', icon: Utensils, label: 'Nutrition', color: 'text-nutrition-500' },
    { href: '/activities', icon: Activity, label: 'Activities', color: 'text-cardio-500' },
    { href: '/trends', icon: LineChart, label: 'Trends', color: 'text-mood-4' },
    { href: '/measurements', icon: Ruler, label: 'Measurements', color: 'text-strength-500' },
    { href: '/photos', icon: Camera, label: 'Photos', color: 'text-accent-500' },
    { href: '/routines', icon: ListChecks, label: 'Routines', color: 'text-strength-500' },
    { href: '/exercises', icon: Dumbbell, label: 'Exercises', color: 'text-strength-500' },
    { href: '/training', icon: Target, label: 'Training', color: 'text-cardio-500' },
    { href: '/calendar', icon: CalendarDays, label: 'Calendar', color: 'text-mood-4' },
    { href: '/nutrition/foods', icon: Apple, label: 'Foods', color: 'text-nutrition-500' },
    { href: '/settings', icon: Settings, label: 'Settings', color: 'text-gray-500' },
  ];

  // Keyed by href where it is rendered, and that is load-bearing: an unkeyed
  // {#each} updates by index, and <svelte:component> then keeps the instance it
  // already had. Filtering this list relabelled the rows while leaving the
  // previous icons in place, so "Daily Log" appeared with the Shared icon.
  $: visibleNav = navItems.filter((item) => routeAllowed($settings.app_mode, item.href));
  // The rail shows the daily drivers; the drawer shows all of visibleNav. See
  // PRIMARY_NAV in lib/appMode.ts for why the rail is not simply everything.
  $: railNav = visibleNav.filter((item) => isPrimaryNav($settings.app_mode, item.href));

  // Sign-out has to erase this account's offline cache: the browser is shared
  // (household app), and anything left in IndexedDB is readable by whoever
  // signs in next. The one thing that cannot simply be deleted is the offline
  // mutation queue — those rows exist nowhere else — so if any are still
  // unsent after a flush attempt, the user is asked instead of guessed at.
  let signOutBusy = false;
  let unsentCount = 0;
  /** Sets in a workout still running. Destroyed by sign-out, and unlike the
   *  queue they cannot be parked — a half-finished session is not a mutation to
   *  replay. So they are named separately and the wording differs. */
  let liveSetCount = 0;

  async function handleSignout(e: MouseEvent) {
    // Always handled in-page. A bare <a href="/auth/logout"> gets intercepted by
    // SvelteKit's client router — it throws "Not found: /auth/logout" before
    // falling back to a real navigation — and the service worker's
    // navigateFallback can serve it from cache without ever reaching the
    // server, leaving the cookie intact.
    e.preventDefault();
    if (signOutBusy) return;

    signOutBusy = true;
    try {
      const { pending, liveSets } = await prepareSignOut();
      if (pending > 0 || liveSets > 0) {
        unsentCount = pending;
        liveSetCount = liveSets;
        return;
      }
      await completeSignout(true);
    } finally {
      signOutBusy = false;
    }
  }

  async function completeSignout(keepUnsent: boolean) {
    try {
      await api.logout();
    } catch {
      // Offline or already logged out — drop the local session regardless.
    }
    await clearLocalSession(keepUnsent);
    userStore.set(null);
  }

  async function signOutKeepingUnsent() {
    unsentCount = 0;
    liveSetCount = 0;
    signOutBusy = true;
    try {
      await completeSignout(true);
    } finally {
      signOutBusy = false;
    }
  }

  async function signOutDiscardingUnsent() {
    unsentCount = 0;
    liveSetCount = 0;
    signOutBusy = true;
    try {
      await completeSignout(false);
    } finally {
      signOutBusy = false;
    }
  }

  let showMobileMenu = false;

  const widthClasses = {
    narrow: 'max-w-3xl',
    medium: 'max-w-5xl',
    wide: 'max-w-7xl',
    full: 'max-w-none',
  } as const;

  $: currentPath = $page.url.pathname;
  $: widthClass = widthClasses[$settings.content_width];
  function closeMenus() {
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
        <SyncStatus />
        <!-- Pull from the watch without going to Settings first: this is the
             control you want precisely when the dashboard is showing
             yesterday's steps. Renders nothing when no watch is connected. -->
        <GarminSyncButton />
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
      <!-- Flex column: header / scrollable nav / footer. An absolutely
           positioned footer used to sit on top of the last nav row, so a tap
           meant for "Settings" could land on "Sign out". -->
      <div
        class="absolute right-0 top-0 h-full w-72 flex flex-col bg-white dark:bg-gray-800 shadow-xl"
        on:click|stopPropagation
        on:keydown|stopPropagation
        role="dialog"
      >
        <div class="flex-shrink-0 p-4 border-b border-gray-200 dark:border-gray-700">
          <div class="flex items-center gap-3 p-2 rounded-lg bg-gray-50 dark:bg-gray-700/50">
            <div class="w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
              <span class="text-primary-600 dark:text-primary-400 font-semibold">
                {user.name?.charAt(0) || 'U'}
              </span>
            </div>
            <div class="flex-1 min-w-0">
              <p class="font-medium truncate text-sm">{user.name}</p>
              <p class="text-xs text-gray-500 truncate">{user.email}</p>
            </div>
          </div>
        </div>
        <nav class="flex-1 min-h-0 overflow-y-auto p-3">
          {#each visibleNav as { href, icon: Icon, label, color } (href)}
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
        <div
          class="flex-shrink-0 p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] border-t border-gray-200 dark:border-gray-700"
        >
          <button
            type="button"
            disabled={signOutBusy}
            on:click={handleSignout}
            class="flex items-center gap-2 text-sm text-gray-500 hover:text-accent-500 transition-colors px-2 py-2"
          >
            <LogOut size={16} />
            Sign out
          </button>
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
      <p class="text-xs text-gray-400 mt-1">
        Health & Fitness Tracker
        <span class="text-gray-300 dark:text-gray-600" aria-hidden="true">·</span>
        <span title={formatVersionTitle($deployedVersion)}
          >{formatVersionLabel($deployedVersion)}</span
        >
      </p>
    </div>

    <nav class="flex-1 px-3 overflow-y-auto">
      {#each visibleNav as { href, icon: Icon, label, color } (href)}
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
        <div class="w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
          <span class="text-primary-600 dark:text-primary-400 font-semibold">
            {user.name?.charAt(0) || 'U'}
          </span>
        </div>
        <div class="flex-1 min-w-0">
          <p class="font-medium truncate text-sm">{user.name}</p>
          <p class="text-xs text-gray-500 truncate">{user.email}</p>
        </div>
      </div>
      <div class="flex items-center justify-between px-2">
        <button
          type="button"
          disabled={signOutBusy}
          on:click={handleSignout}
          class="flex items-center gap-2 text-sm text-gray-500 hover:text-accent-500 transition-colors"
        >
          <LogOut size={16} />
          Sign out
        </button>
        <div class="flex items-center gap-1">
          <GarminSyncButton />
          <SyncStatus />
        </div>
      </div>
    </div>
  </aside>

  <!-- Main content -->
  <!-- pl-14 clears the mobile icon rail below; the rail is fixed, so it takes
       no flow space of its own.

       `min-w-0` is load-bearing. A flex item's `min-width` defaults to `auto`,
       which means it refuses to shrink below its content's minimum width — so
       one page that was too wide (the workout screen's set rows) made <main>
       itself wider than the viewport, and the *document* scrolled sideways.
       On a phone that pans the visual viewport, which drags the fixed header
       and the fixed nav rail off the edge with it: the screenshots of "parts
       moving all around" are this one missing class. Overflow inside a page is
       now that page's problem, not the whole app's. -->
  <main class="flex-1 min-w-0 overflow-x-hidden overflow-y-auto pt-14 pl-12 md:pt-0 md:pl-0">
    <!-- Above the content, inside the scroll container: a running workout has
         to be visible from wherever you have wandered to, without covering the
         page you went there for. -->
    <LiveSessionBar />
    <div class={clsx('mx-auto transition-all duration-300 px-3 py-4 md:p-8 content-area', widthClass)}>
      <slot />
    </div>
  </main>

  <!-- Mobile icon rail.
       Replaces a horizontally scrollable bottom bar. That bar put eleven
       destinations in a strip about five fit on, so reaching the rest meant
       scrolling a nav that gave no sign it scrolled, and it ate the bottom of
       every page on the screen where vertical space is scarcest.
       A rail keeps navigation one tap away (a drawer alone would make it two)
       and mirrors the desktop sidebar, so the app is laid out the same way at
       both sizes. Icons only at 48px; the hamburger above still opens the full
       labelled menu, which is also the accessible path to the same links.

       It shows PRIMARY_NAV, not everything. Fourteen identical grey glyphs in a
       column is not navigation you can read — the rail works only while it is
       short enough to learn by position. The rest live one tap away behind
       "More", which opens the same labelled drawer as the hamburger. -->
  <nav
    class="md:hidden fixed left-0 top-14 bottom-0 z-40 w-12 flex flex-col items-center gap-1 overflow-y-auto scrollbar-hide bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 py-2 pb-safe"
    aria-label="Primary"
  >
    {#each railNav as { href, icon: Icon, label, color } (href)}
      {@const isActive = currentPath === href}
      <a
        {href}
        title={label}
        aria-label={label}
        aria-current={isActive ? 'page' : undefined}
        class={clsx(
          'relative flex items-center justify-center w-9 h-9 rounded-xl flex-shrink-0 transition-colors',
          isActive
            ? 'bg-gray-100 dark:bg-gray-700'
            : 'text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'
        )}
      >
        <!-- The colour alone would not carry the active state for a
             colour-blind user, so it is doubled with a bar on the edge. -->
        {#if isActive}
          <span
            class="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-r bg-primary-500"
            aria-hidden="true"
          ></span>
        {/if}
        <Icon size={20} class={isActive ? color : ''} />
      </a>
    {/each}

    <!-- Everything the rail does not show. Labelled, because an ellipsis icon
         on its own reads as "settings" to about half of people. The separator
         above it says these are a different kind of thing from the five. -->
    {#if visibleNav.length > railNav.length}
      <div class="w-6 border-t border-gray-200 dark:border-gray-700 my-1" aria-hidden="true"></div>
      <button
        type="button"
        on:click|stopPropagation={() => (showMobileMenu = true)}
        aria-label="More sections"
        class="flex flex-col items-center justify-center w-9 h-9 rounded-xl flex-shrink-0 text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
      >
        <MoreHorizontal size={18} />
        <span class="text-[8px] leading-none mt-0.5">More</span>
      </button>
    {/if}
  </nav>

  <!-- Unsent-changes prompt. Signing out wipes this device's copy of the
       account's data, and unsent mutations have no other copy, so the choice
       is the user's to make explicitly. -->
  {#if unsentCount > 0 || liveSetCount > 0}
    <div
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="signout-unsent-title"
    >
      <div class="w-full max-w-sm rounded-2xl bg-white dark:bg-gray-800 p-5 shadow-xl">
        <h2 id="signout-unsent-title" class="text-base font-semibold text-gray-900 dark:text-white">
          {#if liveSetCount > 0 && unsentCount > 0}
            A workout is still running, and {unsentCount} change{unsentCount === 1 ? '' : 's'} are unsaved
          {:else if liveSetCount > 0}
            A workout is still running
          {:else}
            {unsentCount} change{unsentCount === 1 ? '' : 's'} not yet saved to the server
          {/if}
        </h2>
        {#if liveSetCount > 0}
          <!-- Stated separately and first: an unsent mutation can be parked and
               replayed, a live session cannot. Signing out ends it. -->
          <p class="mt-2 text-sm text-gray-600 dark:text-gray-400">
            {liveSetCount} logged set{liveSetCount === 1 ? '' : 's'} exist only in that
            workout, which has not been saved as an activity yet. Signing out will lose
            them — finish the workout first if you want to keep them.
          </p>
        {/if}
        {#if unsentCount > 0}
          <p class="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Signing out clears this device's copy of your data. These changes only exist
            here. Keeping them parks them on this device — they upload the next time you
            sign in, and no other account can see or send them.
          </p>
        {/if}
        <div class="mt-5 flex flex-col gap-2">
          <button
            type="button"
            disabled={signOutBusy}
            on:click={signOutKeepingUnsent}
            class="w-full rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            Sign out, keep them on this device
          </button>
          <button
            type="button"
            disabled={signOutBusy}
            on:click={signOutDiscardingUnsent}
            class="w-full rounded-xl px-4 py-2.5 text-sm font-medium text-accent-600 hover:bg-accent-50 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            Sign out and discard them
          </button>
          <button
            type="button"
            disabled={signOutBusy}
            on:click={() => (unsentCount = 0)}
            class="w-full rounded-xl px-4 py-2.5 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            Stay signed in
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  /* Safe area for devices with home indicator */
  .pb-safe {
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }

  /* Hide scrollbar but keep scroll */
  .scrollbar-hide {
    -ms-overflow-style: none;
    scrollbar-width: none;
  }
  .scrollbar-hide::-webkit-scrollbar {
    display: none;
  }
</style>
