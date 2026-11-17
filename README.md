# generic-chart — HTTPD et Spring Boot sur OpenShift

Deux charts Helm autonomes, dans un même dépôt, déployés par Argo CD :

| Chart | Responsabilité | Namespace de déploiement |
|---|---|---|
| [httpd](charts/httpd/README.md) | Reverse proxy HTTPS vers la Route backend | `<app>-<env>fr` |
| [springboot](charts/springboot/README.md) | Application Java, certificats et AppDynamics facultatifs | `<app>-<env>` |

Les deux composants utilisent des Deployments de deux réplicas par défaut. Le trajet est : navigateur → Route frontend → HTTPD → Route backend → Spring Boot. Le backend et le frontend se trouvent sur le même cluster, dans des namespaces différents.

## Configuration et responsabilités

| Emplacement | Contenu |
|---|---|
| `charts/<composant>/values.yaml` | Valeurs génériques et options documentées |
| `environments/<app>/<env>/<composant>.yaml` | Image, cookie, ressources et spécifiques applicatifs |
| `environments/network/<cluster>/<env>.yaml` | Egress HTTPD commun aux applications de cet environnement |
| `argocd/clusters/<cluster>/applicationset.yaml` | Applications, environnements et nom du cluster déclaré une seule fois |

Les paramètres Helm fournis par les ApplicationSets sont `appName`, `environment`, `clusterName` et `replicas: 2`. Le domaine organisationnel fixe `baseDomain` se configure dans le chart HTTPD. Spring Boot laisse OpenShift attribuer le hostname de sa Route quand `route.host` est vide.

Le hostname attendu par HTTPD est **calculé**, jamais lu sur le cluster. La convention DNS et le hostname réellement attribué doivent être confirmés sur la plateforme.

## Déployer avec Argo CD

1. Adapter les fichiers applicatifs : image Spring Boot, cookies distincts, ressources et éventuels Secrets existants.
2. Remplacer `example.com` par le domaine fixe dans `charts/httpd/values.yaml`, et adapter les noms des clusters dans les ApplicationSets.
3. Faire autoriser le namespace source `gitops-metier`, l’AppProject et les namespaces de destination par la plateforme.
4. Faire gérer uniquement `argocd/clusters/<cluster>/applicationset.yaml` par l’instance Argo CD locale. Si les droits ApplicationSet manquent, utiliser les [modèles d’Applications individuelles](examples/applications/).

Les trois configurations sont :

| Cluster | Environnements | Applications générées |
|---|---|---:|
| `hors-prod` | int, rec | 8 |
| `prod-a` | prod | 4 |
| `prod-b` | prod | 4 |

Les noms restent `<app>-<env>-app` pour Spring Boot et `<app>-<env>-prez` pour HTTPD. Chaque Argo CD cible `https://kubernetes.default.svc`. La synchronisation des Applications générées est manuelle.

## Ajouter une application

Copier `environments/app1/` vers `environments/<nouvelle-app>/`, adapter les images et cookies puis ajouter son nom dans `apps` des ApplicationSets concernés. Il n’est pas nécessaire de copier les charts. Utiliser les modèles d’Applications individuelles si les AppProjects diffèrent entre applications ou entités.

Les exemples historiques `monapp` restent disponibles aux anciens chemins, avec leurs hosts explicites et leurs namespaces spécifiques. Ils ne sont pas générés par les ApplicationSets et ne doivent pas être importés en même temps comme nouveaux déploiements.

## Vérifier localement

Prérequis : Python 3.10+, Helm 3 et un compilateur Go 1.20+ dans `PATH`.

```sh
python3 -m pip install -r requirements-dev.txt
make check
```

La commande effectue le lint et le rendu Helm de chaque Application, vérifie les exemples historiques et les contrats des charts. Les résultats sont dans `build/rendered/` (hors Git). Aucun accès au cluster ni commande `oc` n’est nécessaire. `python3 verify.py` reste un raccourci compatible pour les seuls anciens exemples.

## Documentation

- [Argo CD, Applications individuelles et ApplicationSets](docs/argocd.md)
- [Routes, sessions, MetalLB et NetworkPolicies](docs/networking.md)
- [Migration vers cette refonte](docs/migration.md)
- [HTTPD : valeurs et utilisation autonome](charts/httpd/README.md)
- [Spring Boot : valeurs, certificats et AppDynamics](charts/springboot/README.md)
- [Contribuer et exécuter les vérifications](CONTRIBUTING.md)

Les images et domaines d’exemple ne constituent pas une configuration de production. Les contrôles locaux ne testent ni l’image Red Hat publiée, ni l’agent AppDynamics, ni les droits, le DNS, les Routes ou l’affinité sur un vrai cluster.
