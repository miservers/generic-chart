{{- define "springboot.name" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "springboot.selector" -}}
app.kubernetes.io/name: {{ .Values.appName | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/component: springboot
{{- end -}}

{{/* Labels descriptifs : ne jamais utiliser la version du chart dans les selecteurs. */}}
{{- define "springboot.labels" -}}
{{ include "springboot.selector" . }}
helm.sh/chart: {{ print .Chart.Name "-" .Chart.Version | replace "+" "_" | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
{{- end -}}

{{- define "springboot.javaToolOptions" -}}
{{- .Values.javaToolOptions | trim -}}
{{- if .Values.appdynamics.enabled }} -javaagent:/opt/appdynamics/javaagent.jar{{- end -}}
{{- end -}}
