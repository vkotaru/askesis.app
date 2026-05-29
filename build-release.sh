#!/bin/bash
set -e

# Make sure we're in the workspace root
cd "$(dirname "$0")"

KEYSTORE_FILE="askesis-release.keystore"
KEYSTORE_ALIAS="askesis-key"
AAB_PATH="frontend/android/app/build/outputs/bundle/release/app-release.aab"
SIGNED_AAB_PATH="frontend/android/app/build/outputs/bundle/release/app-release-signed.aab"

# Backend host the release bundle should target. Override for staging/local.
: "${VITE_API_BASE:=https://askesisapp-production.up.railway.app}"
export VITE_API_BASE

if [[ "$VITE_API_BASE" != http://* && "$VITE_API_BASE" != https://* ]]; then
  echo "VITE_API_BASE must be an absolute http(s) URL — got: '$VITE_API_BASE'" >&2
  exit 1
fi

echo "=== 1. Building SvelteKit Production Bundle (VITE_API_BASE=$VITE_API_BASE) ==="
cd frontend
npm run build

echo "=== 2. Syncing Assets with Capacitor ==="
npx cap sync android

echo "=== 3. Compiling Release App Bundle (.aab) ==="
export ANDROID_HOME=/home/prasanth/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/tools:$ANDROID_HOME/platform-tools

cd android
chmod +x gradlew
./gradlew bundleRelease
cd ../..

echo "=== 4. Checking Release Keystore ==="
if [ ! -f "$KEYSTORE_FILE" ]; then
  echo "No keystore found at '$KEYSTORE_FILE'."
  echo "We will now generate a new signing key using 'keytool'."
  echo "Please answer the prompts and remember the password you enter!"
  echo "--------------------------------------------------------"
  
  keytool -genkey -v -keystore "$KEYSTORE_FILE" -alias "$KEYSTORE_ALIAS" \
    -keyalg RSA -keysize 2048 -validity 10000
    
  echo "--------------------------------------------------------"
  echo "Keystore successfully created at: $(pwd)/$KEYSTORE_FILE"
  echo "IMPORTANT: Keep this file safe! If you lose it, you won't be able to update your app on Google Play."
fi

echo "=== 5. Signing the App Bundle (.aab) ==="
# Copy AAB to signed path
cp "$AAB_PATH" "$SIGNED_AAB_PATH"

echo "Please enter the keystore password to sign the bundle:"
jarsigner -verbose -sigalg SHA256withRSA -digestalg SHA-256 \
  -keystore "$KEYSTORE_FILE" "$SIGNED_AAB_PATH" "$KEYSTORE_ALIAS"

echo "=== Build & Signing Complete ==="
echo "Your Google Play publishable Android App Bundle (.aab) is generated at:"
echo "-> $(pwd)/$SIGNED_AAB_PATH"
