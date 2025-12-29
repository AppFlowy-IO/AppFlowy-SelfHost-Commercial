{{/*
Expand the name of the chart.
*/}}
{{- define "appflowy.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "appflowy.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "appflowy.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "appflowy.labels" -}}
helm.sh/chart: {{ include "appflowy.chart" . }}
{{ include "appflowy.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.global.labels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "appflowy.selectorLabels" -}}
app.kubernetes.io/name: {{ include "appflowy.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Component labels - for subcharts
*/}}
{{- define "appflowy.componentLabels" -}}
{{ include "appflowy.labels" . }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "appflowy.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "appflowy.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
=============================================================================
Database Connection Helpers
=============================================================================
*/}}

{{/*
PostgreSQL host
*/}}
{{- define "appflowy.postgresql.host" -}}
{{- if .Values.global.postgresql.host }}
{{- .Values.global.postgresql.host }}
{{- else if .Values.postgresql.enabled }}
{{- printf "%s-postgresql" .Release.Name }}
{{- else }}
{{- fail "PostgreSQL host must be specified when postgresql.enabled is false" }}
{{- end }}
{{- end }}

{{/*
PostgreSQL port
*/}}
{{- define "appflowy.postgresql.port" -}}
{{- .Values.global.postgresql.port | default 5432 }}
{{- end }}

{{/*
PostgreSQL database
*/}}
{{- define "appflowy.postgresql.database" -}}
{{- .Values.global.postgresql.database | default "postgres" }}
{{- end }}

{{/*
PostgreSQL username
*/}}
{{- define "appflowy.postgresql.username" -}}
{{- .Values.global.postgresql.username | default "postgres" }}
{{- end }}

{{/*
PostgreSQL password secret name
*/}}
{{- define "appflowy.postgresql.secretName" -}}
{{- if .Values.global.postgresql.existingSecret }}
{{- .Values.global.postgresql.existingSecret }}
{{- else if .Values.postgresql.enabled }}
{{- printf "%s-postgresql" .Release.Name }}
{{- else }}
{{- printf "%s-postgresql-secret" (include "appflowy.fullname" .) }}
{{- end }}
{{- end }}

{{/*
PostgreSQL password secret key
*/}}
{{- define "appflowy.postgresql.secretKey" -}}
{{- if .Values.global.postgresql.existingSecret }}
{{- .Values.global.postgresql.secretKeys.password | default "postgres-password" }}
{{- else }}
{{- "postgres-password" }}
{{- end }}
{{- end }}

{{/*
PostgreSQL connection URL (for environment variable)
*/}}
{{- define "appflowy.postgresql.url" -}}
postgres://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@{{ include "appflowy.postgresql.host" . }}:{{ include "appflowy.postgresql.port" . }}/{{ include "appflowy.postgresql.database" . }}
{{- end }}

{{/*
PostgreSQL connection URL for GoTrue (with auth schema)
*/}}
{{- define "appflowy.postgresql.gotrueUrl" -}}
postgres://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@{{ include "appflowy.postgresql.host" . }}:{{ include "appflowy.postgresql.port" . }}/{{ include "appflowy.postgresql.database" . }}?search_path=auth
{{- end }}

{{/*
=============================================================================
Redis Connection Helpers
=============================================================================
*/}}

{{/*
Redis host
*/}}
{{- define "appflowy.redis.host" -}}
{{- if .Values.global.redis.host }}
{{- .Values.global.redis.host }}
{{- else if .Values.redis.enabled }}
{{- printf "%s-redis-master" .Release.Name }}
{{- else }}
{{- fail "Redis host must be specified when redis.enabled is false" }}
{{- end }}
{{- end }}

{{/*
Redis port
*/}}
{{- define "appflowy.redis.port" -}}
{{- .Values.global.redis.port | default 6379 }}
{{- end }}

{{/*
Redis URL
*/}}
{{- define "appflowy.redis.url" -}}
{{- if eq (include "appflowy.redis.authEnabled" .) "true" -}}
redis://:$(REDIS_PASSWORD)@{{ include "appflowy.redis.host" . }}:{{ include "appflowy.redis.port" . }}
{{- else -}}
redis://{{ include "appflowy.redis.host" . }}:{{ include "appflowy.redis.port" . }}
{{- end }}
{{- end }}

{{/*
Redis password auth enabled
*/}}
{{- define "appflowy.redis.authEnabled" -}}
{{- if .Values.global.redis.existingSecret -}}
true
{{- else if and .Values.redis.enabled .Values.redis.auth.enabled -}}
true
{{- else if .Values.global.redis.password -}}
true
{{- else -}}
false
{{- end }}
{{- end }}

{{/*
Redis password secret name
*/}}
{{- define "appflowy.redis.secretName" -}}
{{- if .Values.global.redis.existingSecret -}}
{{- .Values.global.redis.existingSecret -}}
{{- else if and .Values.redis.enabled .Values.redis.auth.enabled -}}
{{- if .Values.redis.auth.existingSecret -}}
{{- .Values.redis.auth.existingSecret -}}
{{- else -}}
{{- printf "%s-redis" .Release.Name -}}
{{- end -}}
{{- else -}}
{{- printf "%s-redis-secret" (include "appflowy.fullname" .) -}}
{{- end }}
{{- end }}

{{/*
Redis password secret key
*/}}
{{- define "appflowy.redis.secretKey" -}}
{{- if .Values.global.redis.existingSecret -}}
{{- .Values.global.redis.secretKeys.password | default "redis-password" -}}
{{- else if and .Values.redis.enabled .Values.redis.auth.enabled -}}
{{- if .Values.redis.auth.existingSecret -}}
{{- .Values.redis.auth.existingSecretPasswordKey | default "redis-password" -}}
{{- else -}}
redis-password
{{- end -}}
{{- else -}}
{{- .Values.global.redis.secretKeys.password | default "redis-password" -}}
{{- end }}
{{- end }}

{{/*
=============================================================================
S3/MinIO Connection Helpers
=============================================================================
*/}}

{{/*
S3/MinIO host
*/}}
{{- define "appflowy.s3.host" -}}
{{- if .Values.global.s3.endpoint }}
{{- .Values.global.s3.endpoint }}
{{- else if .Values.minio.enabled }}
{{- printf "%s-minio" .Release.Name }}
{{- else }}
{{- fail "S3 endpoint must be specified when minio.enabled is false" }}
{{- end }}
{{- end }}

{{/*
S3/MinIO endpoint URL
*/}}
{{- define "appflowy.s3.endpoint" -}}
http://{{ include "appflowy.s3.host" . }}:{{ .Values.global.s3.port | default 9000 }}
{{- end }}

{{/*
S3/MinIO bucket
*/}}
{{- define "appflowy.s3.bucket" -}}
{{- .Values.global.s3.bucket | default "appflowy" }}
{{- end }}

{{/*
S3/MinIO region
*/}}
{{- define "appflowy.s3.region" -}}
{{- .Values.global.s3.region | default "us-east-1" }}
{{- end }}

{{/*
S3/MinIO secret name
*/}}
{{- define "appflowy.s3.secretName" -}}
{{- if .Values.global.s3.existingSecret }}
{{- .Values.global.s3.existingSecret }}
{{- else if .Values.minio.enabled }}
{{- printf "%s-minio" .Release.Name }}
{{- else }}
{{- printf "%s-s3-secret" (include "appflowy.fullname" .) }}
{{- end }}
{{- end }}

{{/*
=============================================================================
JWT Helpers
=============================================================================
*/}}

{{/*
JWT secret name
*/}}
{{- define "appflowy.jwt.secretName" -}}
{{- if .Values.global.jwt.existingSecret }}
{{- .Values.global.jwt.existingSecret }}
{{- else }}
{{- printf "%s-jwt-secret" (include "appflowy.fullname" .) }}
{{- end }}
{{- end }}

{{/*
JWT secret key
*/}}
{{- define "appflowy.jwt.secretKey" -}}
{{- .Values.global.jwt.secretKey | default "jwt-secret" }}
{{- end }}

{{/*
=============================================================================
URL Helpers
=============================================================================
*/}}

{{/*
Base URL
*/}}
{{- define "appflowy.baseUrl" -}}
{{ .Values.global.scheme }}://{{ .Values.global.domain }}
{{- end }}

{{/*
WebSocket URL
*/}}
{{- define "appflowy.websocketUrl" -}}
{{ .Values.global.wsScheme }}://{{ .Values.global.domain }}/ws/v2
{{- end }}

{{/*
GoTrue external URL
*/}}
{{- define "appflowy.gotrue.externalUrl" -}}
{{ include "appflowy.baseUrl" . }}/gotrue
{{- end }}

{{/*
GoTrue internal URL (service-to-service)
*/}}
{{- define "appflowy.gotrue.internalUrl" -}}
http://{{ include "appflowy.fullname" . }}-gotrue:{{ .Values.gotrue.service.port | default 9999 }}
{{- end }}

{{/*
AppFlowy Cloud internal URL
*/}}
{{- define "appflowy.cloud.internalUrl" -}}
http://{{ include "appflowy.fullname" . }}-cloud:{{ index .Values "appflowy-cloud" "service" "port" | default 8000 }}
{{- end }}

{{/*
AppFlowy AI internal URL
*/}}
{{- define "appflowy.ai.internalUrl" -}}
http://{{ include "appflowy.fullname" . }}-ai:{{ index .Values "appflowy-ai" "service" "port" | default 5001 }}
{{- end }}

{{/*
=============================================================================
Service Name Helpers
=============================================================================
*/}}

{{- define "appflowy.gotrue.fullname" -}}
{{- printf "%s-gotrue" (include "appflowy.fullname" .) }}
{{- end }}

{{- define "appflowy.cloud.fullname" -}}
{{- printf "%s-cloud" (include "appflowy.fullname" .) }}
{{- end }}

{{- define "appflowy.worker.fullname" -}}
{{- printf "%s-worker" (include "appflowy.fullname" .) }}
{{- end }}

{{- define "appflowy.web.fullname" -}}
{{- printf "%s-web" (include "appflowy.fullname" .) }}
{{- end }}

{{- define "appflowy.admin.fullname" -}}
{{- printf "%s-admin" (include "appflowy.fullname" .) }}
{{- end }}

{{- define "appflowy.ai.fullname" -}}
{{- printf "%s-ai" (include "appflowy.fullname" .) }}
{{- end }}

{{/*
=============================================================================
Image Helpers
=============================================================================
*/}}

{{/*
Return the proper image name
*/}}
{{- define "appflowy.image" -}}
{{- $registryName := .Values.global.imageRegistry -}}
{{- $repositoryName := .image.repository -}}
{{- $tag := .image.tag | default "latest" -}}
{{- if $registryName }}
{{- printf "%s/%s:%s" $registryName $repositoryName $tag -}}
{{- else }}
{{- printf "%s:%s" $repositoryName $tag -}}
{{- end }}
{{- end }}

{{/*
Return image pull secrets
*/}}
{{- define "appflowy.imagePullSecrets" -}}
{{- if .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- range .Values.global.imagePullSecrets }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end }}
