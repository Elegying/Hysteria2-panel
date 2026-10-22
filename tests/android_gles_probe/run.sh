#!/usr/bin/env bash
# Only an explicitly selected disposable CI emulator; never a connected phone.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "${1:-}" = emulator-5554
test "${2:-}" = default || test "${2:-}" = guest-angle
test "$(adb -s "$1" shell getprop ro.kernel.qemu | tr -d '\r')" = 1
probe_dir="$(cd "$(dirname "$0")" && pwd)"
probe_out="$RUNNER_TEMP/gles-probe"
mkdir -p "$probe_out/classes" "$probe_out/dex"
sdk_tools="$ANDROID_HOME/build-tools/36.0.0"
android_jar="$ANDROID_HOME/platforms/android-36/android.jar"
javac --release 8 -classpath "$android_jar" -d "$probe_out/classes" "$probe_dir/GlesProbe.java"
"$sdk_tools/d8" --min-api 24 --lib "$android_jar" --output "$probe_out/dex" \
  "$probe_out/classes/test/hy2/glesprobe/GlesProbe.class"
"$sdk_tools/aapt" package -f -M "$probe_dir/AndroidManifest.xml" -I "$android_jar" \
  -F "$probe_out/probe.apk"
jar uf "$probe_out/probe.apk" -C "$probe_out/dex" classes.dex
keytool -genkeypair -keystore "$probe_out/probe.jks" -storepass android -keypass android \
  -alias diagnostic -keyalg RSA -dname 'CN=Disposable GLES probe' -validity 2 -noprompt
"$sdk_tools/apksigner" sign --ks "$probe_out/probe.jks" --ks-pass pass:android "$probe_out/probe.apk"
sha256sum "$probe_out/probe.apk" > "$RUNNER_TEMP/gles-probe-apk-sha256.txt"
adb -s "$1" install -r "$probe_out/probe.apk"
adb -s "$1" shell am start -W -n test.hy2.glesprobe/.GlesProbe --es driver "$2"
for _attempt in $(seq 1 30); do
  test "$(adb -s "$1" get-state)" = device
  adb -s "$1" logcat -d -s 'Hy2GlesProbe:I' '*:S' > "$RUNNER_TEMP/gles-probe-log.txt"
  if grep -Fq PROBE_PASSED "$RUNNER_TEMP/gles-probe-log.txt"; then
    cat "$RUNNER_TEMP/gles-probe-log.txt"
    exit 0
  fi
  if grep -Fq PROBE_FAILED "$RUNNER_TEMP/gles-probe-log.txt"; then
    cat "$RUNNER_TEMP/gles-probe-log.txt"
    exit 1
  fi
  sleep 1
done
echo 'GLES probe did not complete' >&2
exit 1
