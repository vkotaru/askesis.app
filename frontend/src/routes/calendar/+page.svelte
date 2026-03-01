<script lang="ts">
  import { onMount } from 'svelte';
  import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameMonth, isToday, startOfWeek, endOfWeek } from 'date-fns';
  import { ChevronLeft, ChevronRight } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type CalendarEvent } from '$lib/api/client';

  // Activity name to emoji mapping
  const ACTIVITY_EMOJIS: Record<string, string> = {
    // Cardio
    'run': '🏃',
    'running': '🏃',
    'morning run': '🏃',
    'evening run': '🏃',
    'jog': '🏃',
    'cycling': '🚴',
    'bike': '🚴',
    'biking': '🚴',
    'swimming': '🏊',
    'swim': '🏊',
    'hike': '🥾',
    'hiking': '🥾',
    'trail hike': '🥾',
    'walk': '🚶',
    'walking': '🚶',
    'evening walk': '🚶',
    'hiit': '🔥',
    'hiit session': '🔥',
    'cardio': '❤️',
    // Strength
    'strength': '💪',
    'upper body': '💪',
    'lower body': '🦵',
    'leg day': '🦵',
    'legs': '🦵',
    'core': '🧘',
    'abs': '🧘',
    'back': '💪',
    'chest': '💪',
    'arms': '💪',
    'shoulders': '💪',
    'full body': '🏋️',
    'weights': '🏋️',
    'yoga': '🧘',
    'stretching': '🤸',
  };

  function getActivityEmoji(name: string, type: string): string {
    const lowerName = name.toLowerCase();

    // Check for exact or partial match
    for (const [key, emoji] of Object.entries(ACTIVITY_EMOJIS)) {
      if (lowerName.includes(key)) {
        return emoji;
      }
    }

    // Fallback based on type
    return type === 'cardio' ? '🏃' : '💪';
  }

  let currentDate = new Date();
  let calendar: Record<string, CalendarEvent[]> = {};
  let loading = true;

  $: year = currentDate.getFullYear();
  $: month = currentDate.getMonth() + 1;
  $: monthStart = startOfMonth(currentDate);
  $: monthEnd = endOfMonth(currentDate);

  // Get calendar grid starting from Monday
  $: calendarStart = startOfWeek(monthStart, { weekStartsOn: 1 });
  $: calendarEnd = endOfWeek(monthEnd, { weekStartsOn: 1 });
  $: calendarDays = eachDayOfInterval({ start: calendarStart, end: calendarEnd });

  async function loadCalendar(y: number, m: number) {
    loading = true;
    try {
      calendar = await api.getCalendar(y, m);
    } catch (err) {
      console.error('Failed to load calendar:', err);
    } finally {
      loading = false;
    }
  }

  onMount(() => loadCalendar(year, month));

  function prevMonth() {
    const newDate = new Date(year, month - 2, 1);
    currentDate = newDate;
    loadCalendar(newDate.getFullYear(), newDate.getMonth() + 1);
  }

  function nextMonth() {
    const newDate = new Date(year, month, 1);
    currentDate = newDate;
    loadCalendar(newDate.getFullYear(), newDate.getMonth() + 1);
  }
</script>

<svelte:head>
  <title>Calendar - Askesis</title>
</svelte:head>

<div>
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-2xl font-bold">Training Calendar</h1>
    <div class="flex items-center gap-2">
      <button
        on:click={prevMonth}
        class="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg flex items-center gap-1 text-sm font-medium"
      >
        <ChevronLeft size={16} />
        Prev
      </button>
      <button
        on:click={nextMonth}
        class="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg flex items-center gap-1 text-sm font-medium"
      >
        Next
        <ChevronRight size={16} />
      </button>
    </div>
  </div>

  <!-- Month title -->
  <h2 class="text-xl font-semibold text-center mb-4">{format(currentDate, 'MMMM yyyy')}</h2>

  <div class="card overflow-hidden">
    {#if loading}
      <div class="flex items-center justify-center py-16">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
      </div>
    {:else}
      <!-- Day headers - Monday first -->
      <div class="grid grid-cols-7 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        {#each ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as day}
          <div class="text-center text-sm font-semibold text-gray-600 dark:text-gray-400 py-3">{day}</div>
        {/each}
      </div>

      <!-- Calendar grid -->
      <div class="grid grid-cols-7">
        {#each calendarDays as day, idx}
          {@const dateStr = format(day, 'yyyy-MM-dd')}
          {@const events = calendar[dateStr] || []}
          {@const isCurrentMonth = isSameMonth(day, currentDate)}
          {@const isTodayDate = isToday(day)}
          <div
            class={clsx(
              'min-h-[100px] p-2 border-b border-r border-gray-100 dark:border-gray-700 transition-colors',
              !isCurrentMonth && 'bg-gray-50/50 dark:bg-gray-800/50',
              isTodayDate && 'bg-primary-50 dark:bg-primary-900/20',
              idx % 7 === 6 && 'border-r-0'
            )}
          >
            <!-- Day number -->
            <div
              class={clsx(
                'text-right text-sm font-medium mb-2',
                !isCurrentMonth && 'text-gray-400 dark:text-gray-600',
                isTodayDate && 'text-primary-600 dark:text-primary-400'
              )}
            >
              {format(day, 'd')}
            </div>

            <!-- Activity emojis -->
            {#if events.length > 0}
              <div class="flex flex-wrap gap-1 justify-center">
                {#each events as event}
                  <span
                    class="text-xl cursor-default"
                    title="{event.name}{event.duration_mins ? ` (${event.duration_mins} min)` : ''}"
                  >
                    {getActivityEmoji(event.name, event.type)}
                  </span>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Legend -->
  <div class="mt-6 card p-4">
    <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Legend</h3>
    <div class="flex flex-wrap gap-4">
      <div class="flex items-center gap-2">
        <span class="text-xl">🏃</span>
        <span class="text-sm text-gray-600 dark:text-gray-400">Running</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xl">🚴</span>
        <span class="text-sm text-gray-600 dark:text-gray-400">Cycling</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xl">🏊</span>
        <span class="text-sm text-gray-600 dark:text-gray-400">Swimming</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xl">🥾</span>
        <span class="text-sm text-gray-600 dark:text-gray-400">Hiking</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xl">🚶</span>
        <span class="text-sm text-gray-600 dark:text-gray-400">Walking</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xl">🔥</span>
        <span class="text-sm text-gray-600 dark:text-gray-400">HIIT</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xl">💪</span>
        <span class="text-sm text-gray-600 dark:text-gray-400">Upper Body</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xl">🦵</span>
        <span class="text-sm text-gray-600 dark:text-gray-400">Lower Body</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xl">🧘</span>
        <span class="text-sm text-gray-600 dark:text-gray-400">Core/Yoga</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xl">🏋️</span>
        <span class="text-sm text-gray-600 dark:text-gray-400">Weights</span>
      </div>
    </div>
  </div>
</div>
