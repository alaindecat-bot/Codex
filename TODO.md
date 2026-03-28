# TODO

## Priorité immédiate

- documenter dans le `README` la vision produit de l'app macOS
- définir le schéma des profils utilisateur
- définir l'interface moteur unique entre UI et backend
- définir le contrat d'entrée/sortie de l'orchestrateur
- décrire précisément le flux glisser-déposer -> assistant -> génération

## V1 app macOS

- créer une fenêtre avec zone de glisser-déposer
- accepter uniquement les zips WhatsApp en v1
- ouvrir l'assistant après dépôt du zip
- construire un assistant multi-étapes simple et non technique
- détecter les participants et proposer les abréviations
- permettre la confirmation ou la correction des abréviations
- proposer la sélection d'un profil après analyse du zip
- afficher les options de génération pertinentes avant lancement
- afficher un écran de progression pendant le traitement
- afficher un résumé final avec avertissements éventuels
- intégrer le moteur `Codex CLI` derrière l'application

## Préparation du moteur interchangeable

- isoler toutes les options de génération dans une structure indépendante du CLI
- définir une sortie standardisée :
  - document généré
  - progression
  - logs
  - warnings
  - erreurs partielles
- éviter toute logique UI dépendante directement de `Codex CLI`
- préparer le remplacement futur de `Codex CLI` par un moteur Python natif
- préparer l'exécution future sur machine dédiée

## Fonctions futures

- transcription audio
- intégration réelle des paroles Spotify en mode poème selon le profil choisi
- moteur Python natif compilé
- exécution sur machine dédiée
- bibliothèque interne ou historique de documents si cela devient utile

## Dette technique

- passer à Python `3.10+`
- réduire les warnings liés à `urllib3` / `LibreSSL`
- ajouter des tests automatisés sur le parsing et les heuristiques
- clarifier la séparation entre code de production et scripts d'analyse
