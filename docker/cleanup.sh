#!/usr/bin/env sh

find /srv -name '.git*' -exec rm -rf '{}' \;
find /srv -name '*docker*' -delete
find /srv -name 'docs' -type d -exec rm -rf '{}' \;
find /srv -name 'cmake' -type d -exec rm -rf '{}' \;
find /srv -name 'examples' -type d -exec rm -rf '{}' \;
find /srv -name 'tests' -type d -exec rm -rf '{}' \;
find /srv -name 'scripts' -type d -exec rm -rf '{}' \;
find /srv -name 'plugins' -type d -exec rm -rf '{}' \;
find /srv -name 'icons' -type d -exec rm -rf '{}' \;
find /srv -name 'meshes' -type d -exec rm -rf '{}' \;
find /srv -name 'images' -type d -exec rm -rf '{}' \;
find /srv -name 'qml' -type d -exec rm -rf '{}' \;
find /srv -name 'setting_visibility' -type d -exec rm -rf '{}' \;
find /srv -name 'shaders' -type d -exec rm -rf '{}' \;
find /srv -name 'themes' -type d -exec rm -rf '{}' \;
find /srv -name 'CMake*' -type f -delete
find /srv -name '*.cmake' -type f -delete
find /srv -name 'Docker*' -type f -delete
find /srv -name '*.sh' -type f -delete
find /srv -name '*.in' -type f -delete
find /srv -name '*.ini' -type f -delete
find /srv -name '*.nsi' -type f -delete
find /srv -name '*.md' -type f -delete
find /srv -name '*.yaml' -type f -delete
find /srv -name 'Jenkinsfile' -type f -delete
find /srv -name 'cura.sharedmimeinfo' -type f -delete
find /srv -name 'Doxyfile' -type f -delete
find /srv -name '*.dict' -type f -delete
find /srv -name 'LICENSE' -type f -delete
find /srv -name 'bundled_packages.json' -type f -delete
