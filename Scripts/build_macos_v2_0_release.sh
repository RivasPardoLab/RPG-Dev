#!/bin/zsh
set -euo pipefail

project_dir="${0:A:h:h}"
target_arch="${TARGET_ARCH:-}"
python_bin="${PYTHON_BIN:-python}"
version="2.0.0"

case "$target_arch" in
    arm64)
        architecture_label="ARM64"
        display_architecture="Apple Silicon"
        runner=("$python_bin")
        ;;
    x86_64)
        architecture_label="Intel"
        display_architecture="Intel"
        runner=(/usr/bin/arch -x86_64 "$python_bin")
        ;;
    *)
        echo "Set TARGET_ARCH to arm64 or x86_64." >&2
        exit 1
        ;;
esac

python_arch="$("${runner[@]}" -c 'import platform; print(platform.machine())')"
if [[ "$python_arch" != "$target_arch" ]]; then
    echo "Python architecture is $python_arch, expected $target_arch: $python_bin" >&2
    exit 1
fi

build_dir="$project_dir/build-v2.0-$target_arch"
release_dir="$project_dir/dist/RPG-Peptides-$version/macOS-$architecture_label"
app_name="RPG-macOS-v2.0-$architecture_label"
app_path="$release_dir/$app_name.app"
source_icon="$project_dir/MainWin/icons/Lab2.png"
app_icon="$project_dir/icon.ico"
openbabel_dir="$("${runner[@]}" -c 'from pathlib import Path; import openbabel; print(Path(openbabel.__file__).resolve().parent)')"
openbabel_version="$("${runner[@]}" -c 'import openbabel; print(openbabel.__version__)')"
openbabel_plugins="$openbabel_dir/lib/openbabel/$openbabel_version"

if [[ ! -d "$openbabel_plugins" ]]; then
    echo "Missing Open Babel plugins: $openbabel_plugins" >&2
    exit 1
fi

mkdir -p "$build_dir" "$release_dir"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$build_dir/pyinstaller-cache}"

"${runner[@]}" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --target-architecture "$target_arch" \
    --name "$app_name" \
    --osx-bundle-identifier "org.rivaspardolab.rpg.macos.v2.0.${target_arch}" \
    --collect-all "openbabel" \
    --collect-all "vina" \
    --collect-all "rdkit" \
    --collect-data "meeko" \
    --copy-metadata "openbabel-wheel" \
    --copy-metadata "meeko" \
    --copy-metadata "rdkit" \
    --exclude-module "IPython" \
    --exclude-module "matplotlib" \
    --exclude-module "pandas" \
    --exclude-module "prody" \
    --exclude-module "PySide6" \
    --exclude-module "PyQt6" \
    --add-binary "$openbabel_plugins:openbabel/lib/openbabel/$openbabel_version" \
    --icon "$app_icon" \
    --add-data "$project_dir/eight-bit-dragon.otf:." \
    --add-data "$source_icon:MainWin/icons" \
    --distpath "$release_dir" \
    --workpath "$build_dir/pyinstaller" \
    --specpath "$build_dir" \
    "$project_dir/main.py"

/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName RPG macOS 2.0 ($display_architecture)" "$app_path/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $version" "$app_path/Contents/Info.plist" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $version" "$app_path/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $version" "$app_path/Contents/Info.plist" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $version" "$app_path/Contents/Info.plist"

bad_architectures=0
while IFS= read -r -d '' candidate; do
    description="$(file -b "$candidate")"
    if [[ "$description" == *"Mach-O"* ]]; then
        architectures="$(/usr/bin/lipo -archs "$candidate" 2>/dev/null || true)"
        if [[ "$architectures" != "$target_arch" ]]; then
            echo "Unexpected architecture ($architectures): $candidate" >&2
            bad_architectures=1
        fi
    fi
done < <(find "$app_path" -type f -print0)
if (( bad_architectures != 0 )); then
    echo "The application contains unexpected Mach-O architectures." >&2
    exit 1
fi

codesign --force --deep --sign - "$app_path"
codesign --verify --deep --strict "$app_path"

package_staging="$build_dir/release-package"
package_root="$package_staging/$app_name"
rm -rf "$package_staging"
mkdir -p "$package_root"
ditto "$app_path" "$package_root/$app_name.app"
cp "$project_dir/README-RPG-v2.0-release.md" "$package_root/README.txt"
cp "$project_dir/LICENSE" "$package_root/LICENSE.txt"
cp "$project_dir/README-RPG-v2.0-release.md" "$release_dir/README.txt"
cp "$project_dir/LICENSE" "$release_dir/LICENSE.txt"

zip_path="$release_dir/$app_name.zip"
if [[ -e "$zip_path" ]]; then
    mv "$zip_path" "$zip_path.previous-$(date +%Y%m%d-%H%M%S)"
fi
ditto -c -k --sequesterRsrc --keepParent "$package_root" "$zip_path"

dmg_path="$release_dir/$app_name.dmg"
if [[ -e "$dmg_path" ]]; then
    mv "$dmg_path" "$dmg_path.previous-$(date +%Y%m%d-%H%M%S)"
fi
if hdiutil create \
    -volname "RPG macOS 2.0 $architecture_label" \
    -srcfolder "$package_root" \
    -ov \
    -format UDZO \
    "$dmg_path"; then
    echo "Built: $dmg_path"
else
    echo "DMG creation was unavailable; the ZIP remains ready to use." >&2
fi

checksum_path="$release_dir/SHA256SUMS.txt"
if [[ -f "$dmg_path" ]]; then
    shasum -a 256 "$zip_path" "$dmg_path" > "$checksum_path"
else
    shasum -a 256 "$zip_path" > "$checksum_path"
fi

echo "Built: $app_path"
echo "Built: $zip_path"
echo "Checksums: $checksum_path"
