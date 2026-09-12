#!/bin/sh
set -eu

command_name="${1:-pi-engineering}"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
bin_dir="${HOME}/.local/bin"
target="${bin_dir}/${command_name}"

case "${command_name}" in
  ""|*/*)
    echo "Invalid command name: ${command_name}" >&2
    exit 2
    ;;
esac

mkdir -p "${bin_dir}"

if [ -e "${target}" ] && [ ! -L "${target}" ]; then
  echo "Refusing to overwrite non-symlink file: ${target}" >&2
  exit 3
fi

if [ -L "${target}" ]; then
  current="$(readlink "${target}")"
  if [ "${current}" != "${script_dir}/pi.py" ] && [ "${current}" != "${script_dir}/.venv/bin/pi-engineering" ]; then
    echo "Refusing to replace existing symlink ${target} -> ${current}" >&2
    exit 4
  fi
fi

python3 -m venv "${script_dir}/.venv"
"${script_dir}/.venv/bin/python" -m pip install -c "${script_dir}/requirements.lock" "${script_dir}"
"${script_dir}/.venv/bin/python" -m pip check
ln -sfn "${script_dir}/.venv/bin/pi-engineering" "${target}"

echo "Installed ${command_name} -> ${script_dir}/.venv/bin/pi-engineering"
echo "Try: ${command_name} setup"
