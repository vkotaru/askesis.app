<script lang="ts">
  import { onMount } from 'svelte';
  import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameMonth, isToday } from 'date-fns';
  import { ChevronLeft, ChevronRight } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type CalendarEvent } from '$lib/api/client';

  let currentDate = new Date();
  let calendar: Record<string, CalendarEvent[]> = {};
  let loading = true;

  $: year = currentDate.getFullYear();
  $: month = currentDate.getMonth() + 1;
  $: monthStart = startOfMonth(currentDate);
  $: monthEnd = endOfMonth(currentDate);
  $: days = eachDayOfInterval({ start: monthStart, end: monthEnd });
  $: startDay = monthStart.getDay();
  $: paddedDays = [...Array(startDay).fill(null), ...days];

  async function loadCalendar() {
    loading = true;
    try {
      calendar = await api.getCalendar(year, month);
    } catch (err) {
      console.error('Failed to load calendar:', err);
    } finally {
      loading = false;
    }
  }

  onMount(loadCalendar);

  function prevMonth() {
    currentDate = new Date(year, month - 2, 1);
    loadCalendar();
  }

  function nextMonth() {
    currentDate = new Date(year, month, 1);
    loadCalendar();
  }
</script>

<svelte:head>
  <title>Calendar - Askesis</title>
</svelte:head>

<div>
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-2xl font-bold">Training Calendar</h1>
    <div class="flex items-center gap-4">
      <button on:click={prevMonth} class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
        <ChevronLeft size={20} />
      </button>
      <span class="text-lg font-medium w-40 text-center">
        {format(currentDate, 'MMMM yyyy')}
      </span>
      <button on:click={nextMonth} class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
        <ChevronRight size={20} />
      </button>
    </div>
  </div>

  <div class="card p-6">
    {#if loading}
      <div class="flex items-center justify-center py-8">
        <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-500"></div>
      </div>
    {:else}
      <!-- Day headers -->
      <div class="grid grid-cols-7 gap-2 mb-2">
        {#each ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as day}
          <div class="text-center text-sm font-medium text-gray-500 py-2">{day}</div>
        {/each}
      </div>

      <!-- Calendar grid -->
      <div class="grid grid-cols-7 gap-2">
        {#each paddedDays as day, idx}
          {#if !day}
            <div class="aspect-square"></div>
          {:else}
            {@const dateStr = format(day, 'yyyy-MM-dd')}
            {@const events = calendar[dateStr] || []}
            <div
              class={clsx(
                'aspect-square p-2 rounded-lg border transition-colors',
                isToday(day)
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                  : 'border-gray-100 dark:border-gray-700',
                !isSameMonth(day, currentDate) && 'opacity-50'
              )}
            >
              <div class="text-sm font-medium mb-1">{format(day, 'd')}</div>
              {#if events.length > 0}
                <div class="space-y-1">
                  {#each events.slice(0, 2) as event}
                    <div
                      class={clsx(
                        'text-xs px-1 py-0.5 rounded truncate',
                        event.type === 'cardio'
                          ? 'bg-cardio-100 text-cardio-700 dark:bg-cardio-900/30 dark:text-cardio-400'
                          : 'bg-strength-100 text-strength-700 dark:bg-strength-900/30 dark:text-strength-400'
                      )}
                    >
                      {event.name}
                    </div>
                  {/each}
                  {#if events.length > 2}
                    <div class="text-xs text-gray-500">+{events.length - 2} more</div>
                  {/if}
                </div>
              {/if}
            </div>
          {/if}
        {/each}
      </div>

      <!-- Legend -->
      <div class="flex items-center gap-6 mt-6 pt-4 border-t border-gray-100 dark:border-gray-700">
        <div class="flex items-center gap-2">
          <span class="w-3 h-3 rounded-full bg-cardio-500"></span>
          <span class="text-sm text-gray-600 dark:text-gray-400">Cardio</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="w-3 h-3 rounded-full bg-strength-500"></span>
          <span class="text-sm text-gray-600 dark:text-gray-400">Strength</span>
        </div>
      </div>
    {/if}
  </div>
</div>
