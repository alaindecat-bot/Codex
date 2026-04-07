# TODO

## Priorité immédiate

- documenter dans le `README` la vision produit de l'app macOS
- fait en première passe : définir le schéma des profils utilisateur
- fait en première passe : définir l'interface moteur unique entre UI et backend
- fait en première passe : définir le contrat d'entrée/sortie de l'orchestrateur
- fait en première passe : décrire précisément dans le code le flux glisser-déposer -> assistant -> génération
- à documenter dans le `README` : le flux produit complet, incluant estimation, timeout et rapports de performance
- prochaine priorité produit : terminer les derniers cas de liens riches, surtout LinkedIn, X / Twitter, SWR et pages médias similaires

## V1 app macOS

- fait : créer une fenêtre avec zone de glisser-déposer
- fait : accepter uniquement les zips WhatsApp en v1
- accepter à terme les zips contenant plusieurs fichiers `.txt` de conversation
- fait en première passe : ouvrir l'assistant après dépôt du zip
- construire un assistant multi-étapes simple et non technique
- fait : détecter les participants et proposer les abréviations
- fait : permettre la confirmation ou la correction des abréviations
- fait : proposer la sélection d'un profil après analyse du zip
- permettre le choix de la langue de l'application dans le menu de démarrage
- si le zip contient plusieurs conversations, permettre de choisir le ou les fichiers `.txt` à traiter
- partiellement fait : afficher les options de génération pertinentes avant lancement
- fait en première passe : afficher une estimation avant lancement
- fait en première passe : proposer un timeout par multiplicateur de durée prévue ou valeur fixe
- fait en première passe : proposer un rapport de performance oui/non
- fait en première passe : afficher un écran de progression pendant le traitement
- fait en première passe : permettre l'arrêt manuel ou par timeout
- partiellement fait : afficher un résumé final avec avertissements éventuels
- fait en première passe : produire une analyse prédiction vs temps réel après génération, arrêt, erreur ou timeout
- fait en première passe : produire un dashboard SVG de performance quand l'option est active
- obsolète / remplacé : intégrer le moteur `Codex CLI` derrière l'application
- fait : le moteur utilisé par l'app est maintenant le moteur Python natif du projet

## Préparation du moteur interchangeable

- fait en première passe : isoler toutes les options de génération dans une structure indépendante du CLI
- fait en première passe : définir une sortie standardisée :
  - document généré
  - progression
  - logs
  - warnings
  - erreurs partielles
- fait : éviter toute logique UI dépendante directement de `Codex CLI`
- fait en première passe : préparer le remplacement futur de `Codex CLI` par un moteur Python natif
- préparer l'exécution future sur machine dédiée
- à améliorer : rendre la progression plus événementielle, pas seulement basée sur la durée estimée

## Fonctions futures

- fait en première passe : transcription audio
- fait en première passe : intégration réelle des paroles Spotify en mode poème selon le profil choisi
- moteur Python natif compilé
- exécution sur machine dédiée
- bibliothèque interne ou historique de documents si cela devient utile
- bibliothèque de temps d'exécution : commencée via historique local de prédictions / temps réels

## Dette technique

- passer à Python `3.10+`
- réduire les warnings liés à `urllib3` / `LibreSSL`
- commencé : ajouter des tests automatisés sur le parsing et les heuristiques
- clarifier la séparation entre code de production et scripts d'analyse
- introduire une vraie couche d'internationalisation UI pour permettre au moins le français, l'anglais et le néerlandais
- rendre l'import zip robuste aux archives contenant plusieurs `.txt` et des entrées parasites comme `__MACOSX`
- améliorer le modèle de prédiction avec plus d'historique réel et des coûts par type d'URL plus fins
- décider si les rapports de performance doivent être conservés dans le dossier de sortie ou dans un dossier d'application dédié
