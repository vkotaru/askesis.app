<script lang="ts">
  import { onMount } from 'svelte';
  import { user as userStore, cacheUser } from '$lib/stores/user';
  import { settings } from '$lib/stores/settings';
  import { hydrateFromServer } from '$lib/stores/data';
  import { api } from '$lib/api/client';
  import { sync, countLocalProfileData, migrateLocalToCloud } from '$lib/sync';

  interface LocalProfile {
    id: number;
    name: string;
  }

  let localProfiles: LocalProfile[] = [];
  let nameInput = '';
  let activeTab: 'online' | 'local' = 'local';
  let isCreatingNew = false;
  let errorMsg = '';

  // Username + password sign-in
  let usernameInput = '';
  let passwordInput = '';
  let passwordLoginBusy = false;

  onMount(() => {
    // Load local profiles
    try {
      const stored = localStorage.getItem('askesis_local_profiles');
      if (stored) {
        localProfiles = JSON.parse(stored);
      }
    } catch {
      localProfiles = [];
    }

    // Default tab based on whether local profiles exist
    if (localProfiles.length === 0) {
      isCreatingNew = true;
    }
  });

  function selectProfile(profile: LocalProfile) {
    const userObj = {
      id: profile.id,
      email: 'local@askesis.local',
      name: profile.name,
    };
    
    // Save as active local user
    localStorage.setItem('askesis_local_user', JSON.stringify(userObj));
    localStorage.setItem('askesis_last_local_user', JSON.stringify(profile));
    
    // Update store and hydrate local db structure
    userStore.set(userObj);
    settings.load();
    hydrateFromServer(userObj.id).catch(() => {});
  }

  function handleCreateProfile() {
    errorMsg = '';
    const cleanName = nameInput.trim();
    if (!cleanName) {
      errorMsg = 'Name is required';
      return;
    }

    // Check if name already exists
    if (localProfiles.some(p => p.name.toLowerCase() === cleanName.toLowerCase())) {
      errorMsg = 'A profile with this name already exists';
      return;
    }

    const newProfile: LocalProfile = {
      id: Date.now(),
      name: cleanName,
    };

    localProfiles = [...localProfiles, newProfile];
    localStorage.setItem('askesis_local_profiles', JSON.stringify(localProfiles));
    
    nameInput = '';
    isCreatingNew = false;
    
    // Sign in immediately
    selectProfile(newProfile);
  }

  async function bootstrapCloudUser() {
    // Clear any stale local-profile selection so the layout doesn't short-circuit
    // to local-mode and skip cloud hydration.
    localStorage.removeItem('askesis_local_user');

    const me = await api.getMe();
    userStore.set(me);
    await cacheUser(me);
    await settings.load();
    hydrateFromServer(me.id).catch(() => {});

    // If this device has data from a previous local profile session, offer
    // to push it up to the freshly-signed-in cloud account. Confirm before
    // moving anything since it's a one-way operation.
    try {
      const pending = await countLocalProfileData(me.id);
      const total =
        pending.dailyLogs +
        pending.activities +
        pending.meals +
        pending.foods +
        pending.measurements;
      if (total > 0) {
        const photoNote =
          pending.photosSkipped > 0
            ? `\n\n(${pending.photosSkipped} progress photos won't migrate automatically — please re-upload them after.)`
            : '';
        const ok = confirm(
          `Found ${total} entries from a previous local profile on this device. ` +
            `Push them into your cloud account?${photoNote}`,
        );
        if (ok) {
          await migrateLocalToCloud(me.id);
        }
      }
    } catch (err) {
      console.warn('Migration check failed:', err);
    }

    sync().catch(() => {});
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
      // Same bootstrap the layout runs on mount, so the user lands in the app
      // without a manual reload.
      await bootstrapCloudUser();
    } catch (err) {
      errorMsg =
        err instanceof Error && err.message !== 'Unauthorized'
          ? err.message
          : 'Incorrect username or password';
    } finally {
      passwordLoginBusy = false;
    }
  }

  function deleteProfile(profileId: number, event: MouseEvent) {
    event.stopPropagation();
    if (!confirm('Delete this local profile? This will not clear your database logs, but you will lose access to them under this profile name.')) return;
    
    localProfiles = localProfiles.filter(p => p.id !== profileId);
    localStorage.setItem('askesis_local_profiles', JSON.stringify(localProfiles));
    
    if (localProfiles.length === 0) {
      isCreatingNew = true;
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
        Track your health journey locally or in the cloud
      </p>
    </div>

    <!-- Segment Tab Controller -->
    <div class="flex p-1 bg-gray-100 dark:bg-gray-700/50 rounded-xl mb-6">
      <button
        type="button"
        on:click={() => activeTab = 'local'}
        class="flex-1 py-2 text-sm font-medium rounded-lg transition-all {activeTab === 'local' ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}"
      >
        📱 Local Mode
      </button>
      <button
        type="button"
        on:click={() => activeTab = 'online'}
        class="flex-1 py-2 text-sm font-medium rounded-lg transition-all {activeTab === 'online' ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}"
      >
        ☁️ Cloud Sync
      </button>
    </div>

    <!-- Tab Contents -->
    {#if activeTab === 'local'}
      <div class="space-y-4">
        {#if isCreatingNew}
          <!-- Create Local Profile Form -->
          <form on:submit|preventDefault={handleCreateProfile} class="space-y-4">
            <h2 class="text-lg font-semibold text-gray-800 dark:text-white">Create Local Profile</h2>
            <p class="text-xs text-gray-500 dark:text-gray-400">
              Your profile is stored entirely offline on this device's local database.
            </p>
            
            <div>
              <label for="profile-name" class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1 uppercase tracking-wider">
                Profile Name
              </label>
              <input
                id="profile-name"
                type="text"
                bind:value={nameInput}
                placeholder="e.g. User"
                class="w-full input border-gray-200 dark:border-gray-700 px-4 py-3 rounded-xl dark:bg-gray-900 focus:ring-primary-500 focus:border-primary-500"
              />
              {#if errorMsg}
                <p class="text-red-500 text-xs mt-1 font-medium">{errorMsg}</p>
              {/if}
            </div>

            <div class="flex gap-3">
              {#if localProfiles.length > 0}
                <button
                  type="button"
                  on:click={() => { isCreatingNew = false; errorMsg = ''; }}
                  class="flex-1 py-3 text-sm font-medium border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-xl transition-colors"
                >
                  Cancel
                </button>
              {/if}
              <button
                type="submit"
                class="flex-[2] py-3 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 active:scale-[0.98] rounded-xl transition-all shadow-md shadow-primary-500/20"
              >
                Create Profile
              </button>
            </div>
          </form>
        {:else}
          <!-- List of local profiles -->
          <div class="space-y-3">
            <div class="flex justify-between items-center mb-1">
              <h2 class="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Select Profile</h2>
              <button
                type="button"
                on:click={() => isCreatingNew = true}
                class="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline"
              >
                + Create New
              </button>
            </div>

            <div class="grid grid-cols-1 gap-2 max-h-48 overflow-y-auto pr-1">
              {#each localProfiles as profile}
                <button
                  type="button"
                  on:click={() => selectProfile(profile)}
                  class="flex items-center gap-3 p-3 text-left bg-gray-50 hover:bg-primary-50 dark:bg-gray-700/30 dark:hover:bg-gray-700 rounded-xl border border-gray-200/50 dark:border-gray-700/50 transition-all hover:scale-[1.01] hover:shadow-sm group"
                >
                  <div class="w-9 h-9 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center text-primary-700 dark:text-primary-300 font-bold text-sm">
                    {profile.name.charAt(0).toUpperCase()}
                  </div>
                  <span class="font-medium text-gray-800 dark:text-gray-200 flex-1 truncate">{profile.name}</span>
                  <button
                    type="button"
                    on:click={(e) => deleteProfile(profile.id, e)}
                    class="p-2 text-gray-400 hover:text-red-500 dark:hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Delete Profile"
                  >
                    🗑️
                  </button>
                </button>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {:else}
      <!-- Cloud sign in -->
      <div class="space-y-4">
        <p class="text-xs text-gray-500 dark:text-gray-400 text-center mb-4">
          Sign in to back up and sync your data with the web version.
        </p>

        {#if errorMsg && activeTab === 'online'}
          <p class="text-red-500 text-xs text-center font-medium">{errorMsg}</p>
        {/if}

        <!-- Username + password -->
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
              placeholder="e.g. user"
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
      </div>
    {/if}

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
      Askesis — health logging made simple
    </p>
  </div>
</div>
