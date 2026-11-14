# Charts indépendants HTTPD et Spring Boot — OpenShift / Argo CD

Le même dépôt contient **deux charts autonomes**, chacun avec son propre `templates/deployment.yaml` et ses propres valeurs :

| Répertoire | Application Argo CD INT | Namespace | Responsabilité |
|---|---|---|---|
| `charts/httpd/` | `monapp-int-httpd` | `monapp-front-int` | Reverse proxy, configuration Apache, Route HTTPS, probes TCP |
| `charts/springboot/` | `monapp-int-springboot` | `monapp-back-int` | Application Java, probes Actuator, certificats, AppDynamics, options JVM |

Il n'y a ni chart parent ni boucle commune pour générer les deux Deployments. Une mise à jour des paramètres Spring Boot n'impose aucun rollout HTTPD. Les cycles de synchronisation Argo CD sont indépendants.

## Organisation et fichiers

- `charts/httpd/templates/deployment.yaml` : Deployment exclusivement HTTPD.
- `charts/springboot/templates/deployment.yaml` : Deployment exclusivement Spring Boot.
- `environments/monapp/int/httpd.yaml` et `springboot.yaml` : paramètres INT, même organisation pour REC et PROD.
- `argocd/httpd/monapp-int.yaml` et `argocd/springboot/monapp-int.yaml` : deux Applications, même dépôt Git et chemins de charts différents.
- `examples/springboot-certificates-appdynamics.yaml` : surcharge facultative pour le backend.
- `verify.py` : vérifie les rendus et les liens entre composants pour les trois environnements.

## Installation

Les valeurs fournies sont des exemples : remplacer les images et leurs versions, les domaines et les namespaces par les valeurs de votre plateforme. Fixer les images par digest approuvé en production ; le tag `latest` HTTPD fourni n'est qu'un point de départ.

Les deux namespaces doivent exister. Argo CD doit avoir accès en lecture au dépôt privé `https://github.com/miservers/generic-chart.git`, et son contrôleur doit disposer des droits sur les namespaces cibles. Le projet Argo CD utilisé (`default` dans les exemples) doit autoriser ces destinations et ce dépôt. Le chart ne crée pas les namespaces ni les droits cluster.

Avec l'opérateur OpenShift GitOps, l'équipe plateforme peut déléguer la gestion de chaque namespace avec le label `argocd.argoproj.io/managed-by=openshift-gitops`, selon ses règles d'habilitation. Ce label attribue des permissions au contrôleur.

```sh
# Après préparation des paramètres et commit dans Git :
oc apply -f argocd/springboot/monapp-int.yaml
oc apply -f argocd/httpd/monapp-int.yaml
```

INT et REC sont configurés en auto-sync ; PROD reste en synchronisation manuelle. Attendre que Spring Boot soit Healthy avant de synchroniser HTTPD limite les réponses 503 au premier démarrage. Deux Applications distinctes n'ont pas d'ordre de déploiement garanti entre elles.

## Liaison HTTPD / Spring Boot

Le chart Spring Boot nomme son Service d'après `helm.releaseName`, soit `monapp-int-springboot`. HTTPD renseigne explicitement la cible :

```yaml
# environments/monapp/int/httpd.yaml
backend:
  serviceName: monapp-int-springboot
  namespace: monapp-back-int
  port: 8080
```

Le proxy est généré vers `http://monapp-int-springboot.monapp-back-int.svc.cluster.local:8080/`. Le domaine du cluster est configurable avec `clusterDomain`. Si le nom du Service change (`fullnameOverride` ou nom de release), mettre à jour cette référence côté HTTPD. Si le port du conteneur change, mettre à jour `port` dans Spring Boot ; le chart produit automatiquement `SERVER_PORT`. Le `backend.port` d'HTTPD doit correspondre au `servicePort` de Spring Boot.

Les règles réseau d'entrée sont gérées séparément : HTTPD autorise le routeur, Spring Boot autorise les pods HTTPD sélectionnés par leurs labels ET leur namespace. Adapter `networkPolicy.frontendNamespace` et `networkPolicy.frontendPodLabels` si la release HTTPD change. Les règles sont additives ; une autre NetworkPolicy permissive reste effective. Les sorties ne sont pas filtrées par ces charts. En présence d'un deny egress existant, autoriser DNS, HTTPD vers Spring Boot, puis les flux backend vers DB, RabbitMQ, AppDynamics ou proxy selon les besoins.

## Certificats côté Spring Boot

Les certificats, truststores ou keystores sont montés depuis des Secrets existants dans le namespace backend, sans copier de contenu sensible dans Git :

```yaml
certificates:
  - name: java-truststore
    secretName: monapp-truststore
    mountPath: /etc/java-truststore
javaToolOptions: >-
  -Djavax.net.ssl.trustStore=/etc/java-truststore/truststore.jks
  -Djavax.net.ssl.trustStoreType=JKS
```

Dans cet exemple, le Secret doit contenir la clé fichier `truststore.jks`. Le chart monte le Secret en lecture seule et sélectionne ce truststore pour JSSE. **Monter un PEM seul ne suffit pas à l'importer dans le truststore Java.** L'exemple attend un JKS déjà préparé, composé de certificats de confiance publics. Il remplace la sélection du truststore Java par défaut : inclure les autorités publiques et internes nécessaires.

Le JKS de l'exemple est lu sans mot de passe de vérification d'intégrité ; il ne contient aucune clé privée. Un keystore client avec clé privée/mot de passe demande une configuration applicative distincte, par exemple des propriétés Spring et des références Secret via `env`/`envFrom`. Ne pas passer de mot de passe dans `javaToolOptions` : la JVM peut afficher `JAVA_TOOL_OPTIONS` au démarrage. Le chart ne modifie pas le magasin de confiance OS ni les clients qui utilisent leur propre contexte TLS.

Après rotation d'un certificat, prévoir un rollout Java pour recharger les magasins déjà ouverts. `podAnnotations` permet de versionner explicitement la configuration pour déclencher ce rollout.

## AppDynamics côté Spring Boot

AppDynamics est désactivé par défaut et absent du chart HTTPD. Pour l'activer, adapter les paramètres de `examples/springboot-certificates-appdynamics.yaml`, puis ajouter cette surcharge dans l'Application Argo CD Spring Boot :

```yaml
helm:
  releaseName: monapp-int-springboot
  valueFiles:
    - ../../environments/monapp/int/springboot.yaml
    - ../../examples/springboot-certificates-appdynamics.yaml
```

L'exemple de surcharge contient des placeholders et cible INT : créer une version par environnement avant activation en REC/PROD. Il configure :

1. Un init container copiant l'agent depuis une image interne vers un `emptyDir`.
2. Le montage de ce volume à `/opt/appdynamics` dans le conteneur Java.
3. L'ajout de `-javaagent:/opt/appdynamics/javaagent.jar` aux `javaToolOptions` existantes.
4. Le contrôleur, l'application, le tier et le compte par variables d'environnement.
5. La clé d'accès depuis `appdynamics.accessKeySecret`, sans sa valeur dans Git.
6. Un nom de nœud AppDynamics unique, dérivé du nom du pod.

L'image agent doit contenir `/bin/sh`, `cp`, `chmod` et l'agent complet, avec `javaagent.jar` directement dans `agentSourceDir` (par défaut `/opt/appdynamics`). Elle doit fonctionner avec un UID arbitraire OpenShift. Choisir une version d'agent compatible avec le contrôleur AppDynamics ET le JDK ; aucune compatibilité avec votre contrôleur n'a été testée ici. L'image d'application doit lancer une JVM qui conserve `JAVA_TOOL_OPTIONS`, sans déjà injecter le même agent. Le répertoire agent reste inscriptible pour ses logs et son runtime.

Le Secret d'accès doit exister dans le namespace backend avec la clé `access-key`. La confiance TLS du contrôleur peut demander une configuration propre à l'agent selon sa version : le montage du truststore applicatif ne garantit pas à lui seul la confiance de l'agent. Prévoir aussi les sorties réseau nécessaires vers le contrôleur et les autres services AppDynamics utilisés. Cette configuration concerne l'agent Java APM, pas un Machine Agent, Analytics Agent ou Cluster Agent.

Les paramètres `javaToolOptions` et `appdynamics` sont les points d'entrée dédiés. Le chart rejette leur redéfinition contradictoire dans `env`. Une nouvelle image d'agent déclenche un rollout backend uniquement. Pour la rotation de la clé dans un Secret externe, prévoir un rollout ou un mécanisme de rechargement approprié.

## Autres spécifiques Spring Boot

- `env` et `envFrom` : variables et références ConfigMap/Secret ; ne pas stocker les mots de passe dans les valeurs Git.
- `extraVolumes` et `extraVolumeMounts` : autres configurations ou volumes nécessaires à Java. Les noms `tmp` et `appdynamics` sont réservés.
- `resources`, `startupProbe`, `readinessProbe`, `livenessProbe` : indépendants du frontend.
- `podAnnotations` : annotations de supervision et révision de configuration.
- Les listes Helm sont remplacées en entier par une surcharge : préserver les entrées nécessaires dans `env`.

Actuator doit être présent et les endpoints `/actuator/health/liveness` et `/actuator/health/readiness` accessibles au kubelet sur le port applicatif. Adapter les probes à votre context-path et à votre configuration Spring Security. Ne pas faire dépendre la liveness d'une base de données.

## Hypothèses HTTPD et OpenShift

HTTPD est un reverse proxy : toute l'application, y compris les pages éventuelles, est servie par Spring Boot. Un frontend SPA autonome demanderait une extension du chart HTTPD.

La Route termine TLS en mode edge avec le certificat du routeur, et redirige HTTP vers HTTPS. Le domaine doit être couvert par ce certificat. Le trafic interne est HTTP. Le chart fixe `X-Forwarded-Proto=https` et `X-Forwarded-Port=443` : si la Route est désactivée, le frontal externe doit aussi garantir HTTPS. Une exigence TLS interne nécessite une configuration supplémentaire.

La configuration HTTPD est adaptée à UBI `httpd-24` et son exécutable `/usr/sbin/httpd`. Ne pas remplacer par une image ayant d'autres chemins sans adaptation. La racine du conteneur HTTPD est en lecture seule, avec runtime en `emptyDir`. Les deux charts n'imposent aucun UID/fsGroup ; les images doivent être compatibles avec les attributions OpenShift restricted-v2.

Les logs HTTPD vont sur stdout/stderr. Les probes HTTPD sont TCP, donc vérifient le port, pas la disponibilité fonctionnelle du backend. Une modification de sa ConfigMap déclenche son rollout via checksum.

Aucune affinité de session Spring Boot n'est mise en place : utiliser des applications stateless ou des sessions partagées lorsque plusieurs réplicas sont utilisés. Un cookie du routeur colle à HTTPD et ne garantit pas le même pod Spring Boot. L'IP cliente via X-Forwarded-For nécessite une chaîne de proxys de confiance.

## Migration de l'ancien chart combiné

Le chart `spring-httpd` a été remplacé par les deux charts. Sa dernière version reste dans Git au commit `6de839f2e65ccdf58f465ad2e2fe55495c7b26f7`.

Si l'ancien projet n'a pas encore été déployé, utiliser directement les nouvelles Applications. S'il existe déjà sur un cluster :

1. Avant de synchroniser la nouvelle structure, désactiver l'auto-sync de l'ancienne Application et fixer son `targetRevision` au commit ci-dessus. Si une Application parente la gère, effectuer aussi ces changements dans cette source. Ne pas laisser l'ancienne Application suivre un chemin supprimé sur `main`.
2. Déployer le nouveau Spring Boot, puis valider ses dépendances, probes, certificats et supervision.
3. Pour tester HTTPD en parallèle, utiliser d'abord un hostname temporaire couvert par votre certificat. Ne pas publier deux Routes avec le même hostname. Planifier le transfert du hostname public, par exemple lors d'une courte fenêtre de maintenance.
4. Après bascule et validation, supprimer l'ancienne Application et ses anciennes ressources selon votre procédure. Vérifier la portée du prune/finalizer avant toute suppression. Ne pas changer brutalement le propriétaire Argo CD d'une ressource existante.

Les nouveaux noms incluent `-httpd` et `-springboot`, distincts des anciens `-frontend` et `-backend`. Cette livraison ne réalise aucune migration ni suppression sur un cluster.

## Validation

```sh
helm lint charts/httpd charts/springboot
python3 verify.py  # Helm dans PATH et PyYAML requis
helm template monapp-int-httpd charts/httpd -n monapp-front-int -f environments/monapp/int/httpd.yaml
helm template monapp-int-springboot charts/springboot -n monapp-back-int -f environments/monapp/int/springboot.yaml
```

Depuis un poste connecté au cluster, valider chaque rendu avec `oc apply --dry-run=server -f -`, puis contrôler les rollouts et les logs. Pour vérifier la syntaxe HTTPD dans son image :

```sh
oc exec -n monapp-front-int deployment/monapp-int-httpd -- /usr/sbin/httpd -t -f /etc/custom-httpd/httpd.conf
oc rollout status -n monapp-back-int deployment/monapp-int-springboot
oc logs -n monapp-back-int deployment/monapp-int-springboot -c install-appdynamics
```

Vérifications locales réalisées : lint des deux charts ; rendus INT/REC/PROD ; namespace unique par chart ; correspondance DNS, Service, sélecteurs et règles réseau ; chemins Argo CD ; activation et absence d'AppDynamics ; montage des certificats et références Secret ; rejets des configurations incomplètes ou conflictuelles. Aucun déploiement réel ni démarrage d'agent AppDynamics n'a été effectué ici.

## Références officielles

- [Argo CD et Helm](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/)
- [OpenShift GitOps et permissions](https://docs.redhat.com/en/documentation/red_hat_openshift_gitops/1.21/html/multitenancy/multitenancy-support-in-gitops)
- [NetworkPolicies OpenShift](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/network_security/network-policy)
- [DNS Kubernetes](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)
- [Apache ProxyPass](https://httpd.apache.org/docs/2.4/mod/mod_proxy.html)
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [AppDynamics : agent Java dans les conteneurs](https://docs.appdynamics.com/appd/onprem/24.x/24.6/en/application-monitoring/install-app-server-agents/java-agent/install-the-java-agent/install-the-java-agent-in-containers)
- [AppDynamics : variables d'environnement](https://docs.appdynamics.com/appd/24.x/25.5/en/application-monitoring/install-app-server-agents/java-agent/install-the-java-agent/use-environment-variables-for-java-agent-settings)
- [Oracle : JAVA_TOOL_OPTIONS](https://docs.oracle.com/en/java/javase/24/troubleshoot/environment-variables-and-system-properties.html)
- [Oracle : truststore JSSE](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html)
