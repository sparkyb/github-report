#!/bin/bash

virtualenv="env"
requirements="requirements.txt"

echo "Creating virtualenv..."

case "$OSTYPE" in
  msys* | cywin* | win*)
    if command -v py > /dev/null; then
      py -3 -m virtualenv "$virtualenv"
    else
      virtualenv "$virtualenv"
    fi
    source "$virtualenv/Scripts/activate"
    ;;
  *)
    virtualenv -p python3 "$virtualenv"
    source "$virtualenv/bin/activate"
    ;;
esac

# Install requirements
pip install -r "$requirements"

echo "Creating virtualenv...DONE"
