# Chart HTTPD

Reverse proxy Apache HTTPD vers une Route OpenShift backend. Ce chart peut être utilisé directement par une Application Argo CD sans dépendre du chart Spring Boot.

## Utilisation autonome

```yaml
appName: application
image: registry.access.redhat.com/hi/httpd:latest
replicas: 2
session: enabled
route:
  host: application.example.com
  cookieName: APPLICATION_FRONT
backendRoute:
  host: application-backend.example.com
  caSecretName: ""
```

Avec des hosts explicites, `clusterName` et `environment` ne sont pas requis. Pour la convention du dépôt, laisser les hosts vides et fournir ces paramètres via l’Application. Voir [Routes et réseau](../../docs/networking.md).

| Valeur | Usage |
|---|---|
| `appName` | Identité applicative requise, utilisée dans les labels |
| `fullnameOverride` | Nom explicite facultatif des ressources ; défaut : nom de release |
| `image`, `imagePullPolicy`, `imagePullSecrets` | Image Red Hat et accès au registre |
| `replicas`, `port`, `resources` | Deux pods, port non privilégié 8080 et ressources par défaut |
| `proxyTimeout` | Délai du proxy vers le backend en secondes |
| `startupProbe`, `readinessProbe`, `livenessProbe` | Probes configurables ; défaut TCP sans shell |
| `session`, `route.cookieName` | Affinité du routeur frontend, distincte du cookie backend |
| `route.enabled`, `route.host`, `route.labels` | Route edge et labels facultatifs |
| `backendRoute.host` | Cible explicite ou host attendu calculé |
| `backendRoute.caSecretName`, `caSecretKey` | CA PEM facultative, Secret dans le namespace frontend |
| `clusterName`, `environment`, `baseDomain` | Construction locale des hostnames attendus |
| `networkPolicy` | Entrées depuis les routeurs et Egress facultatif |

Le schéma `values.schema.json` définit les valeurs acceptées. Les clés inconnues sont rejetées. Les champs d’un Probe doivent sélectionner un seul handler ; pour changer de handler avec Helm, supprimer l’ancien par une valeur `null` dans la surcharge.

`route.annotations` a été retiré : ce champ était accepté mais ignoré. Les seules annotations générées sont celles du mécanisme de session, conformément au choix retenu. Le comportement de `set-forwarded-headers` dépend donc de la plateforme.

## Image et TLS

Le processus est lancé directement par `/usr/bin/httpd -f /etc/custom-httpd/httpd.conf -DFOREGROUND`. Il ne dépend pas d’un shell. Les modules sont chargés depuis `/etc/httpd/modules`, les logs vont sur stdout/stderr, la racine est en lecture seule et `/run/httpd` et `/tmp` sont des volumes temporaires. Aucun UID ou fsGroup fixe n’est imposé.

Le tag `latest` est conservé pour compatibilité ; remplacer par un digest approuvé pour les promotions. Cette refonte n’a pas démarré l’image distribuée par Red Hat : confirmer les chemins, modules et permissions avec l’image exacte sous SCC restricted-v2.

HTTPD conserve le hostname backend dans Host/SNI et vérifie le nom, la chaîne CA et l’expiration du certificat. Monter une CA privée si nécessaire ; ne pas contourner la vérification TLS. Le checksum du ConfigMap provoque un rollout quand la configuration change. La rotation d’un Secret CA exige un rechargement/rollout séparé.

Une readiness TCP prouve que HTTPD écoute, pas que le backend répond. Le blocage des chemins Actuator dans le proxy ne protège pas une Route backend exposée directement.

## Références

- [Red Hat HTTPD Hummingbird](https://gitlab.com/redhat/hummingbird/containers/-/blob/main/generated/images/httpd/hummingbird/README.md)
- [mod_proxy](https://httpd.apache.org/docs/2.4/mod/mod_proxy.html)
- [mod_ssl](https://httpd.apache.org/docs/2.4/mod/mod_ssl.html)
