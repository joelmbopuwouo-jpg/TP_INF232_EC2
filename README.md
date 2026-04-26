# TP_INF232 - Application économie (Flask)

Ce dépôt contient une petite application Flask (fichier principal `app2.py`) destinée à gérer des marchés, boutiques, vendeurs, clients, produits, commandes et factures dans un stockage SQLite local.

## Objectif
- Fournir une application serveur-side (sans JavaScript côté client) pour gérer un registre d'acteurs économiques et suivre les ventes.
- Support basique: CRUD, commandes multi-items, facturation, corbeille (soft-delete), export CSV et une image SVG d'analyse.

## Prérequis
- Python 3.8+ (tests faits avec Python 3.10/3.12 recommandés)
- Un environnement virtuel recommandé

## Installation rapide
```bash
# depuis la racine du projet
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # si fourni
# ou installer manuellement
pip install flask flask_sqlalchemy
```

## Variables d'environnement
- `SECRET_KEY` : clé secrète Flask. Par défaut `app2.py` utilise `dev-change-me` si non défini. Changez-la en production.
- `FLASK_DEBUG` : mettez `1` / `true` pour activer le mode debug local. Par défaut, le serveur démarre en debug=False.

Exemple (dev) :
```bash
export SECRET_KEY="ma_cle_dev_change_me"
export FLASK_DEBUG=1
python3 app2.py
```

## Base de données
L'application utilise SQLite (`economie.db`) par défaut (URI : `sqlite:///economie.db` dans `app2.py`).
Au premier démarrage, les tables sont créées automatiquement via `db.create_all()`.

Note sur les migrations
- L'application contient des migrations légères qui ajoutent des colonnes manquantes via `ALTER TABLE` si nécessaire. Pour un projet réel, il est fortement recommandé d'utiliser Alembic pour gérer les migrations de façon sûre et traçable.

## Exécution
Lancer l'application en local :
```bash
# exemple :
export SECRET_KEY="quelque_chose_sécurisé"
python3 app2.py
# ou pour debug local
export FLASK_DEBUG=1
python3 app2.py
```
Ensuite ouvrez http://127.0.0.1:5000/ dans votre navigateur.

## Endpoints utiles
- `/` : page d'accueil
- `/registre` : liste des marchés enregistrés
- `/produits`, `/boutiques`, `/vendeurs`, `/clients` : CRUD correspondants
- `/commandes` : création et traitement des commandes
- `/factures` : factures générées
- `/bilan` et `/bilan/export` : vue de synthèse et export CSV
- `/stats.svg` et `/analyse` : graphique d'analyse en SVG
- Corbeille : route(s) pour restaurer ou supprimer définitivement les éléments marqués `supprime=True`

## Sécurité et pré-production (recommandations)
- Ne pas utiliser SQLite en production si vous attendez une charge ou besoin de concurrence ; préférez Postgres.
- Fixez `SECRET_KEY` via variable d'environnement (ne laissez pas la valeur par défaut).
- Utiliser Gunicorn + un gestionnaire de processus (systemd) pour la production :
```bash
# exemple minimal
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app2:app
```
- Ajouter CSRF (Flask-WTF) pour protéger les formulaires POST.
- Intégrer Alembic pour migrations, et configurer backups réguliers de la base.

## Tests & CI
- Ajouter `pytest` et des tests unitaires pour les routes et modèles clés.
- Ajouter un workflow GitHub Actions pour lint/tests.

## Fichiers à ajouter / prochains pas (TODO)
- `requirements.txt` (générer depuis votre environnement ou ajouter manuellement)
- `Dockerfile` et `docker-compose.yml` pour déploiement
- Intégration Alembic
- Tests unitaires (pytest)
- CSRF / validation des formulaires

---
Si vous voulez, je peux :
- Générer immédiatement un `requirements.txt` à partir de l'environnement actuel.
- Ajouter un `.env.example` et intégrer `python-dotenv` pour charger automatiquement les variables en dev.
- Créer un `Dockerfile` minimal et un `docker-compose.yml` pour tester en local.

## Déploiement sur Render

Vous pouvez déployer ce projet sur Render en utilisant le `Dockerfile` fourni ou en configurant un Web Service.

- Déploiement Docker : poussez votre repo sur GitHub et créez un service Docker sur Render. `render.yaml` est fourni comme exemple. Définissez les variables d'environnement (SECRET_KEY, FLASK_DEBUG, SQLALCHEMY_DATABASE_URI) dans le Dashboard Render.
- Déploiement sans Docker : créez un Web Service, utilisez `pip install -r requirements.txt` comme build command et `gunicorn -w 4 -b 0.0.0.0:$PORT app2:app` comme start command.

Remarques :
- Render ne fournit pas de stockage local persistant pour SQLite. Pour les données persistantes, préférez une base managée (Postgres) et mettez à jour `SQLALCHEMY_DATABASE_URI`.
- Stockez `SECRET_KEY` et autres secrets dans les Environment Secrets de Render (ne les commitez pas).
