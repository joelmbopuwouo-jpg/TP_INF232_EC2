from flask import Flask, render_template, request, redirect, url_for, Response, flash, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os, signal
try:
    # optionally load environment variables from a .env file in development
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # python-dotenv not installed or .env missing: continue silently
    
    pass
from sqlalchemy import text
import time


app = Flask(__name__)
# Ensure instance path is writable in restricted environments (Vercel Lambda is read-only).
# Honor INSTANCE_PATH env var if provided, otherwise use a writable tmp directory.
instance_path_env = os.environ.get('INSTANCE_PATH')
if instance_path_env:
    app.instance_path = instance_path_env
else:
    # prefer a /tmp/instance path which is writable on many serverless platforms
    try:
        tmp_instance = '/tmp/instance'
        os.makedirs(tmp_instance, exist_ok=True)
        app.instance_path = tmp_instance
    except Exception:
        # fallback: keep Flask default but avoid raising here — SQLAlchemy may try to create it and fail;
        # we'll guard SQLAlchemy initialization by handling creation errors where necessary.
        pass

#con figuration de la base de donnees
# Determine DB URI: prefer explicit environment variable. If not provided,
# fall back to the local SQLite file to avoid crashing when Postgres isn't
# available (useful for quick local testing).
db_uri = os.environ.get('SQLALCHEMY_DATABASE_URI')
if not db_uri:
    db_uri = 'sqlite:///economie.db'

# If the URI is for Postgres but psycopg2 is not installed, fall back to sqlite
if db_uri and db_uri.startswith(('postgres://', 'postgresql://')):
    try:
        import psycopg2  # type: ignore
    except Exception:
        # warn and fallback to sqlite to avoid crashing when psycopg2 isn't available
        print('WARNING: SQLALCHEMY_DATABASE_URI points to Postgres but psycopg2 is not installed. Falling back to SQLite for local testing.')
        db_uri = 'sqlite:///economie.db'

app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.secret_key = os.environ.get('SECRET_KEY', 'dev-change-me')
db = SQLAlchemy(app)

# modele de donnees
class Produit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    marche = db.Column(db.String(50))
    nom = db.Column(db.String(50))
    categorie = db.Column(db.String(50)) # habillement, nutrition, etc...
    boutique_id = db.Column(db.Integer, db.ForeignKey('boutique.id'), nullable=True)
    boutique = db.relationship('Boutique', backref='produits')
    prix = db.Column(db.Float)
    date_enregistrement = db.Column(db.DateTime, default=datetime.utcnow)
    quantite = db.Column(db.Integer, default=1)
    supprime = db.Column(db.Boolean, default=False)


class Boutique(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(80), nullable=False)
    marche = db.Column(db.String(50), nullable=False)
    adresse = db.Column(db.String(200))
    # relation vers les vendeurs et clients
    vendeurs = db.relationship('Vendeur', backref='boutique', cascade='all, delete-orphan')
    clients = db.relationship('Client', backref='boutique', cascade='all, delete-orphan')
    supprime = db.Column(db.Boolean, default=False)


class Vendeur(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(50))
    boutique_id = db.Column(db.Integer, db.ForeignKey('boutique.id'), nullable=False)
    supprime = db.Column(db.Boolean, default=False)


class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    contact = db.Column(db.String(120))
    boutique_id = db.Column(db.Integer, db.ForeignKey('boutique.id'), nullable=True)
    supprime = db.Column(db.Boolean, default=False)


class Marche(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), unique=True, nullable=False)
    date_enregistrement = db.Column(db.DateTime, default=datetime.utcnow)
    supprime = db.Column(db.Boolean, default=False)


class Facture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produit_id = db.Column(db.Integer, db.ForeignKey('produit.id'), nullable=False)
    produit = db.relationship('Produit', backref='factures')
    boutique_id = db.Column(db.Integer, db.ForeignKey('boutique.id'), nullable=False)
    boutique = db.relationship('Boutique')
    vendeur_id = db.Column(db.Integer, db.ForeignKey('vendeur.id'), nullable=True)
    vendeur = db.relationship('Vendeur')
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=True)
    client = db.relationship('Client')
    prix = db.Column(db.Float)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    supprime = db.Column(db.Boolean, default=False)


class Commande(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    boutique_id = db.Column(db.Integer, db.ForeignKey('boutique.id'), nullable=False)
    boutique = db.relationship('Boutique')
    vendeur_id = db.Column(db.Integer, db.ForeignKey('vendeur.id'), nullable=True)
    vendeur = db.relationship('Vendeur')
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    client = db.relationship('Client')
    total = db.Column(db.Float, default=0.0)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    etat = db.Column(db.String(30), default='nouvelle')
    supprime = db.Column(db.Boolean, default=False)


class CommandeItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    commande_id = db.Column(db.Integer, db.ForeignKey('commande.id'), nullable=False)
    commande = db.relationship('Commande', backref='items')
    produit_id = db.Column(db.Integer, db.ForeignKey('produit.id'), nullable=False)
    produit = db.relationship('Produit')
    quantite = db.Column(db.Integer, nullable=False, default=1)
    prix_unitaire = db.Column(db.Float, nullable=False)

with app.app_context():
    db.create_all()
    # Lightweight migrations for existing DBs (SQLAlchemy 2.x compatible)
    try:
        # produit.quantite
        with db.engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info('produit')")).all()
            cols = [r[1] for r in res]
        if 'quantite' not in cols:
            raw = db.engine.raw_connection()
            cur = raw.cursor()
            cur.execute("ALTER TABLE produit ADD COLUMN quantite INTEGER DEFAULT 1")
            raw.commit()
            cur.close()
            raw.close()
    except Exception:
        # non-fatal: continue if migration cannot be applied
        pass

    try:
        # commande.etat
        with db.engine.connect() as conn:
            res2 = conn.execute(text("PRAGMA table_info('commande')")).all()
            cols2 = [r[1] for r in res2]
        if 'etat' not in cols2:
            raw = db.engine.raw_connection()
            cur = raw.cursor()
            cur.execute("ALTER TABLE commande ADD COLUMN etat VARCHAR(30) DEFAULT 'nouvelle'")
            raw.commit()
            cur.close()
            raw.close()
        # add supprime column (soft-delete) if missing
        with db.engine.connect() as conn:
            res3 = conn.execute(text("PRAGMA table_info('commande')")).all()
            cols3 = [r[1] for r in res3]
        if 'supprime' not in cols3:
            raw = db.engine.raw_connection()
            cur = raw.cursor()
            # SQLite uses INTEGER for booleans; default 0 -> False
            cur.execute("ALTER TABLE commande ADD COLUMN supprime INTEGER DEFAULT 0")
            raw.commit()
            cur.close()
            raw.close()
        # add supprime column to other tables if missing
        tables = ['produit','facture','client','vendeur','boutique']
        for tbl in tables:
            with db.engine.connect() as conn:
                resx = conn.execute(text(f"PRAGMA table_info('{tbl}')")).all()
                colsx = [r[1] for r in resx]
            if 'supprime' not in colsx:
                raw = db.engine.raw_connection()
                cur = raw.cursor()
                cur.execute(f"ALTER TABLE {tbl} ADD COLUMN supprime INTEGER DEFAULT 0")
                raw.commit()
                cur.close()
                raw.close()
    except Exception:
        pass

@app.route('/')
def home():
    produits = Produit.query.filter_by(supprime=False).all()
    # calcul automatique du nombre par catrgorie pour l'analyse
    stats = {}
    for p in produits:
        stats[p.categorie] = stats.get(p.categorie, 0) +1
    boutiques = Boutique.query.filter_by(supprime=False).all()
    # petites catégories utilisées aussi sur la page d'accueil pour le formulaire
    categories = ['Nutrition','Habillement','Electronique','Autre','Maquillage','Construction','Boisson']
    # marchés enregistrés (unique) : préférer la table Marche si elle existe
    marches_set = set()
    try:
        for m in Marche.query.filter_by(supprime=False).all():
            if m.nom:
                marches_set.add(m.nom)
    except Exception:
        # si la table Marche n'existe pas (avant migration), fallback aux boutiques/produits
        for b in Boutique.query.filter_by(supprime=False).all():
            if b.marche:
                marches_set.add(b.marche)
        for p in Produit.query.filter_by(supprime=False).all():
            if p.marche:
                marches_set.add(p.marche)
    marches = sorted(list(marches_set))
    return render_template('index.html', produits=produits, stats=stats, boutiques=boutiques, categories=categories, marches=marches)

@app.route('/ajouter', methods=['GET','POST'])
def ajouter():
    categories = ['Nutrition','Habillement','Electronique','Autre','Maquillage','Construction','Boisson']
    if request.method == 'GET':
        marche = request.args.get('marche')
        if marche:
            # afficher le formulaire complet avec boutiques pour ce marche
            boutiques = Boutique.query.filter_by(marche=marche).all()
            return render_template('ajouter.html', marche=marche, boutiques=boutiques, categories=categories)
        # pas de marche choisi: rediriger vers la page d'accueil (qui contient la sélection de marche)
        return redirect(url_for('home'))

    # POST: création du produit
    if request.method == 'POST':
        marche = (request.form.get('marche') or '').strip()
        boutique_id = request.form.get('boutique')
        nom_produit = (request.form.get('produit') or '').strip()
        categorie = (request.form.get('categorie') or '').strip()
        prix_field = request.form.get('prix')
        quantite_field = request.form.get('quantite')
        # validation: marche, nom, categorie, prix required
        if not marche or not nom_produit or not categorie or not prix_field:
            flash('Veuillez remplir tous les champs requis pour ajouter un produit.', 'error')
            return redirect(url_for('ajouter') + f"?marche={marche}")
        try:
            prix = float(prix_field)
        except Exception:
            flash('Prix invalide.', 'error')
            return redirect(url_for('ajouter') + f"?marche={marche}")

        # validate boutique if provided
        if boutique_id:
            try:
                bid = int(boutique_id)
            except Exception:
                flash('Boutique invalide.', 'error')
                return redirect(url_for('ajouter') + f"?marche={marche}")
            if not db.session.get(Boutique, bid):
                flash('Boutique sélectionnée introuvable.', 'error')
                return redirect(url_for('ajouter') + f"?marche={marche}")
            bid_val = bid
        else:
            bid_val = None

        # parse quantite if provided
        quantite = None
        if quantite_field:
            try:
                quantite = int(quantite_field)
                if quantite < 0:
                    raise ValueError()
            except Exception:
                flash('Quantité invalide.', 'error')
                return redirect(url_for('ajouter') + f"?marche={marche}")

        nouveau_p = Produit(
            marche=marche,
            nom=nom_produit,
            categorie=categorie,
            prix=prix,
            boutique_id=bid_val,
            quantite=(quantite if quantite is not None else 1)
        )
        db.session.add(nouveau_p)
        db.session.commit()
        flash(f"Produit '{nouveau_p.nom}' ajouté dans la boutique.", 'success')
        return redirect(url_for('home'))

@app.route('/supprimer/<int:id>', methods=['GET','POST'])
def supprimer(id):
    p = db.session.get(Produit, id)
    if p is None:
        flash('Produit introuvable.', 'error')
        return redirect(url_for('home'))

    if request.method == 'GET':
        # afficher une page de confirmation côté serveur (aucun JS requis)
        return render_template('confirm_delete_product.html', p=p)

    # POST: effectuer la suppression après confirmation
    # empêcher la suppression si des factures existent pour ce produit
    if p.factures:
        flash('Impossible de supprimer: ce produit a des factures associées.', 'error')
        return redirect(url_for('home'))
    # soft-delete: mark as supprime
    p.supprime = True
    db.session.commit()
    flash('Produit marqué comme supprimé.', 'info')
    return redirect(url_for('home'))

@app.route('/quitter')
def quitter ():
    os.kill(os.getpid(), signal.SIGINT)
    return "Serveur arrete."


@app.route('/boutiques', methods=['GET','POST'])
def boutiques():
    if request.method == 'POST':
        nom = request.form.get('nom','').strip()
        marche = request.form.get('marche','').strip()
        adresse = request.form.get('adresse')
        # validation: nom and marche required
        if not nom or not marche:
            flash('Veuillez renseigner le nom et le marché de la boutique.', 'error')
            return redirect(url_for('boutiques'))
        b = Boutique(nom=nom, marche=marche, adresse=adresse)
        db.session.add(b)
        db.session.commit()
        flash(f"Boutique '{nom}' ajoutée pour le marché '{marche}'.", 'success')
        next_url = request.args.get('next') or request.form.get('next')
        if next_url:
            return redirect(next_url)
        return redirect(url_for('boutiques'))

    all_boutiques = Boutique.query.filter_by(supprime=False).all()
    return render_template('boutiques.html', boutiques=all_boutiques)


@app.route('/boutiques/edit/<int:id>', methods=['GET','POST'])
def edit_boutique(id):
    b = db.session.get(Boutique, id)
    if b is None:
        abort(404)
    if request.method == 'POST':
        nom = (request.form.get('nom') or '').strip()
        marche = (request.form.get('marche') or '').strip()
        adresse = (request.form.get('adresse') or '').strip()
        # validation: nom and marche required
        if not nom or not marche:
            flash('Veuillez renseigner le nom et le marché de la boutique.', 'error')
            return redirect(url_for('edit_boutique', id=b.id))
        b.nom = nom
        b.marche = marche
        b.adresse = adresse
        db.session.commit()
        flash('Boutique mise à jour.', 'success')
        return redirect(url_for('boutiques'))
    return render_template('boutiques_edit.html', b=b)


@app.route('/boutiques/<int:id>')
def view_boutique(id):
    b = db.session.get(Boutique, id)
    if b is None:
        abort(404)
    # produits liés (filtrer les produits supprimés)
    produits = Produit.query.filter_by(boutique_id=b.id, supprime=False).all()
    return render_template('boutiques_view.html', b=b, produits=produits)


@app.route('/produits/edit/<int:id>', methods=['GET','POST'])
def edit_produit(id):
    p = db.session.get(Produit, id)
    if p is None:
        abort(404)
    if request.method == 'POST':
        nom = (request.form.get('nom') or '').strip()
        categorie = (request.form.get('categorie') or '').strip()
        prix_field = request.form.get('prix')
        quantite_field = request.form.get('quantite')
        if not nom or not categorie or not prix_field or quantite_field is None:
            flash('Veuillez remplir tous les champs obligatoires du produit.', 'error')
            return redirect(url_for('edit_produit', id=p.id))
        try:
            prix = float(prix_field)
        except Exception:
            flash('Prix invalide.', 'error')
            return redirect(url_for('edit_produit', id=p.id))
        try:
            quantite = int(quantite_field)
        except Exception:
            flash('Quantité invalide.', 'error')
            return redirect(url_for('edit_produit', id=p.id))
        p.nom = nom
        p.categorie = categorie
        p.prix = prix
        p.quantite = quantite
        db.session.commit()
        flash('Produit mis à jour.', 'success')
        return redirect(url_for('view_boutique', id=p.boutique.id if p.boutique else 0))
    return render_template('produits_edit.html', p=p)





@app.route('/factures')
def factures():
    factures = Facture.query.filter_by(supprime=False).order_by(Facture.date.desc()).all()
    return render_template('factures.html', factures=factures)


@app.route('/factures/delete/<int:id>', methods=['GET','POST'])
def delete_facture(id):
    f = db.session.get(Facture, id)
    if f is None:
        abort(404)
    if request.method == 'GET':
        return render_template('confirm_delete_facture.html', f=f)
    try:
        # soft-delete: mark as supprime
        f.supprime = True
        db.session.commit()
        flash('Facture marquée comme supprimée.', 'info')
    except Exception:
        db.session.rollback()
        flash('Erreur lors de la suppression de la facture.', 'error')
    return redirect(url_for('factures'))


@app.route('/commandes')
def commandes():
    # n'afficher que les commandes non supprimées
    commandes = Commande.query.filter_by(supprime=False).order_by(Commande.date.desc()).all()
    return render_template('commandes.html', commandes=commandes)


@app.route('/commandes/delete/<int:id>', methods=['GET','POST'])
def delete_commande(id):
    com = db.session.get(Commande, id)
    if com is None:
        abort(404)
    # determine if there is any "empty" field or invalid items
    def _empty_conditions(c):
        empty_fields = []
        if not c.client_id:
            empty_fields.append('client')
        if c.total is None or c.total == 0:
            empty_fields.append('total')
        bad_items = [it for it in c.items if (it.produit is None) or (it.quantite is None) or (it.quantite <= 0)]
        return empty_fields, bad_items

    empty_fields, bad_items = _empty_conditions(com)

    if request.method == 'GET':
        can_delete = bool(empty_fields or bad_items)
        return render_template('confirm_delete_commande.html', com=com, can_delete=can_delete, empty_fields=empty_fields, bad_items=bad_items)

    # POST: perform deletion only if at least one empty condition is present
    empty_fields, bad_items = _empty_conditions(com)
    if not (empty_fields or bad_items):
        flash('Impossible de supprimer: la commande ne contient pas de champ vide.', 'error')
        return redirect(url_for('commandes'))

    try:
        # restore stock for existing items (safe guard)
        # make a copy of items to avoid mutation during iteration
        items_copy = list(com.items)
        for it in items_copy:
            if it.produit:
                it.produit.quantite = (it.produit.quantite or 0) + (it.quantite or 0)
            # delete the item explicitly
            try:
                db.session.delete(it)
            except Exception:
                pass
        # now delete the commande itself
        db.session.delete(com)
        db.session.commit()
        flash('Commande supprimée.', 'info')
    except Exception:
        db.session.rollback()
        flash('Erreur lors de la suppression de la commande.', 'error')
    return redirect(url_for('commandes'))



@app.route('/commandes/force_delete/<int:id>', methods=['GET','POST'])
def force_delete_commande(id):
    com = db.session.get(Commande, id)
    if com is None:
        abort(404)
    if request.method == 'GET':
        return render_template('confirm_force_delete_commande.html', com=com)
    try:
        # soft-delete: mark as supprime=True
        com.supprime = True
        db.session.commit()
        flash('Commande marquée comme supprimée (force).', 'info')
    except Exception:
        db.session.rollback()
        flash('Erreur lors de la suppression forcée de la commande.', 'error')
    return redirect(url_for('commandes'))


@app.route('/corbeille')
def corbeille():
    # collect soft-deleted items from all models
    commandes = Commande.query.filter_by(supprime=True).order_by(Commande.date.desc()).all()
    factures = Facture.query.filter_by(supprime=True).order_by(Facture.date.desc()).all()
    produits = Produit.query.filter_by(supprime=True).all()
    clients = Client.query.filter_by(supprime=True).all()
    vendeurs = Vendeur.query.filter_by(supprime=True).all()
    boutiques = Boutique.query.filter_by(supprime=True).all()
    return render_template('corbeille.html', commandes=commandes, factures=factures, produits=produits, clients=clients, vendeurs=vendeurs, boutiques=boutiques)


def _model_map(name):
    m = {
        'commande': Commande,
        'facture': Facture,
        'produit': Produit,
        'client': Client,
        'vendeur': Vendeur,
        'boutique': Boutique,
    }
    return m.get(name)


@app.route('/corbeille/restore/<model>/<int:id>', methods=['GET','POST'])
def corbeille_restore(model, id):
    Model = _model_map(model)
    if not Model:
        flash('Modèle inconnu.', 'error')
        return redirect(url_for('corbeille'))
    obj = db.session.get(Model, id)
    if obj is None:
        abort(404)
    if request.method == 'GET':
        return render_template('confirm_corbeille_action.html', action='restauration', model=model, obj=obj)
    try:
        obj.supprime = False
        db.session.commit()
        flash(f'{model} restauré.', 'success')
    except Exception:
        db.session.rollback()
        flash('Erreur lors de la restauration.', 'error')
    return redirect(url_for('corbeille'))


@app.route('/corbeille/delete_permanent/<model>/<int:id>', methods=['GET','POST'])
def corbeille_delete_permanent(model, id):
    Model = _model_map(model)
    if not Model:
        flash('Modèle inconnu.', 'error')
        return redirect(url_for('corbeille'))
    obj = db.session.get(Model, id)
    if obj is None:
        abort(404)
    if request.method == 'GET':
        return render_template('confirm_corbeille_action.html', action="suppression définitive", model=model, obj=obj)
    try:
        # special-case: if commande, delete its items first
        if model == 'commande':
            for it in list(obj.items):
                try:
                    db.session.delete(it)
                except Exception:
                    pass
        db.session.delete(obj)
        db.session.commit()
        flash(f'{model} supprimé définitivement.', 'info')
    except Exception:
        db.session.rollback()
        flash('Erreur lors de la suppression définitive.', 'error')
    return redirect(url_for('corbeille'))


@app.route('/corbeille/vider', methods=['GET','POST'])
def corbeille_vider():
    if request.method == 'GET':
        return render_template('confirm_empty_corbeille.html')
    try:
        # delete CommandeItems for soft-deleted commandes
        deleted_counts = {}
        # Commandes
        to_del_cmds = Commande.query.filter_by(supprime=True).all()
        cnt_cmd = 0
        for com in to_del_cmds:
            for it in list(com.items):
                try:
                    db.session.delete(it)
                except Exception:
                    pass
            try:
                db.session.delete(com)
                cnt_cmd += 1
            except Exception:
                pass
        deleted_counts['commandes'] = cnt_cmd

        # Factures
        cnt_fact = 0
        for f in Facture.query.filter_by(supprime=True).all():
            try:
                db.session.delete(f)
                cnt_fact += 1
            except Exception:
                pass
        deleted_counts['factures'] = cnt_fact

        # Produits
        cnt_prod = 0
        for p in Produit.query.filter_by(supprime=True).all():
            try:
                db.session.delete(p)
                cnt_prod += 1
            except Exception:
                pass
        deleted_counts['produits'] = cnt_prod

        # Clients
        cnt_client = 0
        for c in Client.query.filter_by(supprime=True).all():
            try:
                db.session.delete(c)
                cnt_client += 1
            except Exception:
                pass
        deleted_counts['clients'] = cnt_client

        # Vendeurs
        cnt_v = 0
        for v in Vendeur.query.filter_by(supprime=True).all():
            try:
                db.session.delete(v)
                cnt_v += 1
            except Exception:
                pass
        deleted_counts['vendeurs'] = cnt_v

        # Boutiques
        cnt_b = 0
        for b in Boutique.query.filter_by(supprime=True).all():
            try:
                db.session.delete(b)
                cnt_b += 1
            except Exception:
                pass
        deleted_counts['boutiques'] = cnt_b

        db.session.commit()
        flash(f'Corbeille vidée (commandes={cnt_cmd}, factures={cnt_fact}, produits={cnt_prod}, clients={cnt_client}, vendeurs={cnt_v}, boutiques={cnt_b}).', 'info')
    except Exception:
        db.session.rollback()
        flash('Erreur lors du vidage de la corbeille.', 'error')
    return redirect(url_for('corbeille'))


@app.route('/commandes/process/<int:id>', methods=['GET','POST'])
def process_commande(id):
    com = db.session.get(Commande, id)
    if com is None:
        abort(404)
    if request.method == 'GET':
        return render_template('confirm_process_commande.html', com=com)

    # POST: create Facture(s) for each item, do not touch stock (stock handled at order creation)
    if com.etat != 'nouvelle':
        flash('Commande déjà traitée ou dans un état non traitable.', 'error')
        return redirect(url_for('commandes'))

    try:
        # create one Facture per CommandeItem with prix = prix_unitaire * quantite
        for it in com.items:
            f = Facture(produit_id=it.produit_id, boutique_id=com.boutique_id, vendeur_id=com.vendeur_id, client_id=com.client_id, prix=(it.prix_unitaire * it.quantite))
            db.session.add(f)
        com.etat = 'traitee'
        db.session.commit()
        flash('Commande traitée : factures générées.', 'success')
    except Exception:
        db.session.rollback()
        flash('Erreur lors du traitement de la commande.', 'error')
    return redirect(url_for('commandes'))


@app.route('/commandes/new', methods=['GET','POST'])
def commandes_new():
    # allow placing an order for a specific boutique with multiple products
    boutiques = Boutique.query.filter_by(supprime=False).all()
    clients = Client.query.filter_by(supprime=False).all()
    if request.method == 'GET':
        selected_boutique = request.args.get('boutique_id')
        produits = []
        vendeurs = []
        if selected_boutique:
            try:
                bid = int(selected_boutique)
                produits = Produit.query.filter_by(boutique_id=bid, supprime=False).all()
                vendeurs = Vendeur.query.filter_by(boutique_id=bid, supprime=False).all()
            except Exception:
                produits = []
                vendeurs = []
        return render_template('commandes_new.html', boutiques=boutiques, clients=clients, produits=produits, selected_boutique=selected_boutique, vendeurs=vendeurs)

    # POST: create a Commande with multiple items
    boutique_field = request.form.get('boutique_id')
    client_field = request.form.get('client_id')
    vendeur_field = request.form.get('vendeur_id')
    if not boutique_field or not client_field:
        flash('Veuillez sélectionner une boutique et un client pour la commande.', 'error')
        return redirect(url_for('commandes_new'))
    try:
        boutique_id = int(boutique_field)
        client_id = int(client_field)
    except Exception:
        flash('Identifiants boutique/client invalides.', 'error')
        return redirect(url_for('commandes_new'))
    if not db.session.get(Boutique, boutique_id):
        flash('Boutique introuvable.', 'error')
        return redirect(url_for('commandes_new'))
    if not db.session.get(Client, client_id):
        flash('Client introuvable.', 'error')
        return redirect(url_for('commandes_new'))
    vendeur_id = int(vendeur_field) if vendeur_field else None

    # collect product quantities from form: fields named qty_<produit_id>
    items = []
    total = 0.0
    for key, val in request.form.items():
        if not key.startswith('qty_'):
            continue
        try:
            pid = int(key.split('_',1)[1])
            q = int(val or 0)
        except Exception:
            continue
        if q <= 0:
            continue
        produit = db.session.get(Produit, pid)
        if not produit or produit.boutique_id != boutique_id:
            flash(f'Produit invalide ou ne appartenant pas à la boutique: {pid}', 'error')
            return redirect(url_for('commandes_new') + f"?boutique_id={boutique_id}")
        if produit.quantite is None or produit.quantite < q:
            flash(f'Stock insuffisant pour le produit {produit.nom}.', 'error')
            return redirect(url_for('commandes_new') + f"?boutique_id={boutique_id}")
        items.append((produit, q))
        total += produit.prix * q

    if not items:
        flash('Veuillez sélectionner au moins un produit (quantité > 0).', 'error')
        return redirect(url_for('commandes_new') + f"?boutique_id={boutique_id}")

    # create commande first and commit to obtain a stable ID, then create items
    try:
        commande = Commande(boutique_id=boutique_id, vendeur_id=vendeur_id, client_id=client_id, total=total)
        db.session.add(commande)
        db.session.commit()  # persist commande to get commande.id

        for produit, q in items:
            ci = CommandeItem(commande_id=commande.id, produit_id=produit.id, quantite=q, prix_unitaire=produit.prix)
            db.session.add(ci)
            produit.quantite = (produit.quantite or 0) - q
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('Erreur lors de l\'enregistrement de la commande.', 'error')
        return redirect(url_for('commandes_new') + f"?boutique_id={boutique_id}")
    flash('Commande enregistrée.', 'success')
    return redirect(url_for('commandes'))


@app.route('/factures/new', methods=['GET','POST'])
def factures_new():
    if request.method == 'GET':
        produit_id = request.args.get('produit_id')
        produit = None
        vendeurs = []
        # show all clients (we allow anonymous or any client)
        clients = Client.query.filter_by(supprime=False).all()
        if produit_id:
            produit = db.session.get(Produit, int(produit_id))
            if produit and produit.boutique:
                vendeurs = Vendeur.query.filter_by(boutique_id=produit.boutique.id, supprime=False).all()
        return render_template('factures_new.html', produit=produit, vendeurs=vendeurs, clients=clients)

    # POST: create invoice
    pid = int(request.form.get('produit_id') or 0)
    produit = db.session.get(Produit, pid)
    if produit is None:
        abort(404)

    # validate required fields
    vendeur_field = request.form.get('vendeur_id')
    prix_field = request.form.get('prix')
    if not vendeur_field or not prix_field:
        flash('Veuillez renseigner le vendeur et le prix pour enregistrer la facture.', 'error')
        return redirect(url_for('factures_new') + f"?produit_id={produit.id}")

    # validate vendeur exists
    try:
        vendeur_id = int(vendeur_field)
    except Exception:
        flash('Identifiant de vendeur invalide.', 'error')
        return redirect(url_for('factures_new') + f"?produit_id={produit.id}")
    vendeur = db.session.get(Vendeur, vendeur_id)
    if not vendeur:
        flash('Vendeur introuvable.', 'error')
        return redirect(url_for('factures_new') + f"?produit_id={produit.id}")

    # validate prix
    try:
        prix = float(prix_field)
        if prix <= 0:
            raise ValueError()
    except Exception:
        flash('Prix invalide. Entrez un nombre strictement positif.', 'error')
        return redirect(url_for('factures_new') + f"?produit_id={produit.id}")


    # client is now required (same rule as vendeur)
    client_field = request.form.get('client_id')
    if not client_field:
        flash('Veuillez renseigner le client pour enregistrer la facture.', 'error')
        return redirect(url_for('factures_new') + f"?produit_id={produit.id}")
    try:
        client_id = int(client_field)
    except Exception:
        flash('Identifiant de client invalide.', 'error')
        return redirect(url_for('factures_new') + f"?produit_id={produit.id}")
    client = db.session.get(Client, client_id)
    if not client:
        flash('Client introuvable.', 'error')
        return redirect(url_for('factures_new') + f"?produit_id={produit.id}")
    # check vendeur boutique coherence (if produit linked to a boutique)
    if produit.boutique and vendeur.boutique_id != produit.boutique.id:
        flash('Le vendeur sélectionné ne travaille pas dans la boutique de ce produit.', 'error')
        return redirect(url_for('factures_new') + f"?produit_id={produit.id}")

    # check stock
    if not produit.quantite or produit.quantite <= 0:
        flash('Stock insuffisant : ce produit est en rupture.', 'error')
        return redirect(url_for('view_boutique', id=produit.boutique.id if produit.boutique else 0))

    # create facture and decrement stock
    f = Facture(produit_id=produit.id, boutique_id=produit.boutique.id if produit.boutique else None, vendeur_id=vendeur_id, client_id=client_id, prix=prix)
    db.session.add(f)
    produit.quantite = (produit.quantite or 0) - 1
    db.session.commit()
    flash('Achat enregistré (facture créée).', 'success')
    return redirect(url_for('factures'))


@app.route('/bilan')
def bilan():
    produits = Produit.query.all()
    total = len(produits)
    # sold: invoices list
    sold_list = Facture.query.order_by(Facture.date.desc()).all()
    sold_ids = set(f.produit_id for f in sold_list)
    sold = len(sold_ids)
    remaining = total - sold
    remaining_list = [p for p in produits if p.id not in sold_ids]
    return render_template('bilan.html', total=total, sold=sold, remaining=remaining, sold_list=sold_list, remaining_list=remaining_list)


@app.route('/bilan/export')
def bilan_export():
    # export CSV with products and sold status
    import csv
    from io import StringIO
    produits = Produit.query.all()
    sold_counts = {}
    for f in Facture.query.all():
        sold_counts[f.produit_id] = sold_counts.get(f.produit_id, 0) + 1

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['produit_id', 'nom', 'categorie', 'prix', 'boutique', 'marche', 'quantite_restante', 'vendus'])
    for p in produits:
        writer.writerow([p.id, p.nom, p.categorie, p.prix, p.boutique.nom if p.boutique else '', p.marche or (p.boutique.marche if p.boutique else ''), p.quantite or 0, sold_counts.get(p.id, 0)])

    output = si.getvalue()
    return Response(output, mimetype='text/csv', headers={
        'Content-Disposition': 'attachment; filename="bilan.csv"'
    })


@app.route('/boutiques/delete/<int:id>')
def delete_boutique(id):
    b = db.session.get(Boutique, id)
    if b is None:
        abort(404)
    # restreindre suppression si vendeurs ou produits liés
    # vérifier explicitement s'il y a des produits liés pour éviter tout flou
    from sqlalchemy import func
    produit_count = Produit.query.filter_by(boutique_id=b.id).count()
    if b.vendeurs or produit_count > 0:
        flash('Impossible de supprimer: la boutique contient des vendeurs ou des produits. Supprimez-les d\'abord.', 'error')
        return redirect(url_for('boutiques'))
    # soft-delete: mark as supprime
    b.supprime = True
    db.session.commit()
    flash('Boutique marquée comme supprimée.', 'info')
    return redirect(url_for('boutiques'))


@app.route('/vendeurs', methods=['GET','POST'])
def vendeurs():
    if request.method == 'POST':
        nom = request.form.get('nom','').strip()
        telephone = request.form.get('telephone')
        boutique_id = request.form.get('boutique_id')
        # validation: nom and boutique_id required
        if not nom or not boutique_id:
            flash('Veuillez renseigner le nom du vendeur et sélectionner une boutique.', 'error')
            return redirect(url_for('vendeurs'))
        try:
            boutique_id = int(boutique_id)
        except Exception:
            flash('Identifiant de boutique invalide.', 'error')
            return redirect(url_for('vendeurs'))
        # check boutique exists
        if not db.session.get(Boutique, boutique_id):
            flash('La boutique sélectionnée n\'existe pas.', 'error')
            return redirect(url_for('vendeurs'))
        v = Vendeur(nom=nom, telephone=telephone, boutique_id=boutique_id)
        db.session.add(v)
        db.session.commit()
        flash(f"Vendeur '{nom}' ajouté.", 'success')
        return redirect(url_for('vendeurs'))

    all_boutiques = Boutique.query.filter_by(supprime=False).all()
    vendeurs = Vendeur.query.filter_by(supprime=False).all()
    return render_template('vendeurs.html', boutiques=all_boutiques, vendeurs=vendeurs)


@app.route('/vendeurs/edit/<int:id>', methods=['GET','POST'])
def edit_vendeur(id):
    v = db.session.get(Vendeur, id)
    if v is None:
        abort(404)
    if request.method == 'POST':
        nom = (request.form.get('nom') or '').strip()
        telephone = request.form.get('telephone')
        boutique_field = request.form.get('boutique_id')
        # validation
        if not nom or not boutique_field:
            flash('Veuillez renseigner le nom du vendeur et sélectionner une boutique.', 'error')
            return redirect(url_for('edit_vendeur', id=v.id))
        try:
            boutique_id = int(boutique_field)
        except Exception:
            flash('Identifiant de boutique invalide.', 'error')
            return redirect(url_for('edit_vendeur', id=v.id))
        if not db.session.get(Boutique, boutique_id):
            flash('La boutique sélectionnée n\'existe pas.', 'error')
            return redirect(url_for('edit_vendeur', id=v.id))
        v.nom = nom
        v.telephone = telephone
        v.boutique_id = boutique_id
        db.session.commit()
        flash('Vendeur mis à jour.', 'success')
        return redirect(url_for('vendeurs'))
    boutiques = Boutique.query.all()
    return render_template('vendeurs_edit.html', v=v, boutiques=boutiques)


@app.route('/vendeurs/delete/<int:id>')
def delete_vendeur(id):
    v = db.session.get(Vendeur, id)
    if v is None:
        abort(404)
    # soft-delete
    v.supprime = True
    db.session.commit()
    flash('Vendeur marqué comme supprimé.', 'info')
    return redirect(url_for('vendeurs'))


@app.route('/clients', methods=['GET','POST'])
def clients():
    if request.method == 'POST':
        nom = request.form.get('nom','').strip()
        contact = request.form.get('contact')
        boutique_id = request.form.get('boutique_id')
        # validation: nom required
        if not nom:
            flash('Veuillez renseigner le nom du client.', 'error')
            return redirect(url_for('clients'))
        if boutique_id:
            try:
                b_id = int(boutique_id)
            except Exception:
                flash('Identifiant de boutique invalide.', 'error')
                return redirect(url_for('clients'))
            # verify boutique exists
            if not db.session.get(Boutique, b_id):
                flash('La boutique sélectionnée n\'existe pas.', 'error')
                return redirect(url_for('clients'))
            client = Client(nom=nom, contact=contact, boutique_id=b_id)
        else:
            client = Client(nom=nom, contact=contact, boutique_id=None)
        db.session.add(client)
        db.session.commit()
        flash(f"Client '{nom}' ajouté.", 'success')
        return redirect(url_for('clients'))

    all_boutiques = Boutique.query.filter_by(supprime=False).all()
    clients = Client.query.filter_by(supprime=False).all()
    return render_template('clients.html', boutiques=all_boutiques, clients=clients)


@app.route('/clients/search', methods=['GET','POST'])
def client_search():
    clients = Client.query.all()
    results = []
    query = ''
    selected_client = None
    if request.method == 'POST':
        client_id = request.form.get('client_id')
        query = (request.form.get('query') or '').strip()
        if client_id:
            try:
                selected_client = db.session.get(Client, int(client_id))
            except Exception:
                selected_client = None

        if not query:
            flash('Veuillez saisir un nom de produit à rechercher.', 'error')
        else:
            # recherche insensible à la casse (partial match)
            results = Produit.query.filter(Produit.nom.ilike(f"%{query}%")).all()
            if not results:
                flash('Aucun produit trouvé pour la recherche.', 'info')

    return render_template('clients_search.html', clients=clients, results=results, query=query, client=selected_client)


@app.route('/clients/edit/<int:id>', methods=['GET','POST'])
def edit_client(id):
    c = db.session.get(Client, id)
    if c is None:
        abort(404)
    if request.method == 'POST':
        nom = (request.form.get('nom') or '').strip()
        contact = request.form.get('contact')
        boutique_field = request.form.get('boutique_id')
        if not nom:
            flash('Veuillez renseigner le nom du client.', 'error')
            return redirect(url_for('edit_client', id=c.id))
        if boutique_field:
            try:
                b_id = int(boutique_field)
            except Exception:
                flash('Identifiant de boutique invalide.', 'error')
                return redirect(url_for('edit_client', id=c.id))
            if not db.session.get(Boutique, b_id):
                flash('La boutique sélectionnée n\'existe pas.', 'error')
                return redirect(url_for('edit_client', id=c.id))
            c.boutique_id = b_id
        else:
            c.boutique_id = None
        c.nom = nom
        c.contact = contact
        db.session.commit()
        flash('Client mis à jour.', 'success')
        return redirect(url_for('clients'))
    boutiques = Boutique.query.all()
    return render_template('clients_edit.html', c=c, boutiques=boutiques)


@app.route('/clients/delete/<int:id>')
def delete_client(id):
    c = db.session.get(Client, id)
    if c is None:
        abort(404)
    # soft-delete
    c.supprime = True
    db.session.commit()
    flash('Client marqué comme supprimé.', 'info')
    return redirect(url_for('clients'))


@app.route('/stats.svg')
def stats_svg():
    # Générer un graphique SVG simple (barres) sans dépendances externes
    # n'inclure que les produits non supprimés pour que les suppressions impactent le graphe
    produits = Produit.query.filter_by(supprime=False).all()
    stats = {}
    for p in produits:
        stats[p.categorie] = stats.get(p.categorie, 0) + 1

    labels = list(stats.keys())
    counts = list(stats.values())

    if not labels:
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="140"><text x="10" y="20">Aucun produit enregistr\u00e9</text></svg>'
        return Response(svg, mimetype='image/svg+xml')

    # Dimensions et marges
    width = 800
    height = 360
    margin_left = 70
    margin_right = 30
    margin_top = 30
    margin_bottom = 70

    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    max_count = max(counts) if counts else 1

    n = len(counts)
    # barre pleine adjacente (histogramme)
    bar_width = plot_width / n

    # Palette
    colors = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF']

    # Graduations Y
    y_steps = max(3, min(10, max_count))
    # choisir un step arrondi
    step = max(1, int((max_count + y_steps - 1) / y_steps))
    y_ticks = list(range(0, max_count + step, step))

    # Construire les barres et labels
    bars = []
    for i, c in enumerate(counts):
        x = margin_left + i * bar_width
        h = (c / max_count) * plot_height if max_count else 0
        y = margin_top + (plot_height - h)
        color = colors[i % len(colors)]
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width - 4:.1f}" height="{h:.1f}" fill="{color}" stroke="#333" stroke-width="0.5"/>')
        # valeur au-dessus
        bars.append(f'<text x="{x + (bar_width-4)/2:.1f}" y="{y - 6:.1f}" font-size="12" text-anchor="middle">{c}</text>')
        # label categorie sous l'axe
        bars.append(f'<text x="{x + (bar_width-4)/2:.1f}" y="{margin_top + plot_height + 22:.1f}" font-size="12" text-anchor="middle">{labels[i]}</text>')

    # Lignes de grille et graduations Y
    grid_lines = []
    for t in y_ticks:
        yy = margin_top + plot_height - (t / max_count) * plot_height if max_count else margin_top + plot_height
        grid_lines.append(f'<line x1="{margin_left}" y1="{yy:.1f}" x2="{width - margin_right}" y2="{yy:.1f}" stroke="#ddd" stroke-width="1"/>')
        grid_lines.append(f'<text x="{margin_left - 10:.1f}" y="{yy + 4:.1f}" font-size="12" text-anchor="end">{t}</text>')

    # Axe X et Y
    axis = []
    axis.append(f'<line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{width - margin_right}" y2="{margin_top + plot_height}" stroke="#000"/>')
    axis.append(f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#000"/>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
    <style>text{{font-family: sans-serif;}}</style>
    <rect width="100%" height="100%" fill="#fff"/>
    <!-- grille -->
    {''.join(grid_lines)}
    <!-- barres -->
    {''.join(bars)}
    <!-- axes -->
    {''.join(axis)}
    <!-- titre -->
    <text x="{width/2:.1f}" y="20" font-size="16" text-anchor="middle">Nombre de produits par catégorie</text>
    <!-- label axe Y -->
    <text x="20" y="{margin_top + plot_height/2:.1f}" font-size="12" text-anchor="middle" transform="rotate(-90,20,{margin_top + plot_height/2:.1f})">Nombre</text>
    </svg>'''

    resp = Response(svg, mimetype='image/svg+xml')
    # prevent aggressive browser caching of the generated SVG so updates appear immediately
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp
    

@app.route('/stats_pie.svg')
def stats_pie_svg():
    # catégories des produits vendus -> pourcentages
    from collections import Counter
    produits = Produit.query.filter_by(supprime=False).all()
    sold_ids = set(f.produit_id for f in Facture.query.all())
    cat_counts = Counter()
    total_sold = 0
    for p in produits:
        if p.id in sold_ids:
            cat_counts[p.categorie or 'Autre'] += 1
            total_sold += 1

    if total_sold == 0:
        # fallback: use product counts per category so the pie is still informative
        cat_counts = Counter()
        total_products = 0
        for p in produits:
            cat_counts[p.categorie or 'Autre'] += 1
            total_products += 1
        if total_products == 0:
            svg = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><text x="10" y="20">Aucun produit ni vente enregistr\u00e9</text></svg>'
            return Response(svg, mimetype='image/svg+xml')
        # switch to using product distribution
        total_sold = total_products
        # overwrite cat_counts from sold-based counts
        # (already computed above)

    # calcul des arcs
    import math
    cx, cy, r = 150, 100, 80
    start_angle = 0.0
    colors = ['#4caf50','#2196f3','#ff9800','#9c27b0','#f44336','#03a9f4','#8bc34a']
    parts = []
    legend = []
    i = 0
    for cat, cnt in cat_counts.items():
        frac = cnt / total_sold
        angle = frac * 360.0
        end_angle = start_angle + angle
        x1 = cx + r * math.cos(math.radians(start_angle))
        y1 = cy + r * math.sin(math.radians(start_angle))
        x2 = cx + r * math.cos(math.radians(end_angle))
        y2 = cy + r * math.sin(math.radians(end_angle))
        large = 1 if angle > 180 else 0
        path = f'M {cx},{cy} L {x1:.2f},{y1:.2f} A {r},{r} 0 {large},1 {x2:.2f},{y2:.2f} Z'
        color = colors[i % len(colors)]
        parts.append(f'<path d="{path}" fill="{color}" stroke="#fff"/>')
        legend.append((color, f"{cat} ({int(frac*100)}%)"))
        start_angle = end_angle
        i += 1

    svg_parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="240">']
    svg_parts.append('<g>')
    svg_parts.extend(parts)
    svg_parts.append('</g>')
    # legend
    lx = 320
    ly = 40
    for idx, (color, label) in enumerate(legend):
        svg_parts.append(f'<rect x="{lx}" y="{ly + idx*20 -10}" width="12" height="12" fill="{color}" />')
        svg_parts.append(f'<text x="{lx+18}" y="{ly + idx*20}" font-size="12">{label}</text>')

    svg_parts.append('</svg>')
    svg = '\n'.join(svg_parts)
    return Response(svg, mimetype='image/svg+xml')
    


@app.route('/analyse')
def analyse():
    produits = Produit.query.filter_by(supprime=False).order_by(Produit.date_enregistrement.desc()).all()
    # recalcul des stats
    stats = {}
    for p in produits:
        stats[p.categorie] = stats.get(p.categorie, 0) + 1
    # add a timestamp to force the browser to reload the SVG when data changes
    ts = int(time.time())
    return render_template('analyse.html', produits=produits, stats=stats, ts=ts)


@app.route('/registre')
def registre():
    # list registered marketplaces and provide links to the registries
    try:
        marches = [m.nom for m in Marche.query.filter_by(supprime=False).order_by(Marche.nom).all()]
    except Exception:
        marches = sorted(list(set([p.marche for p in Produit.query.filter_by(supprime=False).all() if p.marche] + [b.marche for b in Boutique.query.filter_by(supprime=False).all() if b.marche])))
    return render_template('registre.html', marches=marches)


@app.route('/enregistrer_marche', methods=['POST'])
def enregistrer_marche():
    nom = (request.form.get('marche') or '').strip()
    if not nom:
        flash('Nom de marché vide.', 'error')
        return redirect(url_for('home'))
    try:
        # check existing non-deleted
        existing = None
        try:
            existing = Marche.query.filter_by(nom=nom, supprime=False).first()
        except Exception:
            existing = None
        if existing:
            flash('Ce marché est déjà enregistré.', 'info')
            return redirect(url_for('home'))
        m = Marche(nom=nom)
        db.session.add(m)
        db.session.commit()
        flash(f"Marché '{nom}' enregistré.", 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erreur lors de l\'enregistrement du marché.', 'error')
    return redirect(url_for('home'))

if __name__ == '__main__':
    # Disable debug by default in production; enable via FLASK_DEBUG=1 or 'true'
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    app.run(debug=debug)
