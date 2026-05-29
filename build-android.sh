#!/bin/bash
set -e

# Default the Capacitor API host to the production Railway deploy unless the
# caller has set VITE_API_BASE explicitly (e.g. for staging). The web build
# ignores this var; the native build bakes it into the bundle at compile time
# so the APK can reach the backend across origins.
: "${VITE_API_BASE:=https://askesisapp-production.up.railway.app}"
export VITE_API_BASE

if [[ "$VITE_API_BASE" != http://* && "$VITE_API_BASE" != https://* ]]; then
  echo "VITE_API_BASE must be an absolute http(s) URL — got: '$VITE_API_BASE'" >&2
  exit 1
fi

echo "=== Building SvelteKit Frontend (VITE_API_BASE=$VITE_API_BASE) ==="
cd frontend
npm run build

echo "=== Syncing Web Assets with Capacitor ==="
npx cap sync android

echo "=== Compiling Android App (Gradle) ==="
export ANDROID_HOME=/home/prasanth/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/tools:$ANDROID_HOME/platform-tools

cd android
chmod +x gradlew
./gradlew assembleDebug

echo "=== Build Complete ==="
echo "Debug APK generated at: frontend/android/app/build/outputs/apk/debug/app-debug.apk"
