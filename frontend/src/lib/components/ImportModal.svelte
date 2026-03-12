<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { X, Upload, AlertCircle, CheckCircle, FileSpreadsheet } from 'lucide-svelte';
  import { clsx } from 'clsx';
  import { api, type ImportPreview, type ColumnMapping, type ImportRequest, type ImportResult } from '$lib/api/client';

  export let show = false;
  export let dataType: 'activities' | 'daily-logs' | 'measurements' | 'nutrition' | 'meals' = 'activities';
  export let title = 'Import CSV';

  const dispatch = createEventDispatcher<{ close: void; success: ImportResult }>();

  // Field definitions per data type
  const FIELD_DEFS: Record<string, { value: string; label: string; unit_type?: string }[]> = {
    'activities': [
      { value: 'date', label: 'Date' },
      { value: 'name', label: 'Activity Name' },
      { value: 'activity_type', label: 'Type (cardio/strength)' },
      { value: 'time_of_day', label: 'Time of Day' },
      { value: 'duration_mins', label: 'Duration (minutes)' },
      { value: 'calories', label: 'Calories' },
      { value: 'distance_km', label: 'Distance', unit_type: 'distance' },
      { value: 'url', label: 'URL' },
      { value: 'notes', label: 'Notes' },
      { value: 'tags', label: 'Tags' },
    ],
    'daily-logs': [
      { value: 'date', label: 'Date' },
      { value: 'weight', label: 'Weight', unit_type: 'weight' },
      { value: 'sleep_hours', label: 'Sleep (hours)' },
      { value: 'steps', label: 'Steps' },
      { value: 'water_ml', label: 'Water', unit_type: 'water' },
      { value: 'caffeine_mg', label: 'Caffeine (mg)' },
      { value: 'total_calories', label: 'Total Calories' },
      { value: 'protein_g', label: 'Protein (g)' },
      { value: 'carbs_g', label: 'Carbs (g)' },
      { value: 'fat_g', label: 'Fat (g)' },
      { value: 'notes', label: 'Notes' },
    ],
    'measurements': [
      { value: 'date', label: 'Date' },
      { value: 'neck', label: 'Neck', unit_type: 'measurement' },
      { value: 'shoulders', label: 'Shoulders', unit_type: 'measurement' },
      { value: 'chest', label: 'Chest', unit_type: 'measurement' },
      { value: 'bicep_left', label: 'Bicep (Left)', unit_type: 'measurement' },
      { value: 'bicep_right', label: 'Bicep (Right)', unit_type: 'measurement' },
      { value: 'forearm_left', label: 'Forearm (Left)', unit_type: 'measurement' },
      { value: 'forearm_right', label: 'Forearm (Right)', unit_type: 'measurement' },
      { value: 'waist', label: 'Waist', unit_type: 'measurement' },
      { value: 'abdomen', label: 'Abdomen', unit_type: 'measurement' },
      { value: 'hips', label: 'Hips', unit_type: 'measurement' },
      { value: 'thigh_left', label: 'Thigh (Left)', unit_type: 'measurement' },
      { value: 'thigh_right', label: 'Thigh (Right)', unit_type: 'measurement' },
      { value: 'calf_left', label: 'Calf (Left)', unit_type: 'measurement' },
      { value: 'calf_right', label: 'Calf (Right)', unit_type: 'measurement' },
      { value: 'notes', label: 'Notes' },
    ],
    'nutrition': [
      { value: 'date', label: 'Date' },
      { value: 'meal_type', label: 'Meal Type' },
      { value: 'name', label: 'Meal Name' },
      { value: 'calories', label: 'Calories' },
      { value: 'protein', label: 'Protein (g)' },
      { value: 'carbs', label: 'Carbs (g)' },
      { value: 'fat', label: 'Fat (g)' },
      { value: 'fiber', label: 'Fiber (g)' },
      { value: 'notes', label: 'Notes' },
    ],
    'meals': [
      { value: 'date', label: 'Date' },
      { value: 'meal_1', label: 'Meal 1 / Breakfast (calories)' },
      { value: 'meal_2', label: 'Meal 2 / Lunch (calories)' },
      { value: 'meal_3', label: 'Meal 3 / Dinner (calories)' },
      { value: 'snacks', label: 'Snacks (calories)' },
    ],
  };

  const UNIT_OPTIONS: Record<string, { value: string; label: string }[]> = {
    'distance': [
      { value: 'km', label: 'Kilometers (km)' },
      { value: 'mi', label: 'Miles (mi)' },
    ],
    'weight': [
      { value: 'kg', label: 'Kilograms (kg)' },
      { value: 'lb', label: 'Pounds (lb)' },
    ],
    'measurement': [
      { value: 'cm', label: 'Centimeters (cm)' },
      { value: 'in', label: 'Inches (in)' },
    ],
    'water': [
      { value: 'ml', label: 'Milliliters (ml)' },
      { value: 'L', label: 'Liters (L)' },
      { value: 'oz', label: 'Fluid ounces (oz)' },
      { value: 'cups', label: 'Cups' },
    ],
  };

  let step: 'upload' | 'mapping' | 'importing' | 'result' = 'upload';
  let preview: ImportPreview | null = null;
  let csvData: Record<string, string>[] = [];
  let file: File | null = null;
  let error = '';
  let loading = false;
  let result: ImportResult | null = null;

  // Column mappings: csv_column -> { field, unit }
  let mappings: Record<string, { field: string; unit: string }> = {};

  function close() {
    show = false;
    step = 'upload';
    preview = null;
    csvData = [];
    file = null;
    error = '';
    mappings = {};
    result = null;
    dispatch('close');
  }

  async function handleFileSelect(e: Event) {
    const input = e.target as HTMLInputElement;
    if (!input.files?.length) return;

    file = input.files[0];
    await uploadFile();
  }

  async function handleDrop(e: DragEvent) {
    e.preventDefault();
    if (!e.dataTransfer?.files?.length) return;

    file = e.dataTransfer.files[0];
    if (!file.name.endsWith('.csv')) {
      error = 'Please upload a CSV file';
      return;
    }

    await uploadFile();
  }

  async function uploadFile() {
    if (!file) return;

    loading = true;
    error = '';

    try {
      // Read file for data
      const text = await file.text();
      const lines = text.split('\n');
      const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));

      // Parse all rows
      csvData = [];
      for (let i = 1; i < lines.length; i++) {
        if (!lines[i].trim()) continue;
        const values = parseCSVLine(lines[i]);
        const row: Record<string, string> = {};
        headers.forEach((h, j) => {
          row[h] = values[j] || '';
        });
        csvData.push(row);
      }

      // Get preview from server
      preview = await api.previewCsv(file);

      // Initialize mappings with auto-detected fields
      const fields = FIELD_DEFS[dataType];
      mappings = {};
      for (const col of preview.columns) {
        const colLower = col.toLowerCase().replace(/[_\s-]/g, '');
        const match = fields.find(f => {
          const fieldLower = f.value.toLowerCase().replace(/_/g, '');
          return colLower === fieldLower || colLower.includes(fieldLower) || fieldLower.includes(colLower);
        });
        if (match) {
          const unitType = match.unit_type;
          const defaultUnit = unitType ? UNIT_OPTIONS[unitType][0].value : '';
          mappings[col] = { field: match.value, unit: defaultUnit };
        }
      }

      step = 'mapping';
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to process file';
    } finally {
      loading = false;
    }
  }

  function parseCSVLine(line: string): string[] {
    const result: string[] = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === ',' && !inQuotes) {
        result.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }
    result.push(current.trim());
    return result;
  }

  async function doImport() {
    if (!preview) return;

    step = 'importing';
    loading = true;
    error = '';

    try {
      // Build column mapping and unit mapping
      const columnMapping: ColumnMapping[] = [];
      const unitMapping: Record<string, string> = {};

      for (const [csvCol, mapping] of Object.entries(mappings)) {
        if (mapping.field) {
          columnMapping.push({
            csv_column: csvCol,
            field: mapping.field,
          });
          if (mapping.unit) {
            unitMapping[mapping.field] = mapping.unit;
          }
        }
      }

      const request: ImportRequest = {
        data: csvData,
        column_mapping: columnMapping,
        unit_mapping: unitMapping,
      };

      // Call appropriate import endpoint
      if (dataType === 'activities') {
        result = await api.importActivities(request);
      } else if (dataType === 'daily-logs') {
        result = await api.importDailyLogs(request);
      } else if (dataType === 'measurements') {
        result = await api.importMeasurements(request);
      } else if (dataType === 'meals') {
        result = await api.importMeals(request);
      } else if (dataType === 'nutrition') {
        throw new Error('Nutrition import is not yet supported');
      }

      step = 'result';

      if (result && result.success_count > 0) {
        dispatch('success', result);
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Import failed';
      step = 'mapping';
    } finally {
      loading = false;
    }
  }

  function getFieldLabel(fieldValue: string): string {
    const field = FIELD_DEFS[dataType].find(f => f.value === fieldValue);
    return field?.label || fieldValue;
  }

  function getFieldUnitType(fieldValue: string): string | undefined {
    const field = FIELD_DEFS[dataType].find(f => f.value === fieldValue);
    return field?.unit_type;
  }

  $: fields = FIELD_DEFS[dataType];
  $: mappedFieldCount = Object.values(mappings).filter(m => m.field).length;
</script>

{#if show}
  <div class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" on:click|self={close}>
    <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
        <div class="flex items-center gap-3">
          <FileSpreadsheet size={24} class="text-primary-500" />
          <h2 class="text-lg font-semibold">{title}</h2>
        </div>
        <button on:click={close} class="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
          <X size={20} />
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-6">
        {#if error}
          <div class="mb-4 p-3 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-lg flex items-center gap-2">
            <AlertCircle size={18} />
            {error}
          </div>
        {/if}

        {#if step === 'upload'}
          <!-- File Upload -->
          <div
            class="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl p-12 text-center hover:border-primary-400 transition-colors"
            on:dragover|preventDefault
            on:drop={handleDrop}
          >
            <Upload size={48} class="mx-auto text-gray-400 mb-4" />
            <p class="text-gray-600 dark:text-gray-400 mb-4">
              Drag and drop your CSV file here, or
            </p>
            <label class="btn-primary cursor-pointer inline-block">
              Browse Files
              <input type="file" accept=".csv" on:change={handleFileSelect} class="hidden" />
            </label>
            <p class="text-sm text-gray-500 mt-4">Supported format: CSV (.csv)</p>
          </div>

        {:else if step === 'mapping'}
          <!-- Column Mapping -->
          <div class="space-y-4">
            <div class="flex items-start justify-between gap-4 flex-wrap">
              <div class="flex items-center gap-4 text-sm">
                <span class="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded-lg">
                  {preview?.total_rows} rows found
                </span>
                <span class={clsx(
                  'px-2 py-1 rounded-lg',
                  mappedFieldCount > 0
                    ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                    : 'bg-gray-100 dark:bg-gray-700'
                )}>
                  {mappedFieldCount} of {preview?.columns.length} mapped
                </span>
              </div>
              <button
                on:click={() => { step = 'upload'; preview = null; }}
                class="text-sm text-primary-500 hover:underline"
              >
                Choose different file
              </button>
            </div>

            <!-- Mapping List -->
            <div class="space-y-3">
              {#each preview?.columns || [] as col}
                {@const mapping = mappings[col] || { field: '', unit: '' }}
                {@const unitType = mapping.field ? getFieldUnitType(mapping.field) : undefined}
                {@const isMapped = !!mapping.field}
                <div class={clsx(
                  'p-3 rounded-xl border-2 transition-all',
                  isMapped
                    ? 'border-primary-200 dark:border-primary-800 bg-primary-50/50 dark:bg-primary-900/20'
                    : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50'
                )}>
                  <!-- CSV Column Name -->
                  <div class="flex items-center justify-between mb-2">
                    <span class="font-medium text-sm">{col}</span>
                    {#if preview?.rows[0]?.[col]}
                      <span class="text-xs text-gray-400 truncate max-w-[120px]">
                        e.g. "{preview.rows[0][col]}"
                      </span>
                    {/if}
                  </div>

                  <!-- Field Mapping -->
                  <div class="flex gap-2">
                    <select
                      class={clsx(
                        'flex-1 px-3 py-2 rounded-lg border text-sm bg-white dark:bg-gray-800',
                        isMapped
                          ? 'border-primary-300 dark:border-primary-700'
                          : 'border-gray-300 dark:border-gray-600'
                      )}
                      value={mapping.field}
                      on:change={(e) => {
                        const field = e.currentTarget.value;
                        const newUnitType = getFieldUnitType(field);
                        mappings[col] = {
                          field,
                          unit: newUnitType ? UNIT_OPTIONS[newUnitType][0].value : ''
                        };
                      }}
                    >
                      <option value="">Skip this column</option>
                      <optgroup label="Available Fields">
                        {#each fields as field}
                          <option value={field.value}>{field.label}</option>
                        {/each}
                      </optgroup>
                    </select>

                    {#if unitType}
                      <select
                        class="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-sm bg-white dark:bg-gray-800 min-w-[100px]"
                        value={mapping.unit}
                        on:change={(e) => {
                          mappings[col] = { ...mapping, unit: e.currentTarget.value };
                        }}
                      >
                        {#each UNIT_OPTIONS[unitType] as unit}
                          <option value={unit.value}>{unit.label}</option>
                        {/each}
                      </select>
                    {/if}
                  </div>
                </div>
              {/each}
            </div>

            <!-- Preview rows (hidden on mobile) -->
            {#if preview && preview.rows.length > 0}
              <div class="hidden md:block">
                <h3 class="text-sm font-medium text-gray-500 mb-2">Preview (first 5 rows)</h3>
                <div class="overflow-x-auto border dark:border-gray-700 rounded-lg">
                  <table class="w-full text-sm">
                    <thead>
                      <tr class="bg-gray-50 dark:bg-gray-700">
                        {#each preview.columns as col}
                          <th class="py-2 px-3 text-left font-medium truncate max-w-[120px]">{col}</th>
                        {/each}
                      </tr>
                    </thead>
                    <tbody>
                      {#each preview.rows as row}
                        <tr class="border-t dark:border-gray-700">
                          {#each preview.columns as col}
                            <td class="py-2 px-3 truncate max-w-[120px]">{row[col] || ''}</td>
                          {/each}
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              </div>
            {/if}
          </div>

        {:else if step === 'importing'}
          <!-- Importing -->
          <div class="text-center py-12">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500 mx-auto mb-4"></div>
            <p class="text-gray-600 dark:text-gray-400">Importing data...</p>
          </div>

        {:else if step === 'result'}
          <!-- Result -->
          <div class="text-center py-8">
            {#if result && result.success_count > 0}
              <CheckCircle size={48} class="mx-auto text-green-500 mb-4" />
              <h3 class="text-xl font-semibold mb-2">Import Complete</h3>
              <p class="text-gray-600 dark:text-gray-400 mb-4">
                Successfully imported {result.success_count} records
              </p>
            {:else if result}
              <AlertCircle size={48} class="mx-auto text-yellow-500 mb-4" />
              <h3 class="text-xl font-semibold mb-2">No Records Imported</h3>
              <p class="text-gray-600 dark:text-gray-400 mb-4">
                0 records were imported. Check if the date column is mapped correctly.
              </p>
            {:else}
              <AlertCircle size={48} class="mx-auto text-yellow-500 mb-4" />
              <h3 class="text-xl font-semibold mb-2">Import Complete</h3>
            {/if}

            {#if result && result.error_count > 0}
              <div class="mt-4 text-left">
                <p class="text-sm text-red-500 mb-2">{result.error_count} errors:</p>
                <ul class="text-sm text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-700 rounded-lg p-3 max-h-40 overflow-y-auto">
                  {#each result.errors as err}
                    <li class="mb-1">{err}</li>
                  {/each}
                </ul>
              </div>
            {/if}
          </div>
        {/if}
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-end gap-3 p-4 border-t border-gray-200 dark:border-gray-700">
        {#if step === 'mapping'}
          <button on:click={close} class="btn-secondary">Cancel</button>
          <button
            on:click={doImport}
            disabled={mappedFieldCount === 0 || loading}
            class="btn-primary"
          >
            {loading ? 'Importing...' : `Import ${preview?.total_rows || 0} Rows`}
          </button>
        {:else if step === 'result'}
          <button on:click={close} class="btn-primary">Done</button>
        {/if}
      </div>
    </div>
  </div>
{/if}
