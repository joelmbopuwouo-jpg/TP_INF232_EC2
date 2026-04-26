"""Script minimal pour transférer les données d'un fichier SQLite vers une base Postgres.
Usage:
  export SOURCE_DB=sqlite:///economie.db
  export TARGET_DB=postgresql://user:pass@host:5432/dbname
  python3 scripts/transfer_sqlite_to_postgres.py

Remarque: Ce script fait une copie simple en utilisant SQLAlchemy ORM/metadata.
Vérifiez les contraintes et index côté Postgres après import.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# importez les classes de votre application
from app2 import db, Produit, Boutique, Vendeur, Client, Marche, Facture, Commande, CommandeItem

SOURCE_DB = os.environ.get('SOURCE_DB', 'sqlite:///economie.db')
TARGET_DB = os.environ.get('TARGET_DB')

if not TARGET_DB:
    raise SystemExit('Définir TARGET_DB environment variable (Postgres URL)')

print('Source:', SOURCE_DB)
print('Target:', TARGET_DB)

# connect to source (SQLite) and target (Postgres)
source_engine = create_engine(SOURCE_DB)
Target_engine = create_engine(TARGET_DB)

SourceSession = sessionmaker(bind=source_engine)
TargetSession = sessionmaker(bind=Target_engine)

source_s = SourceSession()
target_s = TargetSession()

# create tables in target if not present
print('Creating tables in target DB if necessary...')
db.metadata.create_all(Target_engine)

print('Copying boutiques...')
for b in source_s.query(Boutique).all():
    b2 = Boutique(id=b.id, nom=b.nom, marche=b.marche, adresse=b.adresse, supprime=b.supprime)
    target_s.merge(b2)

print('Copying vendeurs...')
for v in source_s.query(Vendeur).all():
    v2 = Vendeur(id=v.id, nom=v.nom, telephone=v.telephone, boutique_id=v.boutique_id, supprime=v.supprime)
    target_s.merge(v2)

print('Copying clients...')
for c in source_s.query(Client).all():
    c2 = Client(id=c.id, nom=c.nom, contact=c.contact, boutique_id=c.boutique_id, supprime=c.supprime)
    target_s.merge(c2)

print('Copying marches...')
for m in source_s.query(Marche).all():
    m2 = Marche(id=m.id, nom=m.nom, date_enregistrement=m.date_enregistrement, supprime=m.supprime)
    target_s.merge(m2)

print('Copying produits...')
for p in source_s.query(Produit).all():
    p2 = Produit(id=p.id, marche=p.marche, nom=p.nom, categorie=p.categorie, boutique_id=p.boutique_id, prix=p.prix, date_enregistrement=p.date_enregistrement, quantite=p.quantite, supprime=p.supprime)
    target_s.merge(p2)

print('Copying factures...')
for f in source_s.query(Facture).all():
    f2 = Facture(id=f.id, produit_id=f.produit_id, boutique_id=f.boutique_id, vendeur_id=f.vendeur_id, client_id=f.client_id, prix=f.prix, date=f.date, supprime=f.supprime)
    target_s.merge(f2)

print('Copying commandes...')
for cmd in source_s.query(Commande).all():
    cmd2 = Commande(id=cmd.id, boutique_id=cmd.boutique_id, vendeur_id=cmd.vendeur_id, client_id=cmd.client_id, total=cmd.total, date=cmd.date, etat=cmd.etat, supprime=cmd.supprime)
    target_s.merge(cmd2)

print('Copying commande items...')
for it in source_s.query(CommandeItem).all():
    it2 = CommandeItem(id=it.id, commande_id=it.commande_id, produit_id=it.produit_id, quantite=it.quantite, prix_unitaire=it.prix_unitaire)
    target_s.merge(it2)

print('Committing...')
target_s.commit()
print('Done.')
