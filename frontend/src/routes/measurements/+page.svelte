<script lang="ts">
  import { onMount } from 'svelte';
  import { format, addDays, subDays, parseISO } from 'date-fns';
  import { Ruler, Check, ChevronLeft, ChevronRight, Upload, History, Calendar } from 'lucide-svelte';
  import ImportModal from '$lib/components/ImportModal.svelte';
  import { clsx } from 'clsx';
  import { api, type BodyMeasurement } from '$lib/api/client';
import { settings } from '$lib/stores/settings';
  import { getMeasurementLabel, formatMeasurement, measurementToMetric, measurementFromMetric } from '$lib/utils/units';

  let recentMeasurements: BodyMeasurement[] = [];

  let selectedDate = format(new Date(), 'yyyy-MM-dd');
  let saving = false;
  let saved = false;
  let loading = true;
  let showImportModal = false;

  // Measurement fields
  let neck: number | undefined;
  let shoulders: number | undefined;
  let chest: number | undefined;
  let bicep_left: number | undefined;
  let bicep_right: number | undefined;
  let forearm_left: number | undefined;
  let forearm_right: number | undefined;
  let waist: number | undefined;
  let abdomen: number | undefined;
  let hips: number | undefined;
  let thigh_left: number | undefined;
  let thigh_right: number | undefined;
  let calf_left: number | undefined;
  let calf_right: number | undefined;
  let notes = '';

  // Helper to convert from metric (API stores cm, convert to user's unit for display)
  function fromMetric(value: number | undefined | null): number | undefined {
    if (value == null) return undefined;
    return measurementFromMetric(value, $settings.measurement_unit);
  }

  async function loadMeasurement() {
    loading = true;
    try {
      const measurement = await api.getMeasurement(selectedDate, undefined);
      neck = fromMetric(measurement.neck);
      shoulders = fromMetric(measurement.shoulders);
      chest = fromMetric(measurement.chest);
      bicep_left = fromMetric(measurement.bicep_left);
      bicep_right = fromMetric(measurement.bicep_right);
      forearm_left = fromMetric(measurement.forearm_left);
      forearm_right = fromMetric(measurement.forearm_right);
      waist = fromMetric(measurement.waist);
      abdomen = fromMetric(measurement.abdomen);
      hips = fromMetric(measurement.hips);
      thigh_left = fromMetric(measurement.thigh_left);
      thigh_right = fromMetric(measurement.thigh_right);
      calf_left = fromMetric(measurement.calf_left);
      calf_right = fromMetric(measurement.calf_right);
      notes = measurement.notes ?? '';
    } catch {
      // No measurement for this date, try to load latest as reference
      try {
        const latest = await api.getLatestMeasurement(undefined);
        if (latest) {
          // Pre-fill with latest values for convenience
          neck = fromMetric(latest.neck);
          shoulders = fromMetric(latest.shoulders);
          chest = fromMetric(latest.chest);
          bicep_left = fromMetric(latest.bicep_left);
          bicep_right = fromMetric(latest.bicep_right);
          forearm_left = fromMetric(latest.forearm_left);
          forearm_right = fromMetric(latest.forearm_right);
          waist = fromMetric(latest.waist);
          abdomen = fromMetric(latest.abdomen);
          hips = fromMetric(latest.hips);
          thigh_left = fromMetric(latest.thigh_left);
          thigh_right = fromMetric(latest.thigh_right);
          calf_left = fromMetric(latest.calf_left);
          calf_right = fromMetric(latest.calf_right);
          notes = '';
        } else {
          resetForm();
        }
      } catch {
        resetForm();
      }
    } finally {
      loading = false;
    }
  }

  function resetForm() {
    neck = undefined;
    shoulders = undefined;
    chest = undefined;
    bicep_left = undefined;
    bicep_right = undefined;
    forearm_left = undefined;
    forearm_right = undefined;
    waist = undefined;
    abdomen = undefined;
    hips = undefined;
    thigh_left = undefined;
    thigh_right = undefined;
    calf_left = undefined;
    calf_right = undefined;
    notes = '';
  }

  async function loadRecentMeasurements() {
    try {
      const endDate = format(new Date(), 'yyyy-MM-dd');
      const startDate = format(subDays(new Date(), 365), 'yyyy-MM-dd');
      const measurements = await api.getMeasurements(startDate, endDate, undefined);
      // Sort by date descending and take last 10
      recentMeasurements = measurements.sort((a, b) => b.date.localeCompare(a.date)).slice(0, 10);
    } catch {
      recentMeasurements = [];
    }
  }

  onMount(() => {
    loadMeasurement();
    loadRecentMeasurements();
  });

  function goToDate(date: string) {
    selectedDate = date;
    loadMeasurement();
  }

  // Helper to convert to metric (user enters in their unit, convert to cm for API)
  function toMetric(value: number | undefined): number | undefined {
    if (value == null) return undefined;
    return measurementToMetric(value, $settings.measurement_unit);
  }

  async function handleSubmit() {
    saving = true;
    saved = false;
    try {
      await api.saveMeasurement({
        date: selectedDate,
        neck: toMetric(neck),
        shoulders: toMetric(shoulders),
        chest: toMetric(chest),
        bicep_left: toMetric(bicep_left),
        bicep_right: toMetric(bicep_right),
        forearm_left: toMetric(forearm_left),
        forearm_right: toMetric(forearm_right),
        waist: toMetric(waist),
        abdomen: toMetric(abdomen),
        hips: toMetric(hips),
        thigh_left: toMetric(thigh_left),
        thigh_right: toMetric(thigh_right),
        calf_left: toMetric(calf_left),
        calf_right: toMetric(calf_right),
        notes: notes || undefined,
      });
      saved = true;
      loadRecentMeasurements(); // Refresh recent entries
      setTimeout(() => (saved = false), 2000);
    } catch (err) {
      console.error('Failed to save:', err);
    } finally {
      saving = false;
    }
  }

  function handleDateChange(e: Event) {
    selectedDate = (e.target as HTMLInputElement).value;
    loadMeasurement();
  }

  function prevDay() {
    selectedDate = format(subDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadMeasurement();
  }

  function nextDay() {
    selectedDate = format(addDays(parseISO(selectedDate), 1), 'yyyy-MM-dd');
    loadMeasurement();
  }
</script>

<svelte:head>
  <title>Body Measurements - Askesis</title>
</svelte:head>

<div>
  <!-- Header -->
  <div class="mb-6">
    <h1 class="text-2xl font-bold flex items-center gap-2">
      <Ruler size={24} class="text-strength-500" />
      Body Measurements
    </h1>
    <p class="text-gray-500 text-sm mt-1">Track your body measurements in {getMeasurementLabel($settings.measurement_unit)}</p>

    <!-- Date Navigation -->
    <div class="flex items-center justify-center gap-2 mt-4">
      <button
        type="button"
        on:click={prevDay}
        class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
      >
        <ChevronLeft size={20} />
      </button>
      <input
        type="date"
        value={selectedDate}
        on:change={handleDateChange}
        class="input max-w-[180px] text-center"
      />
      <button
        type="button"
        on:click={nextDay}
        class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
      >
        <ChevronRight size={20} />
      </button>
    </div>
  </div>

  {#if loading}
    <div class="card p-12 flex items-center justify-center">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
    </div>
  {:else}
    <form on:submit|preventDefault={handleSubmit}>
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Left side inputs -->
        <div class="card p-6 space-y-4">
          <h3 class="font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-cardio-500"></span>
            Left Side
          </h3>

          <div>
            <label for="bicep_left" class="label">Bicep (L)</label>
            <div class="relative">
              <input id="bicep_left" type="number" step="0.01" bind:value={bicep_left} placeholder="--" class="input pr-10" />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">{getMeasurementLabel($settings.measurement_unit)}</span>
            </div>
          </div>

          <div>
            <label for="forearm_left" class="label">Forearm (L)</label>
            <div class="relative">
              <input id="forearm_left" type="number" step="0.01" bind:value={forearm_left} placeholder="--" class="input pr-10" />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">{getMeasurementLabel($settings.measurement_unit)}</span>
            </div>
          </div>

          <div>
            <label for="thigh_left" class="label">Thigh (L)</label>
            <div class="relative">
              <input id="thigh_left" type="number" step="0.01" bind:value={thigh_left} placeholder="--" class="input pr-10" />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">{getMeasurementLabel($settings.measurement_unit)}</span>
            </div>
          </div>

          <div>
            <label for="calf_left" class="label">Calf (L)</label>
            <div class="relative">
              <input id="calf_left" type="number" step="0.01" bind:value={calf_left} placeholder="--" class="input pr-10" />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">{getMeasurementLabel($settings.measurement_unit)}</span>
            </div>
          </div>
        </div>

        <!-- Center - Body Diagram -->
        <div class="card p-6 flex flex-col items-center">
          <h3 class="font-semibold text-gray-700 dark:text-gray-300 mb-4">Center</h3>

          <!-- Body silhouette with measurement points -->
          <div class="relative w-48 mx-auto">
            <!-- Body SVG -->
            <svg viewBox="0 0 100 200" class="w-full h-auto text-primary-500/20 dark:text-primary-400/20">
              <!-- Head -->
              <circle cx="50" cy="15" r="12" fill="currentColor" stroke="currentColor" stroke-width="1"/>
              <!-- Neck -->
              <rect x="45" y="27" width="10" height="8" fill="currentColor"/>
              <!-- Shoulders -->
              <path d="M25 35 Q35 32 45 35 L55 35 Q65 32 75 35 L75 45 L25 45 Z" fill="currentColor"/>
              <!-- Torso -->
              <path d="M30 45 L30 100 Q30 110 40 115 L60 115 Q70 110 70 100 L70 45 Z" fill="currentColor"/>
              <!-- Arms -->
              <path d="M25 35 L15 70 L12 90 L18 92 L25 75 L30 50" fill="currentColor"/>
              <path d="M75 35 L85 70 L88 90 L82 92 L75 75 L70 50" fill="currentColor"/>
              <!-- Legs -->
              <path d="M35 115 L30 160 L28 195 L38 195 L42 160 L45 120" fill="currentColor"/>
              <path d="M65 115 L70 160 L72 195 L62 195 L58 160 L55 120" fill="currentColor"/>
            </svg>

            <!-- Measurement indicators -->
            <div class="absolute top-[14%] left-1/2 -translate-x-1/2 w-full text-center">
              <div class="text-xs text-gray-500">Neck</div>
              <div class="text-sm font-semibold text-primary-600 dark:text-primary-400">{neck ?? '--'}</div>
            </div>
            <div class="absolute top-[22%] left-1/2 -translate-x-1/2 w-full text-center">
              <div class="text-xs text-gray-500">Shoulders</div>
              <div class="text-sm font-semibold text-primary-600 dark:text-primary-400">{shoulders ?? '--'}</div>
            </div>
            <div class="absolute top-[32%] left-1/2 -translate-x-1/2 w-full text-center">
              <div class="text-xs text-gray-500">Chest</div>
              <div class="text-sm font-semibold text-primary-600 dark:text-primary-400">{chest ?? '--'}</div>
            </div>
            <div class="absolute top-[45%] left-1/2 -translate-x-1/2 w-full text-center">
              <div class="text-xs text-gray-500">Waist</div>
              <div class="text-sm font-semibold text-primary-600 dark:text-primary-400">{waist ?? '--'}</div>
            </div>
            <div class="absolute top-[52%] left-1/2 -translate-x-1/2 w-full text-center">
              <div class="text-xs text-gray-500">Abdomen</div>
              <div class="text-sm font-semibold text-primary-600 dark:text-primary-400">{abdomen ?? '--'}</div>
            </div>
            <div class="absolute top-[60%] left-1/2 -translate-x-1/2 w-full text-center">
              <div class="text-xs text-gray-500">Hips</div>
              <div class="text-sm font-semibold text-primary-600 dark:text-primary-400">{hips ?? '--'}</div>
            </div>
          </div>

          <!-- Center inputs -->
          <div class="w-full mt-6 space-y-3">
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label for="neck" class="label text-xs">Neck</label>
                <div class="relative">
                  <input id="neck" type="number" step="0.01" bind:value={neck} placeholder="--" class="input pr-8 text-sm" />
                  <span class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">{getMeasurementLabel($settings.measurement_unit)}</span>
                </div>
              </div>
              <div>
                <label for="shoulders" class="label text-xs">Shoulders</label>
                <div class="relative">
                  <input id="shoulders" type="number" step="0.01" bind:value={shoulders} placeholder="--" class="input pr-8 text-sm" />
                  <span class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">{getMeasurementLabel($settings.measurement_unit)}</span>
                </div>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label for="chest" class="label text-xs">Chest</label>
                <div class="relative">
                  <input id="chest" type="number" step="0.01" bind:value={chest} placeholder="--" class="input pr-8 text-sm" />
                  <span class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">{getMeasurementLabel($settings.measurement_unit)}</span>
                </div>
              </div>
              <div>
                <label for="waist" class="label text-xs">Waist</label>
                <div class="relative">
                  <input id="waist" type="number" step="0.01" bind:value={waist} placeholder="--" class="input pr-8 text-sm" />
                  <span class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">{getMeasurementLabel($settings.measurement_unit)}</span>
                </div>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label for="abdomen" class="label text-xs">Abdomen</label>
                <div class="relative">
                  <input id="abdomen" type="number" step="0.01" bind:value={abdomen} placeholder="--" class="input pr-8 text-sm" />
                  <span class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">{getMeasurementLabel($settings.measurement_unit)}</span>
                </div>
              </div>
              <div>
                <label for="hips" class="label text-xs">Hips</label>
                <div class="relative">
                  <input id="hips" type="number" step="0.01" bind:value={hips} placeholder="--" class="input pr-8 text-sm" />
                  <span class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">{getMeasurementLabel($settings.measurement_unit)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right side inputs -->
        <div class="card p-6 space-y-4">
          <h3 class="font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-strength-500"></span>
            Right Side
          </h3>

          <div>
            <label for="bicep_right" class="label">Bicep (R)</label>
            <div class="relative">
              <input id="bicep_right" type="number" step="0.01" bind:value={bicep_right} placeholder="--" class="input pr-10" />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">{getMeasurementLabel($settings.measurement_unit)}</span>
            </div>
          </div>

          <div>
            <label for="forearm_right" class="label">Forearm (R)</label>
            <div class="relative">
              <input id="forearm_right" type="number" step="0.01" bind:value={forearm_right} placeholder="--" class="input pr-10" />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">{getMeasurementLabel($settings.measurement_unit)}</span>
            </div>
          </div>

          <div>
            <label for="thigh_right" class="label">Thigh (R)</label>
            <div class="relative">
              <input id="thigh_right" type="number" step="0.01" bind:value={thigh_right} placeholder="--" class="input pr-10" />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">{getMeasurementLabel($settings.measurement_unit)}</span>
            </div>
          </div>

          <div>
            <label for="calf_right" class="label">Calf (R)</label>
            <div class="relative">
              <input id="calf_right" type="number" step="0.01" bind:value={calf_right} placeholder="--" class="input pr-10" />
              <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">{getMeasurementLabel($settings.measurement_unit)}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Notes and Save -->
      <div class="card p-6 mt-6">
        <div class="mb-4">
          <label for="notes" class="label">Notes</label>
          <textarea
            id="notes"
            bind:value={notes}
            rows={2}
            placeholder="Any notes about today's measurements..."
            class="input resize-none"
          ></textarea>
        </div>

        <div class="flex justify-end">
            <button
              type="submit"
              disabled={saving}
              class={clsx('btn-primary flex items-center gap-2 px-8', saved && 'bg-primary-600')}
            >
              {#if saving}
                <span class="animate-spin">⏳</span>
                Saving...
              {:else if saved}
                <Check size={18} />
                Saved!
              {:else}
                Save Measurements
              {/if}
            </button>
          </div>
      </div>
    </form>
  {/if}

<!-- Import Button -->
    <div class="mt-6">
      <button
        on:click={() => (showImportModal = true)}
        class="btn-secondary w-full flex items-center justify-center gap-2"
      >
        <Upload size={20} />
        Import Bulk
      </button>
    </div>

<!-- Recent Measurements -->
  {#if recentMeasurements.length > 0}
    <div class="card p-6 mt-6">
      <div class="flex items-center gap-2 mb-4">
        <History size={20} class="text-primary-500" />
        <h2 class="text-lg font-semibold">Recent Measurements</h2>
        <span class="text-sm text-gray-400 ml-auto">Last 10 entries</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-gray-200 dark:border-gray-700">
              <th class="pb-3 font-medium text-gray-500">Date</th>
              <th class="pb-3 font-medium text-gray-500">Chest</th>
              <th class="pb-3 font-medium text-gray-500">Waist</th>
              <th class="pb-3 font-medium text-gray-500">Hips</th>
              <th class="pb-3 font-medium text-gray-500">Bicep (L/R)</th>
              <th class="pb-3 font-medium text-gray-500">Thigh (L/R)</th>
            </tr>
          </thead>
          <tbody>
            {#each recentMeasurements as measurement}
              <tr
                class={clsx(
                  'border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors',
                  measurement.date === selectedDate && 'bg-primary-50 dark:bg-gray-700'
                )}
                on:click={() => goToDate(measurement.date)}
              >
                <td class="py-3">
                  <div class="flex items-center gap-2">
                    <Calendar size={14} class="text-gray-400" />
                    <span class="font-medium">{format(parseISO(measurement.date), 'MMM d')}</span>
                    <span class="text-gray-400 text-xs">{format(parseISO(measurement.date), 'yyyy')}</span>
                  </div>
                </td>
                <td class="py-3">
                  {#if measurement.chest}
                    {formatMeasurement(measurement.chest, $settings.measurement_unit)}
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if measurement.waist}
                    {formatMeasurement(measurement.waist, $settings.measurement_unit)}
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if measurement.hips}
                    {formatMeasurement(measurement.hips, $settings.measurement_unit)}
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if measurement.bicep_left || measurement.bicep_right}
                    {formatMeasurement(measurement.bicep_left, $settings.measurement_unit)} / {formatMeasurement(measurement.bicep_right, $settings.measurement_unit)}
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="py-3">
                  {#if measurement.thigh_left || measurement.thigh_right}
                    {formatMeasurement(measurement.thigh_left, $settings.measurement_unit)} / {formatMeasurement(measurement.thigh_right, $settings.measurement_unit)}
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}
</div>

<ImportModal
  bind:show={showImportModal}
  dataType="measurements"
  title="Import Measurements"
  on:success={() => { loadMeasurement(); loadRecentMeasurements(); }}
/>
