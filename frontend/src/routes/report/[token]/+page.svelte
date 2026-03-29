<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { format, parseISO } from 'date-fns';
  import type { WeightUnit, MeasurementUnit } from '$lib/api/client';
  import '../../../app.css';
  import {
    CurrentWeightCard,
    WeightTrendCard,
    WeekCalendarCard,
    StepsBarCard,
    NutritionChartCard,
    MeasurementsCard,
  } from '$lib/components/cards';

  interface MeasurementSnapshot {
    date: string;
    neck: number | null;
    shoulders: number | null;
    chest: number | null;
    bicep_left: number | null;
    bicep_right: number | null;
    waist: number | null;
    abdomen: number | null;
    hips: number | null;
    thigh_left: number | null;
    thigh_right: number | null;
    calf_left: number | null;
    calf_right: number | null;
  }

  interface Report {
    today: string;
    latest_weight: number | null;
    latest_weight_date: string | null;
    weight_unit: WeightUnit;
    measurement_unit: MeasurementUnit;
    weight_trend: { date: string; weight: number }[];
    week_activities: { date: string; name: string; activity_type: string; duration_mins: number | null; calories: number | null; icon: string | null }[];
    week_start: string;
    week_end: string;
    week_steps: { date: string; steps: number | null }[];
    week_nutrition: { date: string; calories: number; protein_g: number }[];
    latest_measurements: MeasurementSnapshot | null;
    previous_measurements: MeasurementSnapshot | null;
    generated_at: string;
  }

  let report: Report | null = null;
  let loading = true;
  let error = '';

  $: token = $page.params.token;

  $: weightChange = (() => {
    if (!report || report.weight_trend.length < 2) return null;
    const trend = report.weight_trend;
    return trend[trend.length - 1].weight - trend[0].weight;
  })();

  onMount(async () => {
    try {
      const res = await fetch(`/api/report/${token}`);
      if (!res.ok) {
        error = res.status === 404 ? 'This report link is no longer active.' : 'Failed to load report.';
        return;
      }
      report = await res.json();
    } catch {
      error = 'Unable to connect. Please try again later.';
    } finally {
      loading = false;
    }
  });
</script>

<svelte:head>
  <title>Health Report - Askesis</title>
  <meta name="robots" content="noindex, nofollow" />
</svelte:head>

<div class="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
  <div class="max-w-2xl mx-auto px-4 py-8">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-8">
      <img src="/icon-192.png" alt="Askesis" class="w-10 h-10 rounded-xl" />
      <div>
        <h1 class="text-xl font-bold text-green-600">Askesis</h1>
        <p class="text-xs text-gray-400">Health Report</p>
      </div>
    </div>

    {#if loading}
      <div class="flex items-center justify-center py-20">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-green-500"></div>
      </div>
    {:else if error}
      <div class="text-center py-20">
        <p class="text-lg text-gray-500">{error}</p>
      </div>
    {:else if report}
      <p class="text-sm text-gray-400 mb-4">{format(parseISO(report.today), 'EEEE, MMMM d, yyyy')}</p>

      <div class="mb-6">
        <CurrentWeightCard
          weight={report.latest_weight}
          weightDate={report.latest_weight_date}
          {weightChange}
          weightUnit={report.weight_unit}
        />
      </div>

      {#if report.weight_trend.length > 1}
        <div class="mb-6">
          <WeightTrendCard
            weightPoints={report.weight_trend}
            weightUnit={report.weight_unit}
            showMovingAverage={true}
          />
        </div>
      {/if}

      <div class="mb-6">
        <WeekCalendarCard
          weekStart={report.week_start}
          weekEnd={report.week_end}
          activities={report.week_activities}
        />
      </div>

      <div class="mb-6">
        <StepsBarCard
          steps={report.week_steps}
          today={report.today}
        />
      </div>

      <div class="mb-6">
        <NutritionChartCard
          data={report.week_nutrition.map(n => ({ date: n.date, calories: n.calories, protein: n.protein_g, burnedCalories: 0 }))}
          subtitle="Last 7 days"
          today={report.today}
        />
      </div>

      {#if report.latest_measurements}
        <div class="mb-6">
          <MeasurementsCard
            latest={report.latest_measurements}
            previous={report.previous_measurements}
            measurementUnit={report.measurement_unit}
          />
        </div>
      {/if}

      <p class="text-center text-xs text-gray-300 dark:text-gray-600 mt-8">
        Updated {format(parseISO(report.generated_at), 'MMM d, yyyy · h:mm a')}
      </p>
    {/if}
  </div>
</div>
