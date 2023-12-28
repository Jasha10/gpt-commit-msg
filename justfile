mypy:
    watchexec --exts py -- 'dmypy run -- *.py'
pyright:
    pyright --watch
ruff:
    watchexec --exts py -- ruff .
lints-inplace:
    watchexec --exts py -- 'isort . && black .'

install-dev:
    #!/usr/bin/env bash
    set -euxo pipefail

    # ensure that pip is installed via direnv:
    [[ "$(which pip)" = $PWD/.direnv/* ]]

    pip install -e .[dev]
