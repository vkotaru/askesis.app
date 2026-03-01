<script lang="ts">
</script>

<div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-rest-50 to-cardio-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
  <!-- Background decoration -->
  <div class="absolute inset-0 overflow-hidden pointer-events-none">
    <div class="absolute -top-40 -right-40 w-80 h-80 bg-primary-200/30 dark:bg-primary-900/20 rounded-full blur-3xl" />
    <div class="absolute -bottom-40 -left-40 w-80 h-80 bg-cardio-200/30 dark:bg-cardio-900/20 rounded-full blur-3xl" />
  </div>

  <div class="relative bg-white/80 dark:bg-gray-800/80 backdrop-blur-xl p-8 rounded-2xl shadow-soft max-w-md w-full mx-4 border border-white/20">
    <!-- Logo/Brand -->
    <div class="text-center mb-8">
      <h1 class="text-4xl font-bold bg-gradient-to-r from-primary-600 via-primary-500 to-rest-500 bg-clip-text text-transparent mb-2">
        Askesis
      </h1>
      <p class="text-gray-500 dark:text-gray-400">
        Track your health journey together
      </p>
    </div>

    <!-- Stats preview -->
    <div class="grid grid-cols-4 gap-2 mb-8">
      {#each [
        { emoji: '🏃', label: 'Activity' },
        { emoji: '💧', label: 'Hydration' },
        { emoji: '😴', label: 'Sleep' },
        { emoji: '🥗', label: 'Nutrition' },
      ] as { emoji, label }}
        <div class="flex flex-col items-center p-3 rounded-xl bg-gray-50 dark:bg-gray-700/50">
          <span class="text-2xl mb-1">{emoji}</span>
          <span class="text-xs text-gray-500">{label}</span>
        </div>
      {/each}
    </div>

    <!-- Login button -->
    <a
      href="/auth/login"
      class="flex items-center justify-center gap-3 w-full bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-xl px-6 py-4 font-medium hover:bg-gray-50 dark:hover:bg-gray-600 transition-all hover:shadow-md group"
    >
      <svg class="w-5 h-5" viewBox="0 0 24 24">
        <path
          fill="#4285F4"
          d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
        />
        <path
          fill="#34A853"
          d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        />
        <path
          fill="#FBBC05"
          d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
        />
        <path
          fill="#EA4335"
          d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        />
      </svg>
      <span>Continue with Google</span>
      <span class="ml-auto text-gray-400 group-hover:translate-x-1 transition-transform">
        →
      </span>
    </a>

    <p class="text-center text-xs text-gray-400 mt-6">
      Family health tracking made simple
    </p>
  </div>
</div>
