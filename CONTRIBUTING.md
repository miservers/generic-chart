# Contribuer

Le périmètre du dépôt comprend deux charts autonomes et leurs exemples Argo CD. Une modification du chart doit rester indépendante du nom d’une application ou d’un cluster.

## Vérification

Installer Helm 3, un compilateur Go 1.20+ et Python 3.10+, puis :

```sh
python3 -m pip install -r requirements-dev.txt
make check
```

`tests/check.py` exécute tous les contrôles hors ligne et s’arrête sur une erreur :

- Développement des List/Matrix avec les chaînes Go template réellement utilisées, puis `helm lint` et `helm template` pour chaque Application.
- Exemples historiques, certificats et paramètres AppDynamics.
- Routes, cookies, Egress, erreurs de valeurs et indépendance des helpers Helm.

Le test de composition place temporairement les deux charts dans un parent Helm pour détecter les collisions de helpers. Il ne modélise pas le déploiement front/backend dans deux namespaces, qui reste décrit par deux Applications.

Le script `tests/route_proxy_smoke.py` est un contrôle facultatif avec deux Apache réels vers un serveur HTTPS simulé. Il exige Apache, ses modules, OpenSSL, Helm et PyYAML :

```sh
APACHE_BIN=/chemin/httpd APACHE_MODULES=/chemin/modules python3 tests/route_proxy_smoke.py
```

Il vérifie les cookies, Host/SNI, redirections et le refus d’un mauvais certificat ; il ne teste pas le routeur OpenShift ni l’image Red Hat. Le test ne fait pas partie de `make check` car Apache n’est pas un prérequis du dépôt.

## Conception

- Préfixer les helpers par le nom du chart ; conserver les sélecteurs immuables lors d’une refonte.
- Ajouter une valeur uniquement si elle a un effet documenté. Décrire son type dans le schéma et fournir un défaut cohérent.
- Utiliser `values.schema.json` pour les types et `templates/validate.yaml` pour les règles entre champs.
- Garder les templates des Routes simples et la session configurable par chart.
- Ne pas utiliser `lookup`, `fieldRef` ou un script `oc` pour découvrir le cluster au rendu.
- Ne pas stocker de Secret dans Git. Les fichiers applicatifs et domaines restent des exemples explicites.
- Mettre à jour la documentation et les tests pertinents ; ne pas présenter un rendu local comme un test de connectivité.

## Références

- [Helpers nommés Helm et portée globale](https://helm.sh/docs/chart_template_guide/named_templates/)
- [Schémas des valeurs Helm](https://helm.sh/docs/topics/charts/)
- [Priorité des valeurs Argo CD](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/)
