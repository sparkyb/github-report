#!/bin/bash

virtualenv="venv"

case "$OSTYPE" in
  msys* | cywin* | win*)
    source "$virtualenv/Scripts/activate"
    ;;
  *)
    source "$virtualenv/bin/activate"
    ;;
esac

python github_report.py "$@"
