{{- define "app.name" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "app.selector" -}}
app.kubernetes.io/name: {{ .Values.appName | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/component: httpd
{{- end -}}

{{/* Host attendu selon la convention Route-namespace.domaine ; aucune lecture API. */}}
{{- define "app.routeHost" -}}
{{- if .Values.route.host -}}
{{- .Values.route.host -}}
{{- else -}}
{{ include "app.name" . }}-{{ .Release.Namespace }}.apps.{{ required "clusterName requis lorsque route.host est vide" .Values.clusterName }}.{{ .Values.baseDomain }}
{{- end -}}
{{- end -}}

{{/* Convention backend : Route <app>-<env>-app, namespace <app>-<env>. */}}
{{- define "app.backendHost" -}}
{{- if .Values.backendRoute.host -}}
{{- .Values.backendRoute.host -}}
{{- else -}}
{{- $env := required "environment requis lorsque backendRoute.host est vide" .Values.environment -}}
{{ .Values.appName }}-{{ $env }}-app-{{ .Values.appName }}-{{ $env }}.apps.{{ required "clusterName requis lorsque backendRoute.host est vide" .Values.clusterName }}.{{ .Values.baseDomain }}
{{- end -}}
{{- end -}}
