{{/*
Expand the name of the chart.
*/}}
{{- define "mintkey.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "mintkey.fullname" -}}
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
Create chart label value (name + version).
*/}}
{{- define "mintkey.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "mintkey.labels" -}}
helm.sh/chart: {{ include "mintkey.chart" . }}
{{ include "mintkey.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — the minimal stable subset used in matchLabels.
*/}}
{{- define "mintkey.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mintkey.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Build a full image reference from a component image value.

Rules (evaluated in order):
  1. If the image string contains "@" it is already a pinned digest reference —
     return it unchanged (digest images must not be re-prefixed).
  2. If the image string contains "/" it is already a fully-qualified registry path —
     return it with the global imageTag appended (tag separator ":").
  3. Otherwise prepend .Values.global.imageRegistry and append .Values.global.imageTag.

Usage (pass a dict with "image" and "root" keys):
  {{ include "mintkey.image" (dict "image" .Values.adminApi.image "root" .) }}
*/}}
{{- define "mintkey.image" -}}
{{- $image := .image -}}
{{- $root := .root -}}
{{- if contains "@" $image -}}
{{- $image -}}
{{- else if contains "/" $image -}}
{{- printf "%s:%s" $image $root.Values.global.imageTag -}}
{{- else -}}
{{- printf "%s/%s:%s" $root.Values.global.imageRegistry $image $root.Values.global.imageTag -}}
{{- end -}}
{{- end }}

{{/*
Service account name — defaults to "default".
Override by setting .Values.serviceAccountName.
*/}}
{{- define "mintkey.serviceAccountName" -}}
{{- default "default" .Values.serviceAccountName }}
{{- end }}

{{/*
imagePullSecrets block — emits the block only when .Values.global.imagePullSecret is non-empty.

Usage:
  {{ include "mintkey.imagePullSecrets" . | nindent 6 }}
*/}}
{{- define "mintkey.imagePullSecrets" -}}
{{- if .Values.global.imagePullSecret -}}
imagePullSecrets:
  - name: {{ .Values.global.imagePullSecret }}
{{- end -}}
{{- end }}

{{/*
Internal Postgres DSN — used when database.mode=chart.
Format: postgresql://mintkey:mintkey@<fullname>-postgres:5432/mintkey
*/}}
{{- define "mintkey.dbUrl" -}}
{{- printf "postgresql://mintkey:mintkey@%s-postgres:5432/mintkey" (include "mintkey.fullname" .) -}}
{{- end }}

{{/*
Extra environment variables — GitOps env-injection hook. Merges
.Values.global.extraEnv (applied to every Go service that calls this helper)
with a per-service extraEnv list (e.g. .Values.broker.extraEnv), in that
order, so a values override can add vars (e.g. OTEL_EXPORTER_OTLP_ENDPOINT)
without a code or template change. Each entry is a normal env-var object:
{name, value} or {name, valueFrom: {...}}. Kubernetes does not de-dupe env
entries by name — avoid setting the same name in both global and
service-level extraEnv.

Usage (append inside a container's env: list, after the hardcoded entries):
  {{- include "mintkey.extraEnv" (dict "root" . "service" .Values.broker) | nindent 12 }}
*/}}
{{- define "mintkey.extraEnv" -}}
{{- $root := .root -}}
{{- $service := .service -}}
{{- range (default (list) $root.Values.global.extraEnv) }}
- name: {{ .name }}
  {{- if hasKey . "value" }}
  value: {{ .value | quote }}
  {{- else if hasKey . "valueFrom" }}
  valueFrom:
    {{- toYaml .valueFrom | nindent 4 }}
  {{- end }}
{{- end }}
{{- range (default (list) $service.extraEnv) }}
- name: {{ .name }}
  {{- if hasKey . "value" }}
  value: {{ .value | quote }}
  {{- else if hasKey . "valueFrom" }}
  valueFrom:
    {{- toYaml .valueFrom | nindent 4 }}
  {{- end }}
{{- end }}
{{- end }}

{{/*
Ensure a host value is non-empty for ingress rules.
Fails template rendering with a descriptive error when the host is blank.

Usage:
  host: {{ include "mintkey.publicUrl" (dict "host" .Values.ingress.adminApi.host "service" "adminApi") }}
*/}}
{{- define "mintkey.publicUrl" -}}
{{- if .host -}}
{{- .host -}}
{{- else -}}
{{- fail (printf "ingress.%s.host must be set when ingress is enabled" .service) -}}
{{- end -}}
{{- end }}
