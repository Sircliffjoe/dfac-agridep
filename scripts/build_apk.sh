#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

BUILD_TOOLS="/home/eventro/Android/Sdk/build-tools/34.0.0"
PLATFORM_JAR="/home/eventro/Android/Sdk/platforms/android-34/android.jar"
KEYSTORE="${HOME}/.android/debug.keystore"
OUTPUT_APK="$ROOT_DIR/agridep/static/downloads/dfac-agridep-field-v1.0.0.apk"

cd "$ROOT_DIR"
mkdir -p mobile/builder/gen mobile/builder/obj mobile/builder/dex agridep/static/downloads

echo "==> Step 1: Compiling resources..."
$BUILD_TOOLS/aapt2 compile --dir mobile/builder/res -o mobile/builder/compiled_res.zip

echo "==> Step 2: Linking package..."
$BUILD_TOOLS/aapt2 link -I $PLATFORM_JAR \
    --manifest mobile/builder/AndroidManifest.xml \
    -o mobile/builder/base.apk \
    mobile/builder/compiled_res.zip \
    --auto-add-overlay \
    --java mobile/builder/gen

echo "==> Step 3: Compiling Java..."
javac -d mobile/builder/obj \
    -cp $PLATFORM_JAR \
    mobile/builder/src/ng/dfac/agridep/mobile/MainActivity.java

echo "==> Step 4: Converting bytecode to DEX..."
$BUILD_TOOLS/d8 --output mobile/builder/dex/ \
    mobile/builder/obj/ng/dfac/agridep/mobile/*.class

echo "==> Step 5: Adding DEX to APK..."
cd mobile/builder/dex
zip -u ../base.apk classes.dex
cd "$ROOT_DIR"

echo "==> Step 6: Zipalign APK..."
rm -f mobile/builder/aligned.apk
$BUILD_TOOLS/zipalign -v -p 4 mobile/builder/base.apk mobile/builder/aligned.apk

echo "==> Step 7: Signing APK..."
$BUILD_TOOLS/apksigner sign \
    --ks "$KEYSTORE" \
    --ks-pass pass:android \
    --key-pass pass:android \
    --out "$OUTPUT_APK" \
    mobile/builder/aligned.apk

echo "==> Step 8: Verifying signature..."
$BUILD_TOOLS/apksigner verify "$OUTPUT_APK"

echo "✓ DFAC AgriDEP Field APK built successfully at: $OUTPUT_APK"
