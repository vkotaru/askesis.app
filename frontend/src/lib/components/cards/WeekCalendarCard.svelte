<script lang="ts">
  import { format, parseISO, addDays } from 'date-fns';

  export let weekStart: string;
  export let weekEnd: string;
  export let activities: { date: string; name: string; activity_type: string; duration_mins: number | null; icon: string | null }[] = [];

  const ICON_EMOJI: Record<string, string> = {
    activity: '🏃', dumbbell: '🏋️', bike: '🚴', footprints: '👣',
    heart: '❤️', flame: '🔥', timer: '⏱️', mountain: '⛰️',
    waves: '🏊', trophy: '🏆',
  };

  function getActivityEmoji(icon: string | null, activityType: string): string {
    if (icon && ICON_EMOJI[icon]) return ICON_EMOJI[icon];
    return activityType === 'strength' ? '🏋️' : '🏃';
  }

  $: weekDays = (() => {
    const start = parseISO(weekStart);
    const todayStr = format(new Date(), 'yyyy-MM-dd');
    return Array.from({ length: 7 }, (_, i) => {
      const d = addDays(start, i);
      const dateStr = format(d, 'yyyy-MM-dd');
      return {
        date: dateStr,
        dayName: format(d, 'EEE'),
        dayNum: format(d, 'd'),
        isToday: dateStr === todayStr,
        activities: activities.filter(a => a.date === dateStr),
      };
    });
  })();

  $: totalWorkouts = activities.length;
  $: totalMins = activities.reduce((sum, a) => sum + (a.duration_mins || 0), 0);
</script>

<div class="card p-6">
  <h2 class="text-sm font-semibold text-gray-500 mb-4">
    This Week
    <span class="font-normal text-gray-400 ml-1">
      {format(parseISO(weekStart), 'MMM d')} – {format(parseISO(weekEnd), 'MMM d')}
    </span>
  </h2>

  <div class="grid grid-cols-7 gap-2">
    {#each weekDays as day}
      <div class="text-center">
        <p class="text-xs text-gray-400 mb-1">{day.dayName}</p>
        <div
          class="rounded-xl p-2 min-h-[72px] flex flex-col items-center justify-start gap-1 transition-colors
            {day.isToday ? 'bg-green-50 dark:bg-green-900/20 ring-2 ring-green-500/30' : 'bg-gray-50 dark:bg-gray-700/50'}"
        >
          <span class="text-sm font-semibold {day.isToday ? 'text-green-600' : 'text-gray-600 dark:text-gray-300'}">
            {day.dayNum}
          </span>
          {#each day.activities as activity}
            <span class="text-base leading-none"
              title="{activity.name}{activity.duration_mins ? ` — ${activity.duration_mins}min` : ''}">
              {getActivityEmoji(activity.icon, activity.activity_type)}
            </span>
          {/each}
          {#if day.activities.length === 0}
            <span class="text-gray-300 dark:text-gray-600 text-xs">—</span>
          {/if}
        </div>
      </div>
    {/each}
  </div>

  {#if totalWorkouts > 0}
    <div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
      <p class="text-xs text-gray-400">
        {totalWorkouts} workout{totalWorkouts === 1 ? '' : 's'} this week
        {#if totalMins > 0} · {totalMins} min total{/if}
      </p>
    </div>
  {/if}
</div>
