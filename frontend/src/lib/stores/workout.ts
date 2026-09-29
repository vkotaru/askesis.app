/**
 * The live workout: everything between walking into the gym and there being a
 * row in `activities`.
 *
 * ## Why this exists at all
 *
 * Logging a session used to mean opening the Activities form — date, name,
 * type, duration, calories, distance, URL, notes, tags, icon — with the set
 * logger as one field near the bottom. That is record-keeping done afterwards.
 * A gym app is a *session*: you start it, it runs, you log each set as you
 * finish it, and at the end it becomes the record. The target is two taps from
 * a cold app to a live session and one tap per set; if a change here makes a
 * set cost two taps, the change is wrong.
 *
 * ## Where the draft lives, and why not on the server
 *
 * One Dexie row, never synced. The obvious alternative — create the Activity at
 * "Start" and update it per set — is wrong four ways: the server's writers
 * delete and reinsert every set row on each update; offline that queues one
 * whole-session replace per set, and `collapseQueue` folds create-then-delete,
 * not update-then-update; an abandoned session would be real history the other
 * account can see; and `updateActivity` attempts the network between every set,
 * in the one place there is no network.
 *
 * ## Clocks
 *
 * Every timer derives from a stored **instant**, never an accumulating counter.
 * `setInterval` is throttled or suspended in a backgrounded tab, so a session
 * timed by incrementing seconds comes back wrong after a screen lock. Deriving
 * `now - startedAt` means a lock, a reload and a twenty-minute phone call all
 * produce the right number, and "rest finished four minutes ago" becomes
 * something the UI can say rather than a bug.
 *
 * ## Persistence cadence
 *
 * Structural changes (tick, add, remove, start, finish) write immediately.
 * Typing debounces at 300ms. `visibilitychange` and `pagehide` force a flush —
 * that is the screen-lock path and the one that matters. `beforeunload` is not
 * used; it does not fire reliably on mobile.
 */
import { derived, get, writable } from 'svelte/store';
import { browser } from '$app/environment';
import { db, type DraftExercise, type DraftSet, type LiveSessionDraft } from '$lib/db';
import { offlineApi } from '$lib/stores/data';
import { currentUserId } from '$lib/stores/user';
import type {
  ActivityInput,
  CatalogEntry,
  Exercise,
  Routine,
  SetType,
  TrackingType,
} from '$lib/api/client';

/** A session untouched for this long is offered up rather than silently resumed. */
const STALE_AFTER_MS = 6 * 60 * 60 * 1000;
const DEFAULT_REST_SECONDS = 120;
const TYPING_DEBOUNCE_MS = 300;

/** The draft, or null when nothing is running. */
export const liveSession = writable<LiveSessionDraft | null>(null);

/** Ticks once a second while a session is live, so elapsed values recompute. */
export const clockTick = writable(Date.now());

/**
 * Has the draft been read from Dexie yet?
 *
 * `liveSession` is null both when there is no workout and when we have not
 * looked. Anything that acts on "no workout" — the /workout route redirecting
 * home, most obviously — must wait for this, or reloading mid-session throws
 * you out of a workout that is sitting in the database.
 */
export const liveSessionLoaded = writable(false);

export const hasLiveSession = derived(liveSession, ($s) => $s !== null);

let tickHandle: ReturnType<typeof setInterval> | null = null;
let saveHandle: ReturnType<typeof setTimeout> | null = null;
let wakeLock: WakeLockSentinel | null = null;

const uuid = () =>
  browser && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

const iso = () => new Date().toISOString();

// ── Persistence ──────────────────────────────────────────────────────────────

async function persist(draft: LiveSessionDraft): Promise<void> {
  if (!browser) return;
  if (draft.localId) await db.liveSession.put(draft);
  else draft.localId = await db.liveSession.add(draft);
}

/** Write now. For anything structural — a tick, an add, a removal. */
async function saveNow(): Promise<void> {
  const draft = get(liveSession);
  if (!draft) return;
  if (saveHandle) {
    clearTimeout(saveHandle);
    saveHandle = null;
  }
  draft.lastTouchedAt = iso();
  await persist(draft);
}

/** Write shortly. For keystrokes, which would otherwise write per character. */
function saveSoon(): void {
  if (saveHandle) clearTimeout(saveHandle);
  saveHandle = setTimeout(() => {
    saveHandle = null;
    void saveNow();
  }, TYPING_DEBOUNCE_MS);
}

function touch(mutate: (d: LiveSessionDraft) => void, immediate = true): void {
  const draft = get(liveSession);
  if (!draft) return;
  mutate(draft);
  liveSession.set(draft);
  if (immediate) void saveNow();
  else saveSoon();
}

// ── Screen wake lock ─────────────────────────────────────────────────────────

/**
 * Keep the screen on while a session is live.
 *
 * The best fix for "the phone locks between sets" is for it not to lock. Also
 * the only way the rest-timer alert reliably lands, since a PWA cannot be woken
 * on a timer with the screen off — there is no alarm to promise, so this is the
 * mitigation instead of one.
 *
 * Absent on some browsers and released automatically whenever the page hides,
 * hence the re-acquire on visibility. Every call is guarded; the app is correct
 * without it.
 */
async function acquireWakeLock(): Promise<void> {
  if (!browser || !('wakeLock' in navigator)) return;
  try {
    wakeLock = await navigator.wakeLock.request('screen');
  } catch {
    wakeLock = null;
  }
}

async function releaseWakeLock(): Promise<void> {
  try {
    await wakeLock?.release();
  } catch {
    // Already released, or the page was hidden. Nothing to do.
  }
  wakeLock = null;
}

// ── Lifecycle ────────────────────────────────────────────────────────────────

function startClock(): void {
  if (tickHandle) return;
  tickHandle = setInterval(() => clockTick.set(Date.now()), 1000);
}

function stopClock(): void {
  if (tickHandle) clearInterval(tickHandle);
  tickHandle = null;
}

/**
 * Load any draft belonging to this account. Called once on app start.
 *
 * Returns the draft so the caller can decide what to do with a stale one — this
 * never auto-finishes and never auto-discards. Those sets exist in exactly one
 * place.
 */
export async function loadLiveSession(): Promise<LiveSessionDraft | null> {
  if (!browser) return null;
  const uid = currentUserId();
  if (!uid) return null;
  // Set only once the read has actually happened — see `liveSessionLoaded`.
  const draft = (await db.liveSession.where('userId').equals(uid).toArray())[0] ?? null;
  liveSession.set(draft);
  liveSessionLoaded.set(true);
  if (draft) {
    startClock();
    void acquireWakeLock();
    void navigator.storage?.persist?.().catch(() => {});
    void resolveTrackingTypes();
  }
  return draft;
}

export function isStale(draft: LiveSessionDraft): boolean {
  return Date.now() - new Date(draft.lastTouchedAt).getTime() > STALE_AFTER_MS;
}

export async function startSession(options: {
  name?: string;
  routine?: Routine | null;
  exercises?: {
    name: string;
    catalogId: number | null;
    plannedSets?: number;
    trackingType?: TrackingType | null;
  }[];
} = {}): Promise<void> {
  const uid = currentUserId();
  if (!uid) throw new Error('Not signed in');

  // A routine stores which movements, not what kind of set each one takes —
  // `resolveTrackingTypes` fills that in from the library once the draft exists.
  const fromRoutine = (options.routine?.exercises ?? []).map((r) => ({
    name: r.name,
    catalogId: r.catalog_id ?? null,
    plannedSets: r.target_sets ?? 1,
    trackingType: null as TrackingType | null,
  }));
  const seed = options.exercises ?? fromRoutine;

  const draft: LiveSessionDraft = {
    userId: uid,
    startedAt: iso(),
    lastTouchedAt: iso(),
    name: options.name ?? options.routine?.name ?? 'Workout',
    routineId: options.routine?.id ?? null,
    restSecondsDefault: DEFAULT_REST_SECONDS,
    restEndsAt: null,
    exercises: seed.map((e) => ({
      draftId: uuid(),
      catalogId: e.catalogId,
      name: e.name,
      trackingType: e.trackingType ?? null,
      sets: Array.from({ length: Math.max(1, e.plannedSets ?? 1) }, () => blankSet()),
    })),
  };

  liveSession.set(draft);
  liveSessionLoaded.set(true);
  await saveNow();
  startClock();
  void acquireWakeLock();
  void navigator.storage?.persist?.().catch(() => {});

  // While there is still signal. A routine's movements are known now; their
  // history is what makes logging fast, and it will not be fetchable later.
  const ids = draft.exercises.map((e) => e.catalogId).filter((id): id is number => !!id);
  if (ids.length) void offlineApi.prefetchHistory(ids);
  // A routine names movements but not what kind of set each one takes.
  void resolveTrackingTypes();
}

function blankSet(setType: SetType = 'working'): DraftSet {
  return {
    draftId: uuid(),
    state: 'planned',
    weightKg: null,
    reps: null,
    durationSeconds: null,
    distanceM: null,
    setType,
    rpe: null,
  };
}

/**
 * Fill in any exercise whose kind we do not know yet, from the cached library.
 *
 * Runs on start *and* on load, and the second is the point: a draft written
 * before movements had a kind — or one seeded from a routine while the picker
 * had not been opened — would otherwise ask for weight and reps forever, and
 * the session it belongs to is exactly the one you cannot restart.
 *
 * Offline-safe: `getCatalog` serves from Dexie, and an exercise that stays
 * unresolved simply keeps the old behaviour.
 */
async function resolveTrackingTypes(): Promise<void> {
  const draft = get(liveSession);
  if (!draft) return;
  const unknown = draft.exercises.filter((e) => e.catalogId && !e.trackingType);
  if (!unknown.length) return;
  let catalog: CatalogEntry[];
  try {
    catalog = await offlineApi.getCatalog();
  } catch {
    return;
  }
  const byId = new Map(catalog.map((c) => [c.id, c.tracking_type]));
  // Decided before touching the draft, so an exercise the library has never
  // heard of does not cost a write on every load.
  const resolved = new Map(
    unknown
      .map((e) => [e.draftId, byId.get(e.catalogId as number)] as const)
      .filter((pair): pair is readonly [string, TrackingType] => !!pair[1])
  );
  if (!resolved.size) return;
  touch((d) => {
    for (const ex of d.exercises) {
      const kind = resolved.get(ex.draftId);
      if (kind) ex.trackingType = kind;
    }
  });
}

export async function discardSession(): Promise<void> {
  const draft = get(liveSession);
  if (draft?.localId) await db.liveSession.delete(draft.localId);
  liveSession.set(null);
  liveSessionLoaded.set(true);
  stopClock();
  void releaseWakeLock();
}

// ── Editing ──────────────────────────────────────────────────────────────────

export function addExercise(
  entry:
    | Pick<CatalogEntry, 'id' | 'name' | 'tracking_type'>
    | { id: null; name: string; tracking_type?: TrackingType }
) {
  touch((d) => {
    d.exercises = [
      ...d.exercises,
      {
        draftId: uuid(),
        catalogId: entry.id,
        name: entry.name,
        // Copied, not looked up at render time: the draft has to keep working
        // offline and after the library entry is edited or archived.
        trackingType: entry.tracking_type ?? 'weight_reps',
        sets: [blankSet()],
      },
    ];
  });
  if (entry.id) void offlineApi.prefetchHistory([entry.id]);
}

/**
 * Correct what kind of set a movement takes, mid-session.
 *
 * Applied to the draft immediately and pushed to the shared library in the
 * background, in that order. A plank that asks for kilograms is wrong *now*,
 * on a screen someone is standing in front of, and making the fix wait on the
 * network would mean it could not be made at all in the one place it is most
 * likely to be noticed. The library edit is best-effort for the same reason:
 * offline, this session logs correctly and the library catches up next time.
 *
 * Nothing already typed is discarded — `weightKg` and `reps` stay on the row,
 * so switching back restores them. Only which fields are *shown* changes.
 */
export function setTrackingType(exerciseId: string, kind: TrackingType) {
  let catalogId: number | null = null;
  touch((d) => {
    const ex = d.exercises.find((e) => e.draftId === exerciseId);
    if (!ex) return;
    ex.trackingType = kind;
    catalogId = ex.catalogId;
  });
  if (catalogId) {
    // PATCH, not PUT. The catalogue's PUT takes the whole entry and clears what
    // it does not carry, so sending {name, tracking_type} here wiped the muscle
    // group, the video link and the form notes — for both accounts, from a
    // sheet that only mentioned how the movement is measured.
    void offlineApi
      .patchCatalogEntry(catalogId, { tracking_type: kind })
      .catch(() => {
        // Offline, or someone archived it. The session is already right.
      });
  }
}

export function removeExercise(draftId: string) {
  touch((d) => {
    d.exercises = d.exercises.filter((e) => e.draftId !== draftId);
  });
}

export function addSet(exerciseId: string) {
  touch((d) => {
    const ex = d.exercises.find((e) => e.draftId === exerciseId);
    if (!ex) return;
    // Repeat the last set rather than starting empty: within a block the weight
    // usually holds, so "same again" should be the default and the edit the
    // exception. Copied as `planned` — a set you have not done is not a claim.
    const previous = ex.sets[ex.sets.length - 1];
    ex.sets = [
      ...ex.sets,
      {
        ...blankSet(previous?.setType ?? 'working'),
        weightKg: previous?.weightKg ?? null,
        reps: previous?.reps ?? null,
      },
    ];
  });
}

export function removeSet(exerciseId: string, setId: string) {
  touch((d) => {
    const ex = d.exercises.find((e) => e.draftId === exerciseId);
    if (ex) ex.sets = ex.sets.filter((s) => s.draftId !== setId);
  });
}

export function updateSet(
  exerciseId: string,
  setId: string,
  patch: Partial<DraftSet>,
  immediate = false
) {
  touch((d) => {
    const ex = d.exercises.find((e) => e.draftId === exerciseId);
    const set = ex?.sets.find((s) => s.draftId === setId);
    if (set) Object.assign(set, patch);
  }, immediate);
}

export function setExerciseNotes(exerciseId: string, notes: string) {
  touch((d) => {
    const ex = d.exercises.find((e) => e.draftId === exerciseId);
    if (ex) ex.notes = notes;
  }, false);
}

/**
 * Every kind of set, in the order they appear in a session.
 *
 * A cycle button was fine at three and is wrong at five — reaching "cooldown"
 * would take four taps and pass through two states that mean something. The
 * sheet offers all five at once instead.
 */
export const SET_TYPES: { value: SetType; label: string; hint: string }[] = [
  { value: 'warmup', label: 'Warm-up', hint: 'Not counted in volume' },
  { value: 'working', label: 'Working', hint: 'The work' },
  { value: 'drop', label: 'Drop', hint: 'Straight on from the last set, lighter' },
  { value: 'failure', label: 'Failure', hint: 'Taken to the last rep you had' },
  { value: 'cooldown', label: 'Cool-down', hint: 'Not counted in volume' },
];

export function setSetType(exerciseId: string, setId: string, setType: SetType) {
  touch((d) => {
    const set = d.exercises
      .find((e) => e.draftId === exerciseId)
      ?.sets.find((s) => s.draftId === setId);
    if (set) set.setType = setType;
  });
}

/**
 * Tick a set: the moment it becomes something you did.
 *
 * This is the claim, and it is what makes prefilling honest. Untick is one tap
 * with no dialog — it is reversible, so asking would be noise.
 */
export function toggleLogged(exerciseId: string, setId: string) {
  touch((d) => {
    const set = d.exercises.find((e) => e.draftId === exerciseId)?.sets.find((s) => s.draftId === setId);
    if (!set) return;
    if (set.state === 'logged') {
      set.state = 'planned';
      set.loggedAt = null;
      return;
    }
    set.state = 'logged';
    set.loggedAt = iso();
    const rest = d.exercises.find((e) => e.draftId === exerciseId)?.restSeconds ?? d.restSecondsDefault;
    d.restEndsAt = new Date(Date.now() + rest * 1000).toISOString();
  });
}

export function adjustRest(seconds: number) {
  touch((d) => {
    if (!d.restEndsAt) return;
    const next = new Date(d.restEndsAt).getTime() + seconds * 1000;
    d.restEndsAt = new Date(Math.max(next, Date.now())).toISOString();
  });
}

export function skipRest() {
  touch((d) => {
    d.restEndsAt = null;
  });
}

// ── Derived numbers ──────────────────────────────────────────────────────────

/**
 * A set only counts as done if it says what was done.
 *
 * Both fields empty is not a record of anything — it renders as "— × —" in
 * history — and a tick is a 44px target sitting beside two blank inputs, so a
 * mis-tap is considerably more likely than a deliberate contentless set. A
 * bodyweight set has reps; a timed hold has a weight or a note. Neither has
 * neither.
 */
export function isMeaningful(set: DraftSet): boolean {
  return (
    set.weightKg != null ||
    set.reps != null ||
    set.durationSeconds != null ||
    set.distanceM != null
  );
}

/** Only logged sets that were the work. A warm-up or a cool-down is not. */
export function sessionTotals(draft: LiveSessionDraft | null) {
  if (!draft) return { sets: 0, volumeKg: 0, plannedRemaining: 0, emptyLogged: 0 };
  let sets = 0;
  let volumeKg = 0;
  let plannedRemaining = 0;
  let emptyLogged = 0;
  for (const ex of draft.exercises) {
    for (const s of ex.sets) {
      if (s.state !== 'logged') {
        plannedRemaining += 1;
        continue;
      }
      if (!isMeaningful(s)) {
        emptyLogged += 1;
        continue;
      }
      if (s.setType === 'warmup' || s.setType === 'cooldown') continue;
      sets += 1;
      volumeKg += (s.weightKg ?? 0) * (s.reps ?? 0);
    }
  }
  return { sets, volumeKg, plannedRemaining, emptyLogged };
}

/**
 * How long the session ran.
 *
 * To the **last logged set**, not to now. A session you forgot to finish until
 * the next morning must not record fourteen hours. Clamped to the range the
 * API accepts, and a sub-minute session reports 1 rather than 0 — `duration_mins`
 * is `ge=1`, so 0 would be rejected and the push would retry forever.
 */
export function sessionDurationMins(draft: LiveSessionDraft | null): number | null {
  if (!draft) return null;
  const stamps = draft.exercises
    .flatMap((e) => e.sets)
    .map((s) => s.loggedAt)
    .filter((t): t is string => !!t)
    .map((t) => new Date(t).getTime());
  if (!stamps.length) return null;
  const mins = Math.round((Math.max(...stamps) - new Date(draft.startedAt).getTime()) / 60000);
  return Math.min(Math.max(mins, 1), 1440);
}

// ── Finishing ────────────────────────────────────────────────────────────────

/**
 * Turn the draft into one Activity, through the offline path that already works.
 *
 * Only `logged` sets cross. Planned rows were never a claim and disappear with
 * the draft. Draft-only fields are dropped explicitly rather than relying on the
 * server ignoring unknown keys — that would make a client field's fate depend on
 * a Pydantic default.
 */
export async function finishSession(name: string, notes?: string): Promise<void> {
  const draft = get(liveSession);
  if (!draft) return;

  const exercises: Exercise[] = draft.exercises
    .map((ex, position) => ({
      name: ex.name,
      catalog_id: ex.catalogId ?? undefined,
      position,
      notes: ex.notes || undefined,
      sets_detail: ex.sets
        .filter((s) => s.state === 'logged' && isMeaningful(s))
        .map((s, i) => ({
          set_number: i + 1,
          weight_kg: s.weightKg,
          reps: s.reps,
          duration_seconds: s.durationSeconds ?? null,
          distance_m: s.distanceM ?? null,
          set_type: s.setType,
          rpe: s.rpe ?? null,
        })),
    }))
    .filter((e) => e.sets_detail.length > 0);

  const started = new Date(draft.startedAt);
  const payload: ActivityInput = {
    // The date the session STARTED, not today — a workout finished after
    // midnight, or resumed the next morning, belongs to the day it happened.
    date: `${started.getFullYear()}-${String(started.getMonth() + 1).padStart(2, '0')}-${String(
      started.getDate()
    ).padStart(2, '0')}`,
    name: name.trim() || 'Workout',
    activity_type: 'strength',
    duration_mins: sessionDurationMins(draft) ?? undefined,
    time_of_day: timeOfDay(started),
    notes: notes?.trim() || undefined,
    icon: 'dumbbell',
    exercises,
  };

  await offlineApi.createActivity(payload);
  await discardSession();
}

function timeOfDay(at: Date): ActivityInput['time_of_day'] {
  const h = at.getHours();
  if (h < 11) return 'morning';
  if (h < 16) return 'afternoon';
  if (h < 21) return 'evening';
  return 'night';
}

// ── Browser wiring ───────────────────────────────────────────────────────────

if (browser) {
  // The screen-lock and app-switch path. Not `beforeunload`, which does not fire
  // reliably on mobile.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') void saveNow();
    else if (get(liveSession)) void acquireWakeLock();
  });
  window.addEventListener('pagehide', () => void saveNow());
}
