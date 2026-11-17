# Chart Spring Boot

Deployment Java indépendant du frontend, avec Service, Route facultative, ServiceAccount et NetworkPolicy d’entrée. Les Secrets et l’image applicative doivent déjà exister.

## Valeurs minimales

```yaml
appName: application
image: registry.example.com/equipe/application:1.0.0
replicas: 2
session: enabled
route:
  host: ""
  cookieName: APPLICATION_BACK
```

Sans host explicite, OpenShift attribue celui de la Route. Pour utiliser le chart sans Route :

```yaml
route:
  enabled: false
```

Le cookie n’est alors pas obligatoire. Avec une Route active, `session: disabled` omet le nom de cookie et désactive l’affinité de cette Route. Le cookie Java reste géré par l’application.

| Valeur | Usage |
|---|---|
| `appName`, `image` | Requis, aucune valeur métier par défaut |
| `fullnameOverride` | Nom explicite facultatif des ressources |
| `replicas`, `port`, `servicePort`, `resources` | Pods, port Java, port du Service et ressources |
| `env`, `envFrom` | Variables ou références de configuration applicative |
| `javaToolOptions` | Options JVM ; l’agent AppDynamics est ajouté si activé |
| `startupProbe`, `readinessProbe`, `livenessProbe` | Probes Actuator configurables |
| `certificates` | Secrets montés en lecture seule |
| `extraVolumes`, `extraVolumeMounts` | Volumes applicatifs facultatifs |
| `podAnnotations` | Annotations du pod |
| `appdynamics` | Injection optionnelle de l’agent Java |
| `route`, `session` | Route edge et affinité |
| `networkPolicy.routerNamespaceSelector` | Routeurs autorisés en entrée |

`clusterName` et `environment` peuvent être transmis par les ApplicationSets communs ; le chart backend ne s’en sert pas pour calculer un host. `networkPolicy.egress`, s’il provient du fichier réseau commun, est également un contexte HTTPD : aucune policy Egress backend n’est rendue.

Le schéma rejette les clés inconnues et les types incohérents. `SERVER_PORT` et `JAVA_TOOL_OPTIONS` sont gérés par le chart. Les variables `APPDYNAMICS_*` sont réservées lorsque l’agent est activé. Les volumes et chemins dupliqués, ainsi que les références de montage absentes, sont refusés au rendu.

Les listes Helm sont remplacées intégralement : si vous surchargez `env`, conserver les variables nécessaires. Pour changer le type d’un Probe, supprimer l’ancien handler par une valeur `null` dans la surcharge.

## Certificats

```yaml
certificates:
  - name: java-truststore
    secretName: application-truststore
    mountPath: /etc/java-truststore
javaToolOptions: >-
  -Djavax.net.ssl.trustStore=/etc/java-truststore/truststore.jks
  -Djavax.net.ssl.trustStoreType=JKS
```

Monter un PEM n’importe pas automatiquement une CA dans Java. Le Secret de cet exemple contient un JKS préparé avec les CA publiques nécessaires, sans clé privée. Le truststore remplace le défaut pour les clients JSSE concernés ; il ne modifie pas la confiance OS ou celle de clients TLS indépendants. Ne pas stocker de mot de passe dans `JAVA_TOOL_OPTIONS`, qui peut être journalisé. Prévoir un rollout lors de la rotation.

## AppDynamics

[Exemple complet](../../examples/springboot-certificates-appdynamics.yaml) à charger après les valeurs de l’application. Les paramètres propres au contrôleur, à l’application, au tier et au compte sont requis si `enabled=true`. La clé du compte est référencée par Secret, jamais écrite dans les valeurs.

L’image d’agent doit contenir `/bin/sh`, `cp`, `chmod` et l’agent complet avec `javaagent.jar` dans `agentSourceDir`, et accepter l’UID OpenShift. L’init container copie l’agent vers un `emptyDir`, puis Java utilise `-javaagent`. Le nom du pod identifie le nœud AppDynamics. Vérifier la compatibilité JDK/agent/contrôleur et la confiance TLS de l’agent ; après rotation du Secret d’accès, effectuer un rollout.

## Probes et sécurité

Les probes supposent Actuator sur le port applicatif sans authentification pour le kubelet. Adapter les chemins au context-path. Une liveness ne devrait pas dépendre de la disponibilité d’une base externe.

Le ServiceAccount n’est pas monté dans le pod. Le conteneur s’exécute sans privilèges supplémentaires et sans UID fixe ; l’image doit être compatible avec la SCC de votre cluster. Le chart ne crée ni base de données, ni stockage persistant, ni réplication des sessions Java.

## Références

- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [AppDynamics : agent Java dans des conteneurs](https://docs.appdynamics.com/appd/onprem/24.x/24.6/en/application-monitoring/install-app-server-agents/java-agent/install-the-java-agent/install-the-java-agent-in-containers)
- [JSSE et truststores](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html)
