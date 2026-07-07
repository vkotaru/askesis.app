#!/usr/bin/env bash
#
# Launch the Askesis native app on an emulator for review.
#   - boots the `askesis_test` AVD (windowed, so you can interact)
#   - builds the debug APK if it's missing (pass --build to force a rebuild)
#   - installs and launches the app
#
# Usage:  ./run.sh [--build]
#
set -euo pipefail

ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
ADB="$ANDROID_HOME/platform-tools/adb"
EMULATOR="$ANDROID_HOME/emulator/emulator"
AVD="askesis_test"
PKG="app.askesis.native"
ACTIVITY="$PKG/app.askesis.MainActivity"
APK="$(dirname "$0")/app/build/outputs/apk/debug/app-debug.apk"

[ -x "$ADB" ] || { echo "adb not found at $ADB — set ANDROID_HOME"; exit 1; }

# 1. Build the APK if needed (or when --build is passed).
if [ "${1:-}" = "--build" ] || [ ! -f "$APK" ]; then
  echo "==> Building debug APK..."
  (cd "$(dirname "$0")" && ./gradlew :app:assembleDebug)
fi

# 2. Boot the emulator if it isn't already running.
if ! "$ADB" devices | grep -q "emulator-.*device"; then
  echo "==> Booting emulator '$AVD'..."
  "$EMULATOR" -avd "$AVD" -no-snapshot -no-boot-anim -gpu swiftshader_indirect \
    >/tmp/askesis_emulator.log 2>&1 &
  echo "    (log: /tmp/askesis_emulator.log)"
else
  echo "==> Emulator already running."
fi

# 3. Wait for it to finish booting.
echo "==> Waiting for device to boot..."
"$ADB" wait-for-device
until [ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
  sleep 2
done
echo "    booted."

# 4. Install + launch.
echo "==> Installing $APK"
"$ADB" install -r "$APK"
echo "==> Launching $ACTIVITY"
"$ADB" shell am start -n "$ACTIVITY" >/dev/null

echo "==> Done. Askesis is running on the emulator."
echo "    Reinstall after changes:  ./run.sh --build"
echo "    Stop the emulator:        $ADB emu kill"
