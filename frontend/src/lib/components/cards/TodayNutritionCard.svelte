<script lang="ts">
  import { Flame, Beef, Wheat, Droplets } from 'lucide-svelte';

  export let calories: number = 0;
  export let protein_g: number | undefined = undefined;
  export let carbs_g: number | undefined = undefined;
  export let fat_g: number | undefined = undefined;
  export let title: string = "Today's Nutrition";
</script>

<div class="card p-4">
  <div class="flex items-center gap-2 mb-3">
    <Flame size={18} class="text-nutrition-500" />
    <h3 class="text-sm font-medium text-gray-500">{title}</h3>
  </div>
  <div class="grid grid-cols-4 gap-4">
    <div>
      <p class="text-xs text-gray-400">Calories</p>
      <p class="text-xl font-bold">{calories || '—'}</p>
    </div>
    <div>
      <p class="text-xs text-gray-400 flex items-center gap-1">
        <Beef size={10} class="text-strength-500" />
        Protein
      </p>
      <p class="text-xl font-bold">
        {protein_g ?? '—'}{#if protein_g}<span class="text-xs font-normal text-gray-400">g</span>{/if}
      </p>
    </div>
    <div>
      <p class="text-xs text-gray-400 flex items-center gap-1">
        <Wheat size={10} class="text-cardio-500" />
        Carbs
      </p>
      <p class="text-xl font-bold">
        {carbs_g ?? '—'}{#if carbs_g}<span class="text-xs font-normal text-gray-400">g</span>{/if}
      </p>
    </div>
    <div>
      <p class="text-xs text-gray-400 flex items-center gap-1">
        <Droplets size={10} class="text-nutrition-600" />
        Fat
      </p>
      <p class="text-xl font-bold">
        {fat_g ?? '—'}{#if fat_g}<span class="text-xs font-normal text-gray-400">g</span>{/if}
      </p>
    </div>
  </div>
</div>
