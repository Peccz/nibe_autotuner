#!/usr/bin/env python3
"""Deprecated token repair helper.

This script used to write a hard-coded myUplink token file. Hard-coded tokens are
not safe in a repository, especially with WRITESYSTEM scope. Re-authenticate via
the normal OAuth flow instead.
"""


def main():
    raise SystemExit(
        "Refusing to create tokens from hard-coded values. "
        "Run `PYTHONPATH=/home/peccz/AI/nibe_autotuner/src "
        "python src/integrations/auth.py` to authenticate."
    )


if __name__ == "__main__":
    main()
