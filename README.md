# WhatsApp Zip to Word

Application macOS pour convertir un export WhatsApp (`.zip`) en document Word (`.docx`).

## Objectif

Le `.zip` contient :

- un fichier `.txt` avec l'historique du chat
- des pièces jointes, surtout des photos

L'application devra :

1. ouvrir et extraire le `.zip`
2. parser le fichier `.txt`
3. détecter les URLs dans les messages
4. vérifier la cible de chaque URL
5. appliquer des actions selon le type de contenu trouvé
6. générer un document Word structuré

Exemple de règles :

- `spotify.com` -> ajouter un bloc "Lien Spotify"
- image distante -> ajouter un bloc "Image liée"
- page web classique -> ajouter le titre et l'URL finale

## Proposition technique

Pour un premier projet, le chemin le plus simple est :

- moteur en `Python`
- interface initiale en ligne de commande
- application Mac plus tard si besoin

Pourquoi :

- plus simple pour parser un zip, du texte et générer un `.docx`
- bon support des bibliothèques
- apprentissage GitHub plus facile sur un projet petit et lisible

## Architecture initiale

- `src/whatsapp_zip_to_docx/zip_reader.py`
  - extraction du zip
- `src/whatsapp_zip_to_docx/chat_parser.py`
  - lecture du `.txt`
- `src/whatsapp_zip_to_docx/url_inspector.py`
  - résolution des URLs et classification
- `src/whatsapp_zip_to_docx/rules.py`
  - règles d'action selon le type d'URL
- `src/whatsapp_zip_to_docx/docx_writer.py`
  - génération du fichier Word
- `src/whatsapp_zip_to_docx/main.py`
  - point d'entrée

## Roadmap courte

### Étape 1

Créer un outil qui :

- prend un `.zip` en entrée
- extrait le `.txt`
- liste les pièces jointes
- extrait les URLs du `.txt`

### Étape 2

Ajouter l'inspection des URLs :

- suivre les redirections
- récupérer le type de contenu
- classifier les liens

### Étape 3

Générer un `.docx` :

- messages textuels
- sections médias
- résumé des URLs détectées

### Étape 4

Ajouter une interface Mac.

## GitHub : apprentissage recommandé

Commencer avec ce flux simple :

1. créer un dépôt local
2. faire un premier commit
3. publier sur GitHub
4. travailler par petites branches
5. ouvrir des pull requests, même si vous êtes seul

Commandes de base :

```bash
git init
git add .
git commit -m "Initial project scaffold"
```

Puis après création du repo GitHub :

```bash
git remote add origin <URL_DU_REPO>
git branch -M main
git push -u origin main
```

## Prochaine étape recommandée

Scaffolder le projet Python avec :

- structure `src/`
- environnement virtuel
- dépendances minimales
- premier parseur du `.txt`

## État actuel

Le projet contient maintenant un premier convertisseur Python capable de :

- extraire le zip WhatsApp
- parser `_chat.txt`
- mapper `Alain` vers `A`
- mapper l'autre participant vers une initiale choisie, par exemple `M`
- intégrer les photos dans un document `.docx`
- rendre les messages contenant seulement une URL sur une ligne dédiée

## Exécution

Créer l'environnement virtuel :

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
python3 -m venv .venv
.venv/bin/pip install python-docx
```

Lancer une conversion :

```bash
cd /Users/alaindecat/Codex/whatsapp-zip-to-docx
PYTHONPATH=src .venv/bin/python3 -m whatsapp_zip_to_docx.main \
  "/chemin/vers/WhatsApp Chat.zip" \
  "/chemin/vers/output.docx" \
  --self-name Alain \
  --other-initial M
```

Optionnel :

```bash
--inspect-urls
```

Cette option tente de suivre les URLs et d'afficher leur type dans le terminal.

## Questions encore ouvertes

- quel format exact de document Word voulez-vous en sortie ?
- faut-il intégrer les photos dans le `.docx` ou juste les référencer ?
- faut-il traiter aussi les audios, vidéos et PDF ?
- quelles actions voulez-vous exactement pour Spotify et les autres URLs ?
