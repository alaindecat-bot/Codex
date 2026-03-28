# WhatsApp Zip to Word

Projet de transformation d'un export WhatsApp (`.zip`) en document Word (`.docx`).

Aujourd'hui, le moteur de traitement est un programme Python lancé via `Codex CLI`.
La prochaine phase du projet vise une vraie application macOS simple à utiliser.

## Vision produit

La cible produit n'est plus une interface en ligne de commande, mais une application macOS.

Cette v1 macOS doit :

- accepter un export WhatsApp par glisser-déposer
- ouvrir un assistant unique, simple et non technique
- détecter les personnes du chat et proposer leurs abréviations
- permettre de choisir un profil de préférences
- lancer la génération du document Word
- afficher un résumé clair avec avertissements éventuels

Le backend actuel reste `Codex CLI`.
Le backend futur devra pouvoir être remplacé par un moteur Python natif ou par un service dédié sur une machine séparée, sans refaire l'interface.

## Parcours utilisateur cible

Flux visé pour l'application macOS :

1. l'utilisateur dépose un zip WhatsApp dans la fenêtre
2. l'application analyse le zip
3. elle détecte les participants
4. elle propose les abréviations et laisse l'utilisateur les corriger
5. elle propose ou applique un profil
6. l'utilisateur valide les options du document
7. l'application lance la génération du `.docx`
8. elle affiche un résumé final avec les éventuels enrichissements manquants ou partiels

La v1 doit rester limitée au zip WhatsApp, afin de garder un parcours clair et fiable.

## Décisions produit retenues

Décisions déjà prises pour la prochaine phase :

- l'entrée principale de l'app sera le glisser-déposer
- l'assistant sera unique, guidé et en mode simple
- les participants seront détectés automatiquement puis confirmés
- l'application proposera des profils réutilisables
- le profil contiendra au minimum :
  - résumé activé ou non
  - politique Spotify
  - politique vidéo
  - comportements réseau/cloud utiles
- Spotify sera en mode poème par défaut
- les paroles Spotify ne seront insérées que si le profil choisi l'autorise
- les vidéos utiliseront Google Drive si cela améliore le document
- l'audio sera visible dans l'interface, mais désactivé en v1
- l'application continuera la génération même si certains enrichissements échouent
- l'usage normal suppose qu'Internet peut être utilisé quand le traitement en a besoin

## Architecture cible

L'architecture visée doit clairement séparer :

- l'interface utilisateur macOS
- l'orchestrateur de traitement
- l'interface moteur
- l'implémentation moteur actuelle via `Codex CLI`
- l'implémentation moteur future via Python natif ou service dédié

Le moteur doit être interchangeable.
L'application macOS ne doit pas dépendre directement de détails propres à `Codex CLI`.

Contrat conceptuel du moteur :

- entrée :
  - zip WhatsApp
  - options utilisateur
  - profil sélectionné
- sortie :
  - document `.docx`
  - progression
  - avertissements
  - erreurs partielles

## Ce que le projet fait aujourd'hui

Le moteur actuel sait déjà :

- extraire un export WhatsApp `.zip`
- parser `_chat.txt`
- générer un document Word structuré par mois et par jour
- afficher les messages avec heure au format `[hh:mm]`
- mapper les participants vers des abréviations, par exemple `Alain -> A`, `murithul -> M`
- intégrer les photos dans le document
- rendre la première page des PDF comme image
- enrichir certains liens publics :
  - `Spotify`
  - `Facebook`
  - pages web classiques avec métadonnées publiques
- intégrer des aperçus cliquables dans le document Word
- envoyer les vidéos sur Google Drive et rendre une vignette cliquable dans le document
- proposer un mode interactif de lancement pour choisir certaines options avant génération

## Rendu Word actuel

Le document généré peut contenir :

- titres de mois
- titres de jours
- messages texte
- poèmes détectés heuristiquement
- images jointes
- PDF rendus comme image
- blocs enrichis pour `Spotify`, `Facebook` et certains liens web
- vignettes vidéo cliquables vers Google Drive si l'option est activée

## Structure actuelle du moteur

- `src/whatsapp_zip_to_docx/zip_reader.py`
  - extraction du zip
- `src/whatsapp_zip_to_docx/parser.py`
  - parsing du chat WhatsApp
- `src/whatsapp_zip_to_docx/url_tools.py`
  - inspection et enrichissement des URLs
- `src/whatsapp_zip_to_docx/docx_writer.py`
  - génération du document Word
- `src/whatsapp_zip_to_docx/google_drive.py`
  - authentification Google Drive et upload de fichiers
- `src/whatsapp_zip_to_docx/interactive.py`
  - dialogue interactif de lancement
- `src/whatsapp_zip_to_docx/reply_analysis.py`
  - heuristiques de détection des réponses
- `src/whatsapp_zip_to_docx/main.py`
  - point d'entrée CLI actuel
- `scripts/export_reply_candidates.py`
  - export Markdown des candidats `question/réponse`

## Moteur actuel : utilisation CLI

La CLI reste le moteur actuel du projet.
Elle n'est plus l'expérience finale visée, mais elle reste le backend de référence à court terme.

## Installation

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
python3 -m venv .venv
.venv/bin/pip install -e .
```

Si vous n'utilisez pas l'installation editable :

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
.venv/bin/pip install python-docx google-api-python-client google-auth-oauthlib
```

## Utilisation du moteur actuel

Conversion simple :

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
PYTHONPATH=src .venv/bin/python3 -m whatsapp_zip_to_docx.main \
  "/chemin/vers/WhatsApp Chat.zip" \
  "/chemin/vers/output.docx" \
  --self-name Alain \
  --other-initial M
```

Avec enrichissement d'URLs :

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
PYTHONPATH=src .venv/bin/python3 -m whatsapp_zip_to_docx.main \
  "/chemin/vers/WhatsApp Chat.zip" \
  "/chemin/vers/output.docx" \
  --self-name Alain \
  --other-initial M \
  --enrich-urls
```

Avec dialogue interactif :

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
PYTHONPATH=src .venv/bin/python3 -m whatsapp_zip_to_docx.main \
  "/chemin/vers/WhatsApp Chat.zip" \
  "/chemin/vers/output.docx" \
  --interactive
```

Avec upload des vidéos vers Google Drive :

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
PYTHONPATH=src .venv/bin/python3 -m whatsapp_zip_to_docx.main \
  "/chemin/vers/WhatsApp Chat.zip" \
  "/chemin/vers/output.docx" \
  --self-name Alain \
  --other-initial M \
  --enrich-urls \
  --upload-videos-to-drive
```

## Google Drive

Le moteur actuel peut utiliser un client OAuth Google de type `Desktop app`.

Fichiers locaux attendus :

- `secrets/client_secret_....json`
- `secrets/google_drive_token.json`

Tester l'authentification :

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
PYTHONPATH=src .venv/bin/python3 -m whatsapp_zip_to_docx.main dummy.zip dummy.docx --test-drive-auth
```

Tester un upload de fichier :

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
PYTHONPATH=src .venv/bin/python3 -m whatsapp_zip_to_docx.main dummy.zip dummy.docx --upload-to-drive "/chemin/vers/un/fichier"
```

## Analyse des réponses

Le script suivant exporte deux listes de candidats `question/réponse` :

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
PYTHONPATH=src .venv/bin/python3 scripts/export_reply_candidates.py \
  "/chemin/vers/WhatsApp Chat.zip" \
  "/chemin/vers/dossier_sortie"
```

Sorties générées :

- `reply_candidates_simple.md`
- `reply_candidates_semantic.md`

## État GitHub

Le dépôt GitHub est publié ici :

- [alaindecat-bot/Codex](https://github.com/alaindecat-bot/Codex)
