rpi-rgb-led-matrix — console web
=================================

Petit serveur web (Python 3, stdlib uniquement, aucun module à installer)
qui permet de lancer les exemples et utilitaires de ce repo depuis une page
web, sans taper de ligne de commande. Le serveur génère dynamiquement un
formulaire pour chaque programme avec :

  - toutes les options communes de la matrice LED
    (`--led-rows`, `--led-chain`, `--led-brightness`, `--led-pixel-mapper`...),
  - les options spécifiques au programme (texte, fonte, image, couleurs,
    démo à lancer, etc.),
  - le bouton « Compiler (make) » pour bâtir le binaire si besoin,
  - un terminal d'envoi sur `stdin` pour les programmes interactifs
    (`text-example`, `pixel-mover`),
  - l'upload de fichiers (images, vidéos, fontes) dans `webserver/uploads/`.

Programmes pris en charge :

  - `examples-api-use/demo` (toutes les démos `-D 0..11`)
  - `examples-api-use/minimal-example`
  - `examples-api-use/text-example`
  - `examples-api-use/scrolling-text-example`
  - `examples-api-use/clock`
  - `examples-api-use/image-example`
  - `examples-api-use/pixel-mover`
  - `utils/led-image-viewer`
  - `utils/text-scroller`
  - `utils/video-viewer`

Démarrage
---------

```
python3 webserver/server.py
```

Le serveur écoute par défaut sur `http://0.0.0.0:8080/`. Ouvrez cette URL
dans un navigateur depuis le réseau local du Pi.

Options :

  - `--host` : adresse d'écoute (défaut `0.0.0.0`).
  - `--port` : port (défaut `8080`).
  - `--no-sudo` : ne préfixe **pas** les commandes par `sudo` (utile en
    développement sans matériel).

sudo / privilèges
-----------------

Les binaires de la matrice doivent être lancés en root pour accéder aux
GPIO. Le serveur préfixe automatiquement la commande par `sudo -n` (mode
non-interactif). Deux possibilités :

  1. Lancer le serveur lui-même en root :
     `sudo python3 webserver/server.py`
     C'est la solution la plus simple ; le binaire ciblé continuera à
     « drop privileges » comme prévu par la librairie une fois la matrice
     initialisée.

  2. Ou bien autoriser l'utilisateur courant à appeler `sudo` sans mot de
     passe pour ces binaires (via `/etc/sudoers.d`).

Compilation
-----------

Les exemples doivent être compilés une fois (`make` dans
`examples-api-use/` et `utils/`). L'interface a un bouton **Compiler**
pour chaque programme : il lance `make <cible>` dans le bon répertoire et
affiche la sortie.

`image-example`, `led-image-viewer` et `video-viewer` ont des dépendances
supplémentaires :

```
sudo apt-get install libgraphicsmagick++-dev libwebp-dev \
                     libavcodec-dev libavformat-dev libswscale-dev \
                     libavdevice-dev pkg-config
```

Utilisation
-----------

  1. Sélectionnez un programme dans la barre latérale.
  2. Ajustez les options de la matrice et les options du programme.
     Les valeurs sont sauvegardées dans `localStorage` du navigateur.
  3. Cliquez sur **Lancer**. Un seul programme tourne à la fois : si l'on
     en lance un nouveau alors qu'un autre est actif, le serveur refuse —
     cliquez d'abord sur **Arrêter**.
  4. La sortie standard et stderr s'affichent en bas de page.
  5. Pour les programmes interactifs (`text-example`, `pixel-mover`),
     tapez le texte / les touches dans la zone *Entrée standard* et
     cliquez sur **Envoyer sur stdin**.

API HTTP
--------

Pour les usages programmatiques :

  - `GET  /api/programs` : métadonnées (options communes + programmes).
  - `GET  /api/files?program=<id>&option=<name>` : liste des fichiers
    autorisés pour ce champ (fontes, images, vidéos selon le programme).
  - `GET  /api/status` : `{ running, program_id, argv, started_at,
    exit_code, log_seq }`.
  - `GET  /api/log?since=<seq>` : log incrémental (sortie capturée).
  - `POST /api/start` body `{ program_id, values }` : démarre.
  - `POST /api/stop` : termine le processus en cours (SIGTERM puis
    SIGKILL au besoin, propagé au groupe via `setsid`).
  - `POST /api/stdin` body `{ text }` : envoie une ligne sur stdin du
    processus.
  - `POST /api/build` body `{ program_id }` : `make` la cible.
  - `POST /api/upload` `multipart/form-data` : uploade un fichier dans
    `webserver/uploads/`.

Sécurité
--------

Le serveur lance des binaires en tant que root et n'a aucune
authentification. **À n'utiliser que sur un réseau de confiance.**
Toutes les options sont validées côté serveur (types, plages de couleurs,
chemins de fichiers limités à des sous-dossiers du repo) et chaque
argument est passé séparément à `subprocess` — il n'y a pas
d'interpolation shell.
