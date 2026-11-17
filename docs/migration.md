# Migration vers la version 0.5.0 des charts

Cette refonte part du commit `06c9da0ce670ead0567eb4dd12eab5c2fb6bb47e`. Aucun déploiement, commit ou push ne fait partie de la préparation locale.

## Compatibilité des ressources

Les noms, namespaces, sélecteurs de pods, ports, réplicas, terminaison TLS edge et paramètres des ApplicationSets sont conservés. Les labels descriptifs `helm.sh/chart` et `app.kubernetes.io/managed-by` sont ajoutés aux ressources hors Route ; ils ne participent pas aux sélecteurs. La version des deux charts passe à 0.5.0. Les paramètres de noms sont explicitement transmis comme chaînes (`forceString`) ; leur valeur ne change pas.

Le checksum HTTPD porte sur le ConfigMap complet. L’ajout de ses labels descriptifs change donc le checksum et entraînera un rollout HTTPD à la première synchronisation, même si le texte de configuration reste identique.

Les helpers internes sont préfixés `httpd.*` et `springboot.*` pour éviter une collision lorsque les charts sont composés par un parent Helm. Ils ne changent pas les noms des ressources. Un éventuel chart externe référençant directement les anciens helpers `app.*` doit être adapté.

## Valeurs à adapter

| Ancienne valeur | Action |
|---|---|
| `springboot.image` omise | Fournir l’image réelle ; le défaut d’exemple a été retiré |
| `route.annotations` | Retirer ce champ, auparavant ignoré ; aucune annotation supplémentaire n’est injectée |
| `springboot.baseDomain` | Retirer ce champ sans effet ; le domaine fixe appartient uniquement à HTTPD |
| Clés inconnues ou fautes de frappe | Corriger selon le `values.yaml` et le schéma du chart |
| `networkPolicy.enabled=false` et `egress.enabled=true` | Choisir une combinaison cohérente ; ce cas est désormais refusé |

Les probes HTTPD ont des valeurs configurables avec les mêmes réglages TCP qu’auparavant. Le chart ne rajoute ni PDB, ni affinité de placement, ni stratégie de disponibilité.

Les exemples `app1`, `app2` et `monapp` continuent de fournir leur image backend, leurs cookies et leurs ressources. Les chemins des fichiers de valeurs et des ApplicationSets ne sont pas déplacés.

## Vérification avant synchronisation

Exécuter `make check`, puis examiner le diff des manifests dans votre processus Argo CD habituel. Vérifier en particulier les erreurs de schéma sur les fichiers propres à votre organisation. La validation locale ne remplace pas les contrôles de plateforme.

Confirmer sur un environnement d’essai : hostname backend attribué par OpenShift, DNS et TLS, chemin MetalLB, filtrage Egress vers les routeurs, admission interne de la Route, cookies aller/retour, comportement après redémarrage. Les droits ApplicationSet/AppProject ne sont pas modifiés par cette refonte.

## Anciennes versions du dépôt

Les versions utilisant un StatefulSet, un Service headless ou un balancer Apache nécessitent une migration distincte. Ne pas faire coexister des contrôleurs aux sélecteurs identiques. Vérifier les propriétaires des objets avant toute suppression afin d’éviter une suppression en cascade. La session mémoire n’est pas conservée lors d’un changement de pod.
