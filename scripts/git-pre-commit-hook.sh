#!/bin/bash
exec "$(git rev-parse --show-toplevel)/scripts/precommit_checks.sh"
