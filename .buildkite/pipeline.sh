#!/bin/bash

set -e

export BASE=".buildkite"
STEPS="$BASE/steps"

echo "env:"
echo "  BASE: $BASE"
echo "  REGISTRY: $REGISTRY"
echo "  PATRONI_IMG: $REGISTRY/patroni"
echo "steps:"

cat "$STEPS/test.yml"
cat "$STEPS/deploy.yml"
