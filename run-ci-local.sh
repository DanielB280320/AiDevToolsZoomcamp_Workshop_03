#!/usr/bin/env bash
# Run .github/workflows/ci.yml locally with act, deploying to the kind cluster.
#
# act runs job containers on the host network, so the kind API server's
# 127.0.0.1 address in the kubeconfig works as-is, and it mounts the host's
# Docker socket, which `docker build` and `kind load` use.
set -euo pipefail

cluster="${KIND_CLUSTER:-agent-relay}"
cd "$(dirname "$0")"

# --pull=false reuses the cached runner image instead of re-pulling it per job.
act push \
  --pull=false \
  -s KUBECONFIG="$(kind get kubeconfig --name "$cluster")" \
  "$@"
