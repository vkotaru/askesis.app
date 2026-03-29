<script lang="ts">
  import { format, parseISO } from 'date-fns';
  import type { TrainingPlan } from '$lib/api/client';

  export let plan: TrainingPlan;

  $: daysLeft = Math.max(0, Math.ceil((new Date(plan.race_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24)));
  $: planStart = new Date(plan.start_date);
  $: totalDays = Math.ceil((new Date(plan.race_date).getTime() - planStart.getTime()) / (1000 * 60 * 60 * 24));
  $: elapsed = totalDays - daysLeft;
</script>

<a href="/training" class="card p-4 flex items-center gap-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
  <div class="text-center">
    <div class="text-2xl font-bold text-primary-500">{daysLeft}</div>
    <div class="text-[10px] text-gray-400">days left</div>
  </div>
  <div class="flex-1">
    <div class="text-sm font-medium">{plan.plan_display_name}</div>
    <div class="text-xs text-gray-400">Race: {format(parseISO(plan.race_date), 'MMM d, yyyy')}</div>
    <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mt-1.5">
      <div class="bg-primary-500 rounded-full h-1.5" style="width: {Math.min((elapsed / totalDays) * 100, 100)}%"></div>
    </div>
  </div>
</a>
