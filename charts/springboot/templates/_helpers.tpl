{{- define "app.name" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "app.selector" -}}
app.kubernetes.io/name: {{ .Values.appName | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/component: springboot
{{- end -}}
