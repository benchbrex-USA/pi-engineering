#!/bin/sh
set -eu

command_name="${1:-pi-engineering}"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
target="${HOME}/.local/bin/${command_name}"

if [ ! -L "${target}" ]; then
  echo "No Pi Engineering symlink found at ${target}"
  exit 0
fi

current="$(readlink "${target}")"
if [ "${current}" != "${script_dir}/pi.py" ] && [ "${current}" != "${script_dir}/.venv/bin/pi-engineering" ]; then
  echo "Refusing to remove unrelated symlink ${target} -> ${current}" >&2
  exit 4
fi

rm "${target}"
echo "Removed ${target}"
