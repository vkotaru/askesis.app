<script lang="ts">
  import { user as userStore, cacheUser } from '$lib/stores/user';
  import { settings } from '$lib/stores/settings';
  import { hydrateFromServer } from '$lib/stores/data';
  import { api, ApiError } from '$lib/api/client';
  import { sync } from '$lib/sync';
  import { APP_VERSION } from '$lib/version';

  // Mirrors MIN_PASSWORD_LENGTH in backend/app/security.py. Client-side only —
  // the server validates independently.
  const MIN_PASSWORD_LENGTH = 8;

  let usernameInput = '';
  let passwordInput = '';
  let passwordLoginBusy = false;
  let errorMsg = '';

  // Set when /auth/login answers 409 password_not_set: the identifier of an
  // account that exists but predates password auth, waiting to be claimed.
  let claimIdentifier = '';
  let newPasswordInput = '';
  let confirmPasswordInput = '';

  /**
   * The bootstrap the root layout runs on mount, so the user lands in the app
   * without a manual reload. Setting userStore is what swaps <Login> for the
   * app shell, which is also what arms the one-time stranded-local-data check
   * in +layout.svelte.
   */
  async function bootstrapSession() {
    const me = await api.getMe();
    userStore.set(me);
    await cacheUser(me);
    await settings.load();
    hydrateFromServer(me.id).catch(() => {});
    sync().catch(() => {});
  }

  function backToLogin() {
    claimIdentifier = '';
    newPasswordInput = '';
    confirmPasswordInput = '';
    errorMsg = '';
  }

  async function handlePasswordLogin() {
    errorMsg = '';
    if (passwordLoginBusy) return;

    const identifier = usernameInput.trim();
    if (!identifier || !passwordInput) {
      errorMsg = 'Username and password are required';
      return;
    }

    passwordLoginBusy = true;
    try {
      await api.login(identifier, passwordInput);
      passwordInput = '';
      await bootstrapSession();
    } catch (err) {
      if (err instanceof ApiError && err.code === 'password_not_set') {
        // Not a failure the user can fix by retyping — switch to the claim form.
        passwordInput = '';
        claimIdentifier = identifier;
        return;
      }
      errorMsg =
        err instanceof Error && err.message !== 'Unauthorized'
          ? err.message
          : 'Incorrect username or password';
    } finally {
      passwordLoginBusy = false;
    }
  }

  async function handleSetInitialPassword() {
    errorMsg = '';
    if (passwordLoginBusy) return;

    if (newPasswordInput.length < MIN_PASSWORD_LENGTH) {
      errorMsg = `Password must be at least ${MIN_PASSWORD_LENGTH} characters`;
      return;
    }
    if (newPasswordInput !== confirmPasswordInput) {
      errorMsg = 'Passwords do not match';
      return;
    }

    passwordLoginBusy = true;
    try {
      await api.setInitialPassword(claimIdentifier, newPasswordInput);
      newPasswordInput = '';
      confirmPasswordInput = '';
      claimIdentifier = '';
      // The server signed us in as part of the same response, so this is the
      // identical post-login path.
      await bootstrapSession();
    } catch (err) {
      errorMsg =
        err instanceof Error && err.message !== 'Unauthorized'
          ? err.message
          : 'Could not set a password for that account';
    } finally {
      passwordLoginBusy = false;
    }
  }
</script>

<div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-rest-50 to-cardio-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 font-sans">
  <!-- Background decoration -->
  <div class="absolute inset-0 overflow-hidden pointer-events-none">
    <div class="absolute -top-40 -right-40 w-80 h-80 bg-primary-200/30 dark:bg-primary-900/20 rounded-full blur-3xl" />
    <div class="absolute -bottom-40 -left-40 w-80 h-80 bg-cardio-200/30 dark:bg-cardio-900/20 rounded-full blur-3xl" />
  </div>

  <div class="relative bg-white/80 dark:bg-gray-800/80 backdrop-blur-xl p-8 rounded-2xl shadow-soft max-w-md w-full mx-4 border border-white/20">
    <!-- Logo/Brand -->
    <div class="text-center mb-6">
      <h1 class="text-4xl font-bold bg-gradient-to-r from-primary-600 via-primary-500 to-rest-500 bg-clip-text text-transparent mb-2">
        Askesis
      </h1>
      <p class="text-gray-500 dark:text-gray-400 text-sm">
        Track your health journey
      </p>
    </div>

    <div class="space-y-4">
      {#if claimIdentifier}
        <p class="text-xs text-gray-500 dark:text-gray-400 text-center mb-4">
          This account has no password yet — it was created before password sign-in
          existed. Choose one now to finish signing in.
        </p>

        <p class="text-sm text-center font-medium text-gray-700 dark:text-gray-200 break-all">
          {claimIdentifier}
        </p>

        {#if errorMsg}
          <p class="text-red-500 text-xs text-center font-medium">{errorMsg}</p>
        {/if}

        <form on:submit|preventDefault={handleSetInitialPassword} class="space-y-3">
          <div>
            <label for="claim-password" class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1 uppercase tracking-wider">
              New Password
            </label>
            <input
              id="claim-password"
              type="password"
              autocomplete="new-password"
              bind:value={newPasswordInput}
              placeholder="••••••••"
              class="w-full input border-gray-200 dark:border-gray-700 px-4 py-3 rounded-xl dark:bg-gray-900 focus:ring-primary-500 focus:border-primary-500"
            />
            <p class="text-[11px] text-gray-400 dark:text-gray-500 mt-1">
              At least {MIN_PASSWORD_LENGTH} characters.
            </p>
          </div>

          <div>
            <label for="claim-password-confirm" class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1 uppercase tracking-wider">
              Confirm Password
            </label>
            <input
              id="claim-password-confirm"
              type="password"
              autocomplete="new-password"
              bind:value={confirmPasswordInput}
              placeholder="••••••••"
              class="w-full input border-gray-200 dark:border-gray-700 px-4 py-3 rounded-xl dark:bg-gray-900 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          <button
            type="submit"
            disabled={passwordLoginBusy}
            class="w-full py-3 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 active:scale-[0.98] rounded-xl transition-all shadow-md shadow-primary-500/20 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {passwordLoginBusy ? 'Setting password…' : 'Set Password & Sign In'}
          </button>

          <button
            type="button"
            on:click={backToLogin}
            class="w-full py-2 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
          >
            Back to sign in
          </button>
        </form>
      {:else}
        <p class="text-xs text-gray-500 dark:text-gray-400 text-center mb-4">
          Sign in to your account.
        </p>

        {#if errorMsg}
          <p class="text-red-500 text-xs text-center font-medium">{errorMsg}</p>
        {/if}

        <form on:submit|preventDefault={handlePasswordLogin} class="space-y-3">
          <div>
            <label for="login-username" class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1 uppercase tracking-wider">
              Username or Email
            </label>
            <input
              id="login-username"
              type="text"
              autocomplete="username"
              bind:value={usernameInput}
              placeholder="e.g. prasanth"
              class="w-full input border-gray-200 dark:border-gray-700 px-4 py-3 rounded-xl dark:bg-gray-900 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          <div>
            <label for="login-password" class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1 uppercase tracking-wider">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autocomplete="current-password"
              bind:value={passwordInput}
              placeholder="••••••••"
              class="w-full input border-gray-200 dark:border-gray-700 px-4 py-3 rounded-xl dark:bg-gray-900 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          <button
            type="submit"
            disabled={passwordLoginBusy}
            class="w-full py-3 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 active:scale-[0.98] rounded-xl transition-all shadow-md shadow-primary-500/20 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {passwordLoginBusy ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
      {/if}
    </div>

    <!-- Stats preview grid -->
    <div class="grid grid-cols-4 gap-2 mt-8">
      {#each [
        { emoji: '🏃', label: 'Activity' },
        { emoji: '💧', label: 'Hydration' },
        { emoji: '😴', label: 'Sleep' },
        { emoji: '🥗', label: 'Nutrition' },
      ] as { emoji, label }}
        <div class="flex flex-col items-center p-2 rounded-xl bg-gray-50 dark:bg-gray-700/30 border border-gray-100 dark:border-gray-700/50">
          <span class="text-xl mb-1">{emoji}</span>
          <span class="text-[10px] font-medium text-gray-500">{label}</span>
        </div>
      {/each}
    </div>

    <p class="text-center text-xs text-gray-400 dark:text-gray-500 mt-6">
      Askesis v{APP_VERSION} — health logging made simple
    </p>
  </div>
</div>
