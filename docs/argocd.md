# Argo CD

## Une instance par cluster

Chaque ApplicationSet utilise deux générateurs List combinés par Matrix : le premier déclare `clusterName`, `apps`, `envs`, `components` ; le deuxième développe les listes avec `elementsYaml`. Les suffixes `app/prez` et `fr` sont calculés une seule fois. Il n’y a pas de générateur de clusters ni de lecture API.

Le nom du cluster est transmis à Helm et au label `deployment.example.com/cluster` de chaque Application. Il doit correspondre au segment utilisé dans la convention DNS ; il peut différer du nom enregistré dans Argo CD. Le préfixe de label `deployment.example.com` est un exemple organisationnel.

Le domaine fixe se trouve uniquement dans `charts/httpd/values.yaml` sous `baseDomain`. Il n’est pas fourni par les ApplicationSets ni répété dans les valeurs applicatives.

## Ordre des valeurs

Chaque Application charge :

1. Les valeurs par défaut de son chart.
2. `environments/network/<cluster>/<env>.yaml`.
3. `environments/<app>/<env>/<composant>.yaml`.
4. Les paramètres Helm de l’Application : `appName`, `environment`, `clusterName`, `replicas`.

Les paramètres ont priorité sur les fichiers. Le réglage existant `replicas: 2` est conservé dans les ApplicationSets ; une autre valeur dans un fichier d’environnement ne le remplacera pas. Pour changer le nombre de pods, modifier le paramètre de l’Application/ApplicationSet correspondant.

Le fichier réseau commun contient `networkPolicy.egress`. Le chart Spring Boot accepte ce contexte pour partager les mêmes fichiers mais n’applique aucune règle Egress. La signification de ces paramètres est exclusivement HTTPD.

Les listes Helm, notamment `env`, `certificates` et `extraVolumes`, sont remplacées par les surcharges ; elles ne sont pas fusionnées élément par élément.

## Namespaces et AppProjects

| Champ | Fonction |
|---|---|
| `Application.metadata.namespace` | Namespace où réside l’objet Application Argo CD |
| `Application.spec.destination.namespace` | Namespace où sont déployés les workloads |
| `Application.spec.project` | AppProject contrôlant les dépôts et destinations autorisés |

Les exemples ApplicationSet utilisent `gitops-metier` comme namespace source et `applications-metier` comme AppProject. Adapter ces noms à l’entité ; ne pas remplacer arbitrairement les projets isolés existants par un projet commun.

La plateforme doit autoriser :

- Les Applications et ApplicationSets dans le namespace source, via la configuration de l’instance Argo CD/Operator.
- Ce namespace dans `AppProject.spec.sourceNamespaces`.
- Le dépôt privé et les destinations dans chaque AppProject.
- Les permissions Kubernetes des contrôleurs sur les ressources gérées.

Les charts ne créent ni namespace, ni AppProject, ni droits cluster. Les objets AppProject restent dans le namespace de contrôle Argo CD. Les Applications peuvent résider dans le namespace de l’entité.

Un ApplicationSet crée ses Applications dans son propre namespace. Si chaque Application doit résider dans un namespace distinct, prévoir un ApplicationSet par namespace ou créer les Applications individuellement. App of Apps ne contourne pas les droits manquants.

## Création depuis l’interface

Les fichiers `examples/applications/app1-int-{app,prez}.yaml` sont des modèles complets à coller dans l’éditeur YAML Argo CD. Adapter le namespace source et l’AppProject existants, puis contrôler les paramètres Helm. Aucun ApplicationSet n’est nécessaire pour cette méthode.

Les Applications des exemples suivent `main`. Les changements locaux ne sont visibles qu’après publication explicite dans Git. Adapter `targetRevision` à votre processus de promotion ; aucune politique de publication automatique n’est ajoutée ici.

## Références

- [Argo CD : paramètres et priorité des valeurs Helm](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/)
- [List et elementsYaml](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Generators-List/)
- [Matrix](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Generators-Matrix/)
- [Applications dans plusieurs namespaces](https://argo-cd.readthedocs.io/en/stable/operator-manual/app-any-namespace/)
- [ApplicationSets dans plusieurs namespaces](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Appset-Any-Namespace/)
