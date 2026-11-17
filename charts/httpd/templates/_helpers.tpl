{{- define "httpd.name" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "httpd.selector" -}}
app.kubernetes.io/name: {{ .Values.appName | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/component: httpd
{{- end -}}

{{/* Host attendu selon la convention Route-namespace.domaine ; aucune lecture API. */}}
{{- define "httpd.routeHost" -}}
{{- if .Values.route.host -}}
{{- .Values.route.host -}}
{{- else -}}
{{ include "httpd.name" . }}-{{ .Release.Namespace }}.apps.{{ required "clusterName requis lorsque route.host est vide" .Values.clusterName }}.{{ .Values.baseDomain }}
{{- end -}}
{{- end -}}

{{/* Convention backend : Route <app>-<env>-app, namespace <app>-<env>. */}}
{{- define "httpd.backendHost" -}}
{{- if .Values.backendRoute.host -}}
{{- .Values.backendRoute.host -}}
{{- else -}}
{{- $env := required "environment requis lorsque backendRoute.host est vide" .Values.environment -}}
{{ .Values.appName }}-{{ $env }}-app-{{ .Values.appName }}-{{ $env }}.apps.{{ required "clusterName requis lorsque backendRoute.host est vide" .Values.clusterName }}.{{ .Values.baseDomain }}
{{- end -}}
{{- end -}}

{{/* Labels descriptifs : ne jamais utiliser la version du chart dans les selecteurs. */}}
{{- define "httpd.labels" -}}
{{ include "httpd.selector" . }}
helm.sh/chart: {{ print .Chart.Name "-" .Chart.Version | replace "+" "_" | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
{{- end -}}
