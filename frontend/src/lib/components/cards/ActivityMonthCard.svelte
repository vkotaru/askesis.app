<script lang="ts">
  /**
   * The last five weeks of training, as a calendar of what you actually did.
   *
   * Replaces the eight-week bar chart that used to sit here. That chart answered
   * "how many kilometres did I ride each week", which is the same question the
   * Weekly Targets tile above already answers, and answers better — against a
   * target rather than in the abstract. What nothing on this page showed was the
   * *shape* of a month: which days you trained, where the rest days fell, how
   * long a gap ran. That is what a calendar is for and what a bar chart of
   * weekly totals destroys by summing.
   *
   * Rolling, not calendar-month: it ends on today and runs back five weeks, so
   * the most recent week is always complete rather than a stub at the start of a
   * month. The trade is that it spans two months, which is why the left rail
   * labels each row with the month its week begins in.
   *
   * Read-only on purpose. Tapping a day opens the same day-detail dialog the
   * other dashboard charts use; editing happens on the Activities page.
   */
  import { createEventDispatcher } from 'svelte';
  import {
    format,
    parseISO,
    startOfWeek,
    addDays,
    subWeeks,
    isSameMonth,
    isFuture,
  } from 'date-fns';
  import { CalendarDays } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { ICON_MAP, getActivityEmoji } from '$lib/utils/activityIcons';
  import type { Activity } from '$lib/api/client';

  export let activities: Activity[] = [];
  /** How many weeks back to show, the current (partial) week included. */
  export let weeks: number = 5;
  export let today: string = format(new Date(), 'yyyy-MM-dd');

  const dispatch = createEventDispatcher<{ dayClick: string }>();

  const DOW = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

  $: end = parseISO(today);
  // Back to the Monday of the first week shown, so every row is a whole week and
  // the columns line up under the day-of-week header.
  $: firstMonday = startOfWeek(subWeeks(end, weeks - 1), { weekStartsOn: 1 });

  $: byDate = activities.reduce<Record<string, Activity[]>>((acc, a) => {
    (acc[a.date] ??= []).push(a);
    return acc;
  }, {});

  $: rows = Array.from({ length: weeks }, (_, w) => {
    const rowStart = addDays(firstMonday, w * 7);
    return {
      // The month a week belongs to is the month it STARTS in — a week split
      // across two months has to be labelled once, not ambiguously.
      label: format(rowStart, 'MMM'),
      showLabel:
        w === 0 || !isSameMonth(rowStart, addDays(firstMonday, (w - 1) * 7)),
      days: Array.from({ length: 7 }, (_, d) => {
        const day = addDays(rowStart, d);
        const iso = format(day, 'yyyy-MM-dd');
        return {
          iso,
          dayOfMonth: format(day, 'd'),
          items: byDate[iso] ?? [],
          isToday: iso === today,
          // A day that has not happened yet is dimmed rather than hidden: the
          // grid keeps its shape, and an empty future Friday does not read as a
          // missed session.
          future: isFuture(day) && iso !== today,
        };
      }),
    };
  });

  // Both halves count the same days. `activeDays` used to include future ones
  // while `totalDays` excluded them, so an activity logged for tomorrow —
  // a planned session, a mis-typed date — rendered "22 of 21 days trained".
  $: activeDays = rows.reduce(
    (n, row) => n + row.days.filter((d) => !d.future && d.items.length > 0).length,
    0
  );
  $: totalDays = rows.reduce((n, row) => n + row.days.filter((d) => !d.future).length, 0);

  function iconFor(activity: Activity) {
    return activity.icon ? ICON_MAP[activity.icon] ?? null : null;
  }

  function label(activity: Activity): string {
    const mins = activity.duration_mins ? ` (${activity.duration_mins} min)` : '';
    return `${activity.name}${mins}`;
  }
</script>

<div class="card p-4 md:p-6" data-testid="month-card">
  <div class="flex items-center gap-2 mb-1">
    <CalendarDays size={20} class="text-mood-4" />
    <h2 class="text-lg font-semibold">Last {weeks} weeks</h2>
    <span class="text-xs text-gray-400 ml-auto">
      {activeDays} of {totalDays} days trained
    </span>
  </div>
  <p class="text-[10px] text-gray-400 mb-3">Click a day for details</p>

  <!-- A month label rail, then the seven day columns. -->
  <div class="grid grid-cols-[1.75rem_repeat(7,1fr)] gap-1">
    <span></span>
    {#each DOW as d, i}
      <span class="text-[10px] text-gray-400 text-center pb-0.5">{d}</span>
    {/each}

    {#each rows as row}
      <span class="text-[10px] text-gray-400 flex items-center justify-end pr-1 tabular-nums">
        {row.showLabel ? row.label : ''}
      </span>
      {#each row.days as day (day.iso)}
        <button
          type="button"
          disabled={day.future}
          aria-label="{day.iso}: {day.items.length
            ? day.items.map(label).join(', ')
            : 'nothing logged'}"
          title={day.items.map(label).join('\n')}
          on:click={() => dispatch('dayClick', day.iso)}
          class={clsx(
            // A fixed height, not aspect-square: the card spans the full grid
            // width, so square cells would be ~140px tall and the icons would
            // float in acres of white. A month view's cells are wide and short.
            'h-12 rounded-md flex flex-col items-center justify-center gap-0.5 p-0.5 transition-colors',
            day.future
              ? 'opacity-30 cursor-default'
              : 'cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700',
            day.isToday
              ? 'ring-1 ring-primary-400'
              : day.items.length > 0
                ? 'bg-gray-50 dark:bg-gray-800/60'
                : ''
          )}
        >
          <span
            class={clsx(
              'text-[10px] leading-none tabular-nums',
              day.isToday ? 'text-primary-500 font-semibold' : 'text-gray-400'
            )}
          >
            {day.dayOfMonth}
          </span>

          <!-- Up to two marks, then a count. A day with five logged activities
               would otherwise render five illegible glyphs in a cell this size. -->
          <span class="flex items-center justify-center gap-0.5 leading-none">
            <!-- Keyed, like the nav: an unkeyed {#each} updates by index and
                 <svelte:component> keeps the instance it already had, so a
                 revalidation that reorders two activities on one day would
                 leave the first one's icon on the second. The same pattern put
                 the Shared icon on Daily Log. -->
            {#each day.items.slice(0, 2) as activity (activity.id ?? activity.name)}
              {@const Icon = iconFor(activity)}
              {#if Icon}
                <span
                  class={activity.activity_type === 'cardio'
                    ? 'text-cardio-500'
                    : 'text-strength-500'}
                >
                  <svelte:component this={Icon} size={13} />
                </span>
              {:else}
                <span class="text-[11px]">
                  {getActivityEmoji(activity.name, activity.activity_type)}
                </span>
              {/if}
            {/each}
            {#if day.items.length > 2}
              <span class="text-[8px] text-gray-400">+{day.items.length - 2}</span>
            {/if}
          </span>
        </button>
      {/each}
    {/each}
  </div>
</div>
