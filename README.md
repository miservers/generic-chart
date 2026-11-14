# Helm générique Spring Boot + HTTPD pour OpenShift

Un chart, une Application Argo CD par application métier et environnement, deux namespaces existants. Le frontend désigne ici le reverse proxy HTTPD : toute l'application, y compris les éventuelles pages statiques, est servie par Spring Boot. Un frontend SPA indépendant nécessiterait une adaptation.

Flux : client HTTPS → Route OpenShift edge → Service HTTPD → HTTPD → Service Spring Boot inter-namespace → pods Spring Boot.

La terminaison TLS est assurée par le routeur, avec son certificat par défaut ; les flux internes sont HTTP. Le nom de Route doit être couvert par ce certificat. Cette variante suppose HTTPS en entrée ; si `route.enabled=false`, le frontal externe doit aussi terminer TLS et interdire HTTP. Une exigence TLS interne demande une variante reencrypt et HTTPS jusqu'au backend.

## Structure

- `charts/spring-httpd/` : chart partagé, configuration HTTPD, Deployments, Services, ServiceAccounts, Route, NetworkPolicies et schéma des valeurs.
- `environments/monapp/{int,rec,prod}.yaml` : paramètres par environnement.
- `argocd/monapp-{int,rec,prod}.yaml` : Applications Argo CD ; sync automatique INT/REC, manuelle PROD.
- `verify.py` : vérifications locales du rendu Helm et des invariants réseau.

## Adapter puis déployer

1. Copier le contenu de ce répertoire à la racine d'un dépôt GitOps.
2. Le `repoURL` pointe vers `https://github.com/miservers/generic-chart.git`. Choisir votre AppProject existant (`default` dans l'exemple). Le dépôt étant privé, configurer ses identifiants de lecture dans Argo CD.
3. Renseigner les deux namespaces, le hostname de Route et les images dans chaque fichier d'environnement. Pour PROD, utiliser les digests approuvés, y compris pour HTTPD ; `latest` est uniquement une valeur de démarrage illustrative. Les images privées nécessitent un pull secret présent dans les deux namespaces.
4. Faire préparer les namespaces et les droits Argo CD par l'équipe plateforme. Le chart ne crée ni namespaces ni droits cluster. L'AppProject doit autoriser le dépôt, les DEUX destinations et les types de ressources utilisés. Le compte du contrôleur doit disposer des droits dans les DEUX namespaces, même si `spec.destination.namespace` indique seulement celui du frontend. Tous les objets du chart portent explicitement leur namespace.
5. Ajouter les fichiers à Git, puis créer l'Application :

```sh
oc apply -f argocd/monapp-int.yaml
```

Avec OpenShift GitOps Operator, l'équipe plateforme peut, selon son modèle de délégation, déclarer les deux namespaces comme gérés (cette opération donne des droits au contrôleur, elle doit être conforme aux habilitations locales) :

```sh
oc label namespace monapp-front-int argocd.argoproj.io/managed-by=openshift-gitops
oc label namespace monapp-back-int argocd.argoproj.io/managed-by=openshift-gitops
```

Ne pas utiliser `CreateNamespace=true` pour tenter de créer les deux namespaces : ce mécanisme porte sur le namespace de destination. Les namespaces partagés sont gérés en dehors de cette Application.

## Réutilisation pour une autre application

Créer `environments/facturation/int.yaml` à partir de l'exemple et une Application `facturation-int` avec `helm.releaseName: facturation-int`. Conserver `path: charts/spring-httpd`, changer `valueFiles` en `../../environments/facturation/int.yaml` et adapter `destination.namespace`. Le nom de release doit être unique par application et environnement. Ne pas changer `appName` sur un Deployment existant sans planifier sa recréation : il participe aux sélecteurs immuables.

Le Service backend est calculé automatiquement : pour `monapp-int`, il est `monapp-int-backend.monapp-back-int.svc.cluster.local:8080`. Il n'y a aucune IP de pod ou de Service à renseigner. `clusterDomain` est configurable.

## Images, probes et configuration applicative

- HTTPD : configuration complète dédiée, lancement direct `/usr/sbin/httpd`, chemins et modules de l'image UBI `httpd-24`. Ne pas remplacer cette image par `httpd:alpine` ou une image hardened différente sans adapter les chemins et vérifier les modules. Aucun UID ni fsGroup n'est imposé : OpenShift les attribue selon sa SCC. Le frontend utilise un système de fichiers racine en lecture seule et des volumes `emptyDir` pour son runtime.
- Spring Boot : image compatible UID arbitraire ; port par défaut 8080. Si `backend.port` change, adapter aussi `SERVER_PORT` dans `backend.env`. Helm remplace les listes `env` lors d'une surcharge : recopier les variables nécessaires.
- Les probes backend supposent Actuator installé et ses endpoints `/actuator/health/liveness` et `/actuator/health/readiness` accessibles sans authentification depuis le kubelet, sur le même port. Adapter les chemins si context-path. Les trois probes sont configurables. Ne pas faire dépendre la liveness d'une base de données.
- HTTPD : probes TCP, donc contrôle du port uniquement. La disponibilité fonctionnelle de Spring Boot relève de sa propre readiness et des contrôles externes.
- `backend.envFrom` peut référencer un Secret existant dans le namespace backend. Aucun mot de passe n'est créé dans Git.
- Les changements de ConfigMap HTTPD déclenchent un rollout via checksum. Pour les Secrets externes référencés par `envFrom`, prévoir un redémarrage ou un mécanisme de rechargement à leur rotation.
- Les logs HTTPD sortent sur stdout/stderr. Consulter avec `oc logs -n monapp-front-int deployment/monapp-int-frontend`. La gestion de l'image Spring Boot doit également prévoir les logs console.
- Pas d'affinité de session entre les pods Spring Boot. Deux réplicas supposent une application stateless ou un stockage de session partagé, par exemple Spring Session/Redis. Un cookie du routeur colle au pod HTTPD, pas au pod backend derrière le Service.

## Politique réseau

Les règles installées sélectionnent uniquement les pods de cette release : entrée HTTPD depuis les namespaces des routeurs, entrée backend uniquement depuis les pods HTTPD de cette même application dans le namespace frontend. `namespaceSelector` et `podSelector` figurent dans le même élément pour exiger les deux conditions.

Les NetworkPolicies sont additives : une règle préexistante plus permissive peut autoriser d'autres sources. Les règles de ce chart ne ferment pas les sorties. Si vos namespaces ont un deny egress, l'équipe plateforme doit autoriser DNS, HTTPD vers les pods backend au port applicatif, ainsi que les sorties backend nécessaires (DB, RabbitMQ, proxy, etc.). Les politiques administratives du cluster peuvent également influencer les flux. Adapter le sélecteur routeur si votre topologie utilise des labels différents.

Le frontal n'expose pas `/actuator`. Tout monitoring direct du backend devra disposer d'une règle d'entrée dédiée. HTTPD définit `X-Forwarded-Proto=https` et `X-Forwarded-Port=443` pour cette topologie edge HTTPS. L'adresse IP cliente et sa chaîne X-Forwarded-For nécessitent une politique de confiance du routeur et des proxys ; ne pas utiliser cet en-tête brut comme preuve d'identité.

## Vérifier

```sh
helm lint charts/spring-httpd
helm template monapp-int charts/spring-httpd -f environments/monapp/int.yaml
python3 verify.py  # nécessite Helm dans PATH et PyYAML

# Depuis un poste connecté, après préparation des namespaces et des droits :
helm template monapp-int charts/spring-httpd -f environments/monapp/int.yaml | oc apply --dry-run=server -f -
oc rollout status -n monapp-back-int deployment/monapp-int-backend
oc rollout status -n monapp-front-int deployment/monapp-int-frontend
oc get route -n monapp-front-int monapp-int
oc exec -n monapp-front-int deployment/monapp-int-frontend -- /usr/sbin/httpd -t -f /etc/custom-httpd/httpd.conf
curl -I https://monapp-int.apps.example.com/
```

Validation livrée : lint Helm et rendu des trois environnements, contrôle des namespaces, sélecteurs Service/Deployment, cible DNS HTTPD et règles inter-namespace ; rejet des namespaces identiques. Aucun déploiement réel ni test d'exécution de l'image HTTPD n'a été effectué ici. Vérifier SCC, disponibilité des images, RBAC et réseau sur votre cluster avant promotion.

## Références officielles

- Argo CD et Helm : https://argo-cd.readthedocs.io/en/stable/user-guide/helm/
- Argo CD, spécification Application : https://argo-cd.readthedocs.io/en/stable/user-guide/application-specification/
- OpenShift GitOps, permissions multi-namespace : https://docs.redhat.com/en/documentation/red_hat_openshift_gitops/1.21/html/multitenancy/multitenancy-support-in-gitops
- OpenShift 4.18, NetworkPolicy : https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/network_security/network-policy
- Kubernetes, DNS des Services : https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
- Apache HTTPD, ProxyPass et ProxyPassReverse : https://httpd.apache.org/docs/2.4/mod/mod_proxy.html
- Images HTTPD SCLorg : https://github.com/sclorg/httpd-container
- Spring Boot Actuator et probes : https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
