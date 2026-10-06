#!/usr/bin/env bash
set -euo pipefail

[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted ]] || {
  echo 'This script only creates clusters on disposable GitHub-hosted runners.' >&2
  exit 1
}

kind_version=v0.27.0
kind_dir="${RUNNER_TEMP:?}/appflowy-kind-bin"
mkdir -p "$kind_dir"
curl --fail --silent --show-error --location --retry 3 \
  "https://github.com/kubernetes-sigs/kind/releases/download/${kind_version}/kind-linux-amd64" \
  --output "$kind_dir/kind-linux-amd64"
curl --fail --silent --show-error --location --retry 3 \
  "https://github.com/kubernetes-sigs/kind/releases/download/${kind_version}/kind-linux-amd64.sha256sum" \
  --output "$kind_dir/kind-linux-amd64.sha256sum"
(cd "$kind_dir" && sha256sum --check kind-linux-amd64.sha256sum)
chmod +x "$kind_dir/kind-linux-amd64"
ln -s "$kind_dir/kind-linux-amd64" "$kind_dir/kind"
echo "$kind_dir" >> "$GITHUB_PATH"
export PATH="$kind_dir:$PATH"

if kind get clusters | grep -Fxq appflowy-ci; then
  echo 'Refusing to reuse an existing appflowy-ci kind cluster.' >&2
  exit 1
fi
export KUBECONFIG="$RUNNER_TEMP/appflowy-ci.kubeconfig"
echo "KUBECONFIG=$KUBECONFIG" >> "$GITHUB_ENV"
touch "$RUNNER_TEMP/appflowy-kind.created"
kind create cluster --name appflowy-ci --image kindest/node:v1.32.2 \
  --config ci/kind.yaml --kubeconfig "$KUBECONFIG" --wait 180s

# Exercise the chart's actual Ingress resources, including auth/S3 rewrites and
# WebSockets. A hand-written test proxy would hide chart routing regressions.
helm upgrade --install ingress-nginx ingress-nginx \
  --repo https://kubernetes.github.io/ingress-nginx \
  --version 4.12.1 --kube-context kind-appflowy-ci \
  --namespace ingress-nginx --create-namespace \
  --set controller.service.type=NodePort \
  --set controller.service.nodePorts.http=30080 \
  --set controller.admissionWebhooks.enabled=false \
  --set controller.resources.requests.cpu=100m \
  --set controller.resources.requests.memory=128Mi \
  --set controller.resources.limits.memory=256Mi \
  --set-string controller.config.disable-access-log=true \
  --wait --timeout 5m
