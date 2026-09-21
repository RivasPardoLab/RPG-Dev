#!/bin/zsh
set -euo pipefail

project_dir="${0:A:h:h}"
build_dir="$project_dir/build"
dist_dir="$project_dir/dist"
source_icon="$project_dir/MainWin/icons/Lab2.png"
app_icon="$project_dir/icon.ico"
python_bin="${PYTHON_BIN:-python}"
openbabel_dir="$("$python_bin" -c 'from pathlib import Path; import openbabel; print(Path(openbabel.__file__).resolve().parent)')"
openbabel_version="$("$python_bin" -c 'import openbabel; print(openbabel.__version__)')"
openbabel_plugins="$openbabel_dir/lib/openbabel/$openbabel_version"

mkdir -p "$build_dir" "$dist_dir"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$build_dir/pyinstaller-cache}"

"$python_bin" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "RPG-macOS" \
    --osx-bundle-identifier "org.rivaspardolab.rpg.macos" \
    --collect-all "openbabel" \
    --copy-metadata "openbabel" \
    --add-binary "$openbabel_plugins:openbabel/lib/openbabel/$openbabel_version" \
    --icon "$app_icon" \
    --add-data "$project_dir/eight-bit-dragon.otf:." \
    --add-data "$source_icon:MainWin/icons" \
    "$project_dir/main.py"

app_path="$dist_dir/RPG-macOS.app"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName RPG macOS" "$app_path/Contents/Info.plist"
codesign --force --deep --sign - "$app_path"

dmg_path="$dist_dir/RPG-macOS.dmg"
if [[ -e "$dmg_path" ]]; then
    mv "$dmg_path" "$dmg_path.previous"
fi
if hdiutil create \
    -volname "RPG macOS" \
    -srcfolder "$app_path" \
    -ov \
    -format UDZO \
    "$dmg_path"; then
    echo "Built: $dmg_path"
else
    zip_path="$dist_dir/RPG-macOS.zip"
    if [[ -e "$zip_path" ]]; then
        mv "$zip_path" "$zip_path.previous"
    fi
    ditto -c -k --sequesterRsrc --keepParent "$app_path" "$zip_path"
    echo "DMG creation was unavailable; built: $zip_path"
fi

echo "Built: $app_path"
