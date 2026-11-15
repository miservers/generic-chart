# HTTPD + Spring Boot : deux charts et affinité par Route OpenShift

Le même dépôt contient deux charts autonomes et deux Applications Argo CD par application métier et environnement.

| Chart | Workload | Namespace INT | Responsabilité |
|---|---|---|---|
| `charts/httpd` | Deployment, 2 pods | `monapp-front-int` | Route publique, reverse proxy HTTPS vers la Route backend |
| `charts/springboot` | Deployment, 2 pods | `monapp-back-int` | Route backend avec cookie d'affinité, Java, certificats et AppDynamics optionnel |

**Flux : navigateur → Route frontend → HTTPD → Route backend → pod Spring Boot.**

Les backends sont de nouveau des Deployments classiques. HTTPD ne connaît ni les IP ni les noms individuels des pods. Il n'y a plus de StatefulSet, Service headless, BalancerMember ou cookie d'affinité fabriqué par Apache.

## Répertoires

- `charts/httpd/templates/deployment.yaml` : Deployment HTTPD.
- `charts/springboot/templates/deployment.yaml` : Deployment Spring Boot.
- `environments/monapp/{int,rec,prod}/httpd.yaml` et `springboot.yaml` : paramètres par composant, avec 2 réplicas chacun.
- `argocd/httpd/monapp-{int,rec,prod}.yaml` et `argocd/springboot/monapp-{int,rec,prod}.yaml` : Applications indépendantes.
- `examples/springboot-certificates-appdynamics.yaml` : surcharge Java facultative.
- `verify.py` : vérification des rendus Helm et des liens entre charts.
- `tests/route_proxy_smoke.py` : test local d'Apache vers un endpoint HTTPS simulé.

## Cookies et bascule

Les deux Routes portent les annotations suivantes avec des noms de cookies distincts :

```yaml
# Route frontend INT
router.openshift.io/cookie_name: MONAPP_INT_FRONT
haproxy.router.openshift.io/disable_cookies: 'false'

# Route backend INT
router.openshift.io/cookie_name: MONAPP_INT_BACK
haproxy.router.openshift.io/disable_cookies: 'false'
```

Le navigateur reçoit le cookie de la Route backend dans la réponse relayée par HTTPD, puis le renvoie à l'URL publique. HTTPD transmet le header `Cookie` vers la Route backend. Cela fonctionne avec les deux HTTPD : c'est le routeur backend qui interprète le cookie et sélectionne le pod Spring Boot. Le cookie de session Java, par exemple `JSESSIONID`, reste distinct et n'est pas remplacé par le cookie du routeur.

Le client reste sur le même backend tant qu'il est disponible. Si le pod disparaît ou n'est plus disponible dans les endpoints, le routeur peut sélectionner un autre pod et actualiser l'affinité. **La session Java en mémoire n'est pas répliquée** : une reconnexion utilisateur peut être nécessaire. La détection et la mise à jour des endpoints prennent du temps ; une requête en cours peut échouer. Un redémarrage trop bref pour être observé peut ramener au même pod, mais sa session mémoire est tout de même perdue. Ne pas promettre le rejeu d'un POST non idempotent.

Les cookies du routeur sont normalement host-only : le navigateur les associe à l'URL publique qu'il consulte, même s'ils ont été créés sur le saut backend. `ProxyPassReverseCookieDomain` réécrit en complément un Domain explicitement égal au hostname backend. Si l'application impose un autre domaine parent ou un autre chemin de cookie, adapter cette règle et la configuration de l'application. Chaque application/environnement doit avoir des noms de cookies distincts.

## Valeurs principales

```yaml
# environments/monapp/int/httpd.yaml
replicas: 2
route:
  host: monapp-int.apps.example.com
  cookieName: MONAPP_INT_FRONT
backendRoute:
  host: monapp-back-int.apps-internal.example.com

# environments/monapp/int/springboot.yaml
replicas: 2
image: registry.example.com/equipe/monapp:1.0.0
route:
  host: monapp-back-int.apps-internal.example.com
  cookieName: MONAPP_INT_BACK
  labels:
    ingress-scope: internal
```

Les deux valeurs `httpd.backendRoute.host` et `springboot.route.host` doivent être identiques. Les noms de Route frontend et backend doivent être différents, sinon HTTPD bouclerait vers lui-même. Les hosts sont explicites pour conserver l'indépendance des Applications Argo CD.

La cible est toujours `https://HOST_BACKEND/`, port 443. HTTPD utilise `ProxyPreserveHost Off` : le Host et le SNI correspondent à la Route backend, ce qui permet son routage et la vérification TLS. Il définit `X-Forwarded-Host` sur le domaine public, `X-Forwarded-Proto=https` et `X-Forwarded-Port=443` pour Spring Boot, et supprime un éventuel header `Forwarded` reçu. `ProxyAddHeaders Off` évite d'ajouter une autre valeur de Host transmis. Spring Boot conserve `SERVER_FORWARD_HEADERS_STRATEGY=framework` dans les valeurs par défaut.

`ProxyPassReverse` traduit les redirections HTTP vers le domaine public. `ServerName https://HOST_PUBLIC:443` et `UseCanonicalName On` évitent de produire des redirections en HTTP à cause du saut edge → HTTPD. Apache peut avertir au démarrage qu'un ServerName HTTPS est associé à un listener HTTP : ici TLS entrant est terminé par le routeur, c'est volontaire. Aucun chiffrement entrant n'est activé dans HTTPD.

L'annotation `haproxy.router.openshift.io/set-forwarded-headers` vaut `replace` côté frontend et `never` côté backend, afin de ne pas reconstruire la chaîne Forwarded/X-Forwarded-For sur le second saut. Cette annotation n'est pas une garantie générale sur tous les headers : vérifier le comportement de votre IngressController, notamment `X-Forwarded-Host`, avec l'application. Ne pas utiliser une adresse fournie dans X-Forwarded-For comme preuve d'identité sans politique de confiance adaptée.

## TLS de la Route backend

Les deux Routes utilisent une terminaison edge avec redirection HTTP → HTTPS. HTTPD vérifie le certificat du routeur backend : `SSLProxyVerify require`, nom DNS et expiration contrôlés. La résolution DNS de `backendRoute.host` doit pointer vers le routeur joignable depuis les pods HTTPD, et le certificat doit couvrir ce host.

Par défaut, HTTPD utilise le bundle système Red Hat `/etc/pki/tls/certs/ca-bundle.crt`. Si le routeur utilise une CA privée, créer un Secret dans le **namespace frontend**, puis configurer :

```yaml
backendRoute:
  host: monapp-back-int.apps-internal.example.com
  caSecretName: internal-router-ca
  caSecretKey: ca.crt
```

Le Secret doit contenir la chaîne CA PEM de confiance dans la clé indiquée. Elle est montée en lecture seule sous `/etc/backend-route-ca/ca.crt`. Cette CA concerne HTTPD vers le routeur ; elle est indépendante des truststores Java du backend. Ne pas désactiver la vérification TLS pour contourner un problème de certificat. Après rotation de cette CA, prévoir un rollout HTTPD pour recharger la confiance. Les changements de ConfigMap HTTPD déclenchent déjà son rollout via checksum.

Le trafic routeur → HTTPD et routeur → Spring Boot reste HTTP avec edge. Une exigence TLS jusqu'aux pods demanderait une variante reencrypt.

## Route backend interne et réseau

**Le label `ingress-scope: internal` ne rend pas une Route privée à lui seul.** Il est fourni comme convention à adapter. L'équipe plateforme doit avoir un IngressController interne qui sélectionne ce label, et exclure ces Routes des IngressControllers publics. Elle doit aussi fournir le DNS et un certificat adaptés. Les charts ne créent ni ne modifient les IngressControllers du cluster.

Un routeur interne limite l'exposition réseau, mais ne signifie pas automatiquement « accessible uniquement par HTTPD ». Si le contournement du frontal doit être interdit pour les autres clients internes, prévoir les restrictions d'accès réseau / ACL du routeur adaptées à la plateforme. Une Route backend admise par le routeur public peut exposer directement Spring Boot, y compris ses endpoints techniques. L'interdiction `/actuator` dans HTTPD ne protège pas une requête qui contourne HTTPD.

Les NetworkPolicies d'entrée des deux charts autorisent désormais les pods du routeur, sélectionnés par `networkPolicy.routerNamespaceSelector`, sur le port applicatif. Le sélecteur par défaut utilise `network.openshift.io/policy-group: ingress` et un `podSelector: {}`. Adapter ce sélecteur si votre routeur interne utilise une autre topologie. La policy backend n'autorise plus directement HTTPD. Les policies sont additives : une règle préexistante permissive reste effective.

Les charts ne filtrent pas les sorties. Avec un deny egress existant, autoriser DNS et HTTPD → adresse/port HTTPS du routeur, selon le chemin réel (Service, VIP, SNAT, hostNetwork), ainsi que les sorties Java requises vers DB, RabbitMQ, AppDynamics ou proxy. La policy backend voit la provenance du routeur, pas celle du pod HTTPD d'origine ; elle ne suffit donc pas à prouver que le client est passé par le frontal.

Pour vérifier l'admission des Routes :

```sh
oc get route -n monapp-front-int monapp-int-httpd -o yaml
oc get route -n monapp-back-int monapp-int-springboot -o yaml
# Contrôler status.ingress : routerName, conditions Admitted et hostname.
```

## ApplicationSet app1 / app2 — INT et REC

`argocd/applicationsets/applications-metier.yaml` génère huit Applications pour un seul cluster sélectionné. Chaque application métier déclare `envs: [int, rec]` et `components: [httpd, springboot]`. `elementsYaml` développe ces tableaux, puis Matrix associe le cluster.

| Application | Namespace |
|---|---|
| app1-int-app | app1-int |
| app1-int-prez | app1-intfr |
| app1-rec-app | app1-rec |
| app1-rec-prez | app1-recfr |
| app2-int-app | app2-int |
| app2-int-prez | app2-intfr |
| app2-rec-app | app2-rec |
| app2-rec-prez | app2-recfr |

Les huit fichiers `environments/{app1,app2}/{int,rec}/{httpd,springboot}.yaml` sont fournis. Leurs images et domaines `example.com` sont des exemples à adapter ; les hosts frontend/backend sont explicitement renseignés, conformément à la version actuelle des charts. L'ApplicationSet ne découvre pas le domaine Ingress. Les noms Helm de release suivent les noms des Applications (`-app` et `-prez`).

Faire gérer le répertoire `argocd/applicationsets` par votre Application parente App of Apps, ou créer cet ApplicationSet depuis Argo CD. L'Application parente doit être autorisée à gérer ce type de ressource dans `openshift-gitops`. Le contrôleur ApplicationSet doit être installé et autorisé à traiter cet objet.

Le Secret représentant **un seul cluster cible dans Argo CD** doit porter `deploy-applications-metier: "true"`. Aucun cluster sélectionné ne produit d'Application ; plusieurs clusters créeraient des noms en collision. Le cluster local doit également avoir un Secret de cluster pour cette sélection par label. Les namespaces doivent exister et être accessibles au contrôleur ; l'AppProject doit autoriser le dépôt et les destinations.

La synchronisation des huit Applications est manuelle. Les anciens exemples individuels `monapp` sont conservés et indépendants ; ne pas les importer si vous ne voulez déployer que app1/app2. Pour une migration d'Applications existantes vers ApplicationSet, contrôler leurs noms et propriétaires avant activation.

Références : [List / elementsYaml](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Generators-List/) et [Matrix](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Generators-Matrix/).

## Installation Argo CD

1. Adapter les domaines, images et namespaces des fichiers d'environnement. Fixer les images par digest approuvé en production ; `latest` HTTPD reste une valeur illustrative.
2. Faire préparer les deux namespaces, les droits du contrôleur Argo CD et la Route interne par l'équipe plateforme. Aucun namespace ou droit cluster n'est créé par ces charts.
3. Configurer l'accès en lecture au dépôt privé `https://github.com/miservers/generic-chart.git`. Choisir un AppProject autorisant ce dépôt et les destinations (`default` dans les exemples).
4. Committer les paramètres, puis créer les Applications :

```sh
oc apply -f argocd/springboot/monapp-int.yaml
oc apply -f argocd/httpd/monapp-int.yaml
```

INT et REC utilisent auto-sync ; PROD reste manuel. Les Applications ont des cycles indépendants : vérifier la disponibilité du backend et l'admission de sa Route avant de synchroniser HTTPD évite les erreurs initiales. Avec OpenShift GitOps Operator, la délégation via `argocd.argoproj.io/managed-by=openshift-gitops` relève de l'équipe plateforme et attribue des droits au contrôleur.

Pour une nouvelle application, dupliquer les fichiers d'environnement et les deux Applications, changer `appName`, les releaseNames, namespaces, hosts, noms de cookies et images. Conserver les chemins `charts/httpd` et `charts/springboot`. Garder les labels de sélection stables lors des mises à jour des Deployments.

## Spécifiques Spring Boot conservés

- `certificates` monte des Secrets existants dans le namespace backend, en lecture seule.
- `javaToolOptions` configure les options JVM.
- `appdynamics` injecte facultativement l'agent Java par init container et référence une clé d'accès dans un Secret.
- `env`, `envFrom`, `extraVolumes`, `extraVolumeMounts`, `podAnnotations` et les ressources/probes restent propres au backend.

Exemple de truststore :

```yaml
certificates:
  - name: java-truststore
    secretName: monapp-truststore
    mountPath: /etc/java-truststore
javaToolOptions: >-
  -Djavax.net.ssl.trustStore=/etc/java-truststore/truststore.jks
  -Djavax.net.ssl.trustStoreType=JKS
```

Le Secret contient `truststore.jks`, préparé avec toutes les CA nécessaires. Monter un PEM ne l'importe pas automatiquement dans Java. Ce JKS contient uniquement des certificats publics et est lu sans mot de passe de vérification d'intégrité. Une clé privée / un keystore client demande une configuration applicative et des références Secret distinctes. Ne pas mettre de mot de passe dans `JAVA_TOOL_OPTIONS`, que la JVM peut afficher. La sélection de ce truststore remplace celle du truststore par défaut pour les clients JSSE concernés ; elle ne modifie pas la confiance OS ou les clients utilisant un contexte TLS indépendant. Prévoir un rollout après rotation.

Pour AppDynamics, adapter `examples/springboot-certificates-appdynamics.yaml` puis l'ajouter après les valeurs d'environnement dans `source.helm.valueFiles`. L'image d'agent doit contenir `/bin/sh`, `cp`, `chmod`, l'agent complet et `javaagent.jar` à la racine de `agentSourceDir`, fonctionner avec UID arbitraire et être compatible avec le JDK et le contrôleur utilisés. L'init container copie l'agent dans un `emptyDir` ; `-javaagent:/opt/appdynamics/javaagent.jar` est ajouté aux options JVM. Le nom du pod identifie le nœud AppDynamics. Le Secret d'accès doit exister dans le namespace backend ; aucune valeur secrète n'est stockée dans Git.

L'exemple AppDynamics cible INT et contient des placeholders. Prévoir des paramètres distincts REC/PROD. Il concerne l'agent Java APM uniquement. La confiance TLS du contrôleur peut nécessiter des paramètres propres à l'agent. Après rotation de sa clé, prévoir un rollout. HTTPD n'injecte aucun agent Java.

Les listes Helm sont remplacées par les surcharges : conserver les variables nécessaires dans `env`. `SERVER_PORT` est généré depuis `port`. Les variables gérées et les noms de volumes réservés sont validés pour éviter les doublons.

## Image HTTPD Red Hat durcie

Le chart utilise `registry.access.redhat.com/hi/httpd:latest`, variante runtime, dans les trois environnements. Le tag `latest-builder` n'est pas utilisé. `imagePullPolicy: Always` permet de résoudre le tag mutable à chaque démarrage ; cela ne redémarre pas automatiquement les pods lorsqu'une nouvelle image est publiée. Pour des promotions reproductibles, remplacer `image` par un digest approuvé et choisir la politique de pull adaptée.

Le Containerfile officiel utilise `ENTRYPOINT ["/usr/bin/httpd", "-DFOREGROUND"]`. Le chart lance directement `/usr/bin/httpd -f /etc/custom-httpd/httpd.conf -DFOREGROUND` : aucun shell, script de démarrage, `mkdir` ou `chown` n'est exécuté dans le conteneur. Il fournit une configuration complète dédiée ; les listeners et inclusions de la configuration par défaut de l'image ne sont donc pas chargés. Le seul listener de ce chart est 8080 ; `mod_ssl` sert à la connexion sortante HTTPS vers la Route backend.

La racine reste en lecture seule ; `/run/httpd` et `/tmp` sont des `emptyDir` inscriptibles. Aucun UID fixe ni SCC anyuid n'est demandé. Les probes sont TCP et ne nécessitent aucun outil dans l'image. Les logs se consultent sans shell :

```sh
oc logs -n monapp-front-int deployment/monapp-int-httpd
oc exec -n monapp-front-int deployment/monapp-int-httpd -- /usr/bin/httpd -t -f /etc/custom-httpd/httpd.conf
oc exec -n monapp-front-int deployment/monapp-int-httpd -- /usr/bin/httpd -M -f /etc/custom-httpd/httpd.conf
```

`oc rsh` et `/bin/sh` ne sont pas requis et peuvent être absents de cette image distroless. Les chemins du binaire, le compte apache, la présence de mod_ssl et la disposition `/etc/httpd` ont été contrôlés dans les sources officielles Hummingbird. Le registre n'a pas fourni de manifeste exploitable dans l'environnement de travail : le digest et le démarrage de l'image publiée n'ont pas été vérifiés ici. Effectuer le test `httpd -t` et le rollout sur le cluster avant promotion.

## Probes, images et logs

Spring Boot doit inclure Actuator et exposer les probes `/actuator/health/liveness` et `/actuator/health/readiness` au kubelet, sur le port applicatif, sans authentification. Adapter les chemins au context-path. Ne pas faire dépendre la liveness d'une base de données. La readiness gouverne les endpoints disponibles pour la Route backend.

HTTPD utilise des probes TCP, qui ne garantissent pas la disponibilité de la Route backend. Les chemins et modules sont ceux d'Red Hat Hardened Image `registry.access.redhat.com/hi/httpd:latest`, avec `/usr/bin/httpd` et `mod_ssl`. Valider l'image approuvée avant promotion. Les logs Apache vont sur stdout/stderr ; l'image Spring Boot doit également prévoir ses logs console. Les images doivent accepter l'UID arbitraire OpenShift ; aucun UID/fsGroup n'est imposé. Le système de fichiers HTTPD est en lecture seule avec des volumes temporaires dédiés.

## Migration depuis les versions précédentes

Cette version retire le StatefulSet, le Service headless et le balancer Apache du commit `78ad91b96c36bff2fbdc267a3d4a7477ffa925ae`. Les anciennes valeurs `workloadKind` et `stickySession` sont rejetées par les schémas, afin de détecter une migration incomplète. Supprimer aussi les anciennes valeurs de cible Service côté HTTPD et les remplacer par `backendRoute`.

Si rien n'a été déployé, utiliser directement cette version. Si un StatefulSet est déjà actif, planifier une fenêtre de maintenance ou une migration parallèle avec des noms ET des sélecteurs différents. Suspendre auto-sync/self-heal avant une migration manuelle. **Ne pas faire coexister un Deployment et un StatefulSet avec les mêmes sélecteurs.** En migration avec interruption, retirer l'ancien contrôleur avant de démarrer le nouveau. Puis valider la Route backend interne, sa confiance TLS et sa disponibilité, avant la synchronisation HTTPD. Les sessions existantes ne sont pas conservées.

L'ancien chart combiné `spring-httpd` reste consultable au commit `6de839f2e65ccdf58f465ad2e2fe55495c7b26f7`. Une Application qui utilise encore ce chemin doit être épinglée à cette ancienne révision pendant sa migration, au lieu de suivre `main`. Aucun changement n'est exécuté sur le cluster par cette livraison.

## Vérifications

```sh
helm lint charts/httpd charts/springboot
python3 verify.py  # Helm dans PATH et PyYAML
helm template monapp-int-httpd charts/httpd -n monapp-front-int -f environments/monapp/int/httpd.yaml
helm template monapp-int-springboot charts/springboot -n monapp-back-int -f environments/monapp/int/springboot.yaml
```

Depuis un poste connecté, valider chaque rendu avec `oc apply --dry-run=server -f -`, puis après synchronisation :

```sh
oc rollout status -n monapp-back-int deployment/monapp-int-springboot
oc rollout status -n monapp-front-int deployment/monapp-int-httpd
oc exec -n monapp-front-int deployment/monapp-int-httpd -- /usr/bin/httpd -t -f /etc/custom-httpd/httpd.conf
curl -v -c cookies.txt -b cookies.txt https://monapp-int.apps.example.com/
```

Pour tester l'affinité réelle, utiliser un endpoint de diagnostic applicatif indiquant le pod et/ou un identifiant de requête visible dans les logs backend. Conserver le même cookie jar, vérifier le même pod, puis provoquer une panne uniquement en environnement de test et vérifier la bascule. Contrôler aussi que la Route backend n'est pas joignable depuis les réseaux non autorisés.

Validation locale : lint et rendu INT/REC/PROD, deux réplicas, deux Deployments, correspondance des hosts, cookies distincts, policies routeur, montage CA, options Java/AppDynamics et rejet des anciens paramètres. Le test suivant utilise deux Apache réels et un serveur HTTPS simulé :

```sh
APACHE_BIN=/chemin/httpd APACHE_MODULES=/chemin/modules python3 tests/route_proxy_smoke.py
```

Il contrôle Host/SNI, headers publics, transmission des cookies dans les deux sens, réécriture du Domain, redirection HTTPS et rejet d'un certificat au mauvais nom. Il adapte les chemins/modules locaux et **ne teste pas le routeur OpenShift, son affinité réelle, l'image Red Hat hi/httpd ou le réseau du cluster**. Aucun déploiement réel ni démarrage de l'agent AppDynamics n'a été effectué ici.

## Références officielles

- [Routes et cookies OpenShift 4.18](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/pdf/ingress_and_load_balancing/routes)
- [Sélection des Routes par IngressController](https://docs.redhat.com/en/documentation/openshift_container_platform/4.19/html/ingress_and_load_balancing/configuring-ingress-cluster-traffic)
- [NetworkPolicies OpenShift](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/network_security/network-policy)
- [Argo CD et Helm](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/)
- [Apache ProxyPass, Host et cookies](https://httpd.apache.org/docs/2.4/mod/mod_proxy.html)
- [Apache vérification TLS du proxy](https://httpd.apache.org/docs/2.4/mod/mod_ssl.html)
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [AppDynamics : agent Java dans les conteneurs](https://docs.appdynamics.com/appd/onprem/24.x/24.6/en/application-monitoring/install-app-server-agents/java-agent/install-the-java-agent/install-the-java-agent-in-containers)
- [Oracle truststore JSSE](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html)

- [Red Hat : Containerfile de hi/httpd](https://gitlab.com/redhat/hummingbird/containers/-/blob/main/images/httpd/Containerfile.j2)
- [Red Hat : packages et utilisateur de hi/httpd](https://gitlab.com/redhat/hummingbird/containers/-/blob/main/images/httpd/properties.yml)
- [Red Hat : documentation HTTPD Hummingbird](https://gitlab.com/redhat/hummingbird/containers/-/blob/main/generated/images/httpd/hummingbird/README.md)
