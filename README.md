# WhatsApp Zip to Word

Convertisseur Python pour transformer un export WhatsApp (`.zip`) en document Word (`.docx`).

## Ce que le projet fait aujourd'hui

Le projet sait déjà :

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

## Structure du projet

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
  - point d'entrée CLI
- `scripts/export_reply_candidates.py`
  - export Markdown des candidats `question/réponse`

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

## Utilisation

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

Le projet peut utiliser un client OAuth Google de type `Desktop app`.

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

## Prochaines améliorations

- intégrer le marquage des réponses détectées directement dans le document Word
- affiner encore le dialogue interactif de lancement
- améliorer la présentation visuelle des vidéos dans Word
- traiter éventuellement les audios
- nettoyer l'environnement Python pour réduire les warnings techniques
