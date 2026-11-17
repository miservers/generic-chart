# Routes, sessions et réseau

## Trajet

Le navigateur appelle la Route frontend. HTTPD appelle le hostname de la Route backend en HTTPS/443. Le routeur termine TLS et transmet vers Spring Boot sur son port applicatif (8080 par défaut).

Sur la plateforme décrite, MetalLB expose le Service LoadBalancer du routeur. Le trajet peut donc être : HTTPD → IP MetalLB → Service du routeur → pods routeurs → Spring Boot. MetalLB assure l’exposition ; le routeur OpenShift gère HTTP et l’affinité des Routes.

## Hostname backend

Si `springboot.route.host` est vide, le chart omet `spec.host` et OpenShift attribue le hostname. HTTPD calcule sa cible attendue avec :

```text
<app>-<env>-app-<app>-<env>.apps.<clusterName>.<baseDomain>
```

Le chart ne lit ni la Route ni la configuration du cluster. La plateforme doit confirmer cette convention, y compris l’effet éventuel de `appsDomain`. Comparer le hostname attribué dans la console avec celui du ConfigMap HTTPD. Si les noms diffèrent, utiliser `backendRoute.host` côté HTTPD ou adapter la convention avant déploiement.

Un `fullnameOverride` backend ou une autre convention impose une cible HTTPD explicite correspondante. Aucun `lookup`, `fieldRef` ou script `oc` ne découvre le cluster.

## Affinité

Chaque chart conserve `session: enabled` ou `disabled`. Avec `enabled` et une Route active, `route.cookieName` est obligatoire. Le routeur utilise ce cookie pour sélectionner un endpoint. `JSESSIONID` reste le cookie de session Java.

HTTPD transmet les cookies dans les deux sens ; changer de pod HTTPD n’empêche pas de retrouver le backend sélectionné. Les noms de cookies frontend/backend doivent être distincts et spécifiques à l’application et à l’environnement. Un backend indisponible peut entraîner une nouvelle sélection ; la session Java en mémoire n’est pas répliquée.

Les Routes utilisent TLS edge. La configuration HTTPD vérifie le certificat et le nom backend avec SNI/Host. Si nécessaire, monter une CA privée via `backendRoute.caSecretName`. `ProxyPassReverse` réécrit les redirections et `ProxyPassReverseCookieDomain` le Domain explicitement égal au hostname backend. Adapter le chemin et la portée des cookies si l’application impose un contexte particulier.

## NetworkPolicies

Les deux charts créent, quand `networkPolicy.enabled=true`, une policy d’entrée sélectionnant les pods applicatifs. Elle autorise les routeurs sélectionnés par `networkPolicy.routerNamespaceSelector` sur le port applicatif. Le sélecteur est à confirmer selon le CNI et l’exposition des routeurs.

HTTPD dispose en plus d’un Egress optionnel :

```yaml
networkPolicy:
  enabled: true
  egress:
    enabled: false
    routerNamespace: openshift-ingress
    routerPodSelector: {}
    dnsIPs: []
    dnsPort: 53
```

Après activation et renseignement du DNS, seules les sorties autorisées par les policies applicables sont admises : TCP/443 vers les pods de `openshift-ingress`, et UDP/TCP vers les IPv4 DNS en `/32`. Le namespace et le sélecteur de pods appartiennent au même élément `to` (condition ET).

`openshift-ingress-operator` héberge l’Operator, pas les routeurs. Pour restreindre au contrôleur `default`, après vérification de ses labels :

```yaml
routerPodSelector:
  matchLabels:
    ingresscontroller.operator.openshift.io/deployment-ingresscontroller: default
```

Le port DNS est configurable : 53 pour un chemin filtré vers le Service, éventuellement 5353 vers les pods DNS. La destination effective après NAT, le chemin MetalLB et le mode `hostNetwork` doivent être testés sur le cluster. Le sélecteur ne sélectionne pas directement l’IP MetalLB et ne modifie pas le DNS.

Les policies sont additives. Autoriser les routeurs sur 443 n’isole pas un hostname particulier et ne garantit pas que seul HTTPD peut joindre la Route backend. Son label `ingress-scope: internal` ne la rend pas privée sans configuration adaptée des IngressControllers et de leur exposition. Le refus `/actuator` dans HTTPD ne protège pas un accès contournant HTTPD.

Les règles Egress Spring Boot (DB, RabbitMQ, AppDynamics, etc.) relèvent de la configuration réseau applicative existante et ne sont pas générées ici.

## Références

- [Routes OpenShift](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/ingress_and_load_balancing/configuring-routes)
- [NetworkPolicy, NAT et hostNetwork](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [IngressController OpenShift](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/ingress_and_load_balancing/configuring-ingress-cluster-traffic)
- [Apache : proxy et cookies](https://httpd.apache.org/docs/2.4/mod/mod_proxy.html)
- [Apache : vérification TLS](https://httpd.apache.org/docs/2.4/mod/mod_ssl.html)
