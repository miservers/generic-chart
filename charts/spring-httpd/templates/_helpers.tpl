{{- define "app.name" -}}
{{-  .Release.Name | trunc 54 | trimSuffix "-" -}}
{{- end -}}
{{- define "app.selector" -}}
app.kubernetes.io/name: {{ .root.Values.appName | quote }}
app.kubernetes.io/instance: {{ .root.Release.Name | quote }}
app.kubernetes.io/component: {{ .component | quote }}
{{- end -}}
{{- define "app.backendURL" -}}
http://{{ include "app.name" . }}-backend.{{ .Values.namespaces.backend }}.svc.{{ .Values.clusterDomain }}:{{ .Values.backend.servicePort }}/
{{- end -}}
