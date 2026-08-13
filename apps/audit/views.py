"""
Page « Audit & Logs » du back-office : restitution du journal d'audit.

Cette page est la partie VISIBLE du dispositif : elle ne journalise rien, elle
CONSOMME `apps.audit.models.AuditLog`, alimenté par les vues, les signaux et le
middleware.

Deux vues :
- `AuditLogListView`   : la liste filtrable (/gestion/audit/) ;
- `AuditLogDetailView` : le détail d'une entrée (/gestion/audit/<pk>/).

Parti pris de lisibilité : rien de technique n'apparaît à l'écran. Les noms de
champs bruts (`unit_price`) sont traduits par le `verbose_name` du modèle
(« Prix unitaire »), les valeurs à choix par les libellés déjà figés dans
`extra["libelles"]` par les vues du back-office, et `extra` est déplié en
lignes lisibles plutôt qu'affiché en JSON.
"""
import re
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView

from apps.sample.mixins import GestionLayoutMixin, StaffRequiredMixin

from .forms import AuditFilterForm
from .models import AuditLog

# ———————————————————————————————————————————————————————————————————————————
# Tables d'affichage
# ———————————————————————————————————————————————————————————————————————————

# Pastille de couleur par action (classes Vuexy « bg-label-* », comme historique.html).
# Le violet de Vuexy est la couleur « primary » : elle est réservée ici au
# changement de permissions, l'événement le plus sensible du journal.
ACTION_BADGES = {
    AuditLog.Action.CREATE: "bg-label-success",
    AuditLog.Action.UPDATE: "bg-label-info",
    AuditLog.Action.DELETE: "bg-label-danger",
    AuditLog.Action.LOGIN: "bg-label-secondary",
    AuditLog.Action.LOGOUT: "bg-label-secondary",
    AuditLog.Action.LOGIN_FAILED: "bg-label-warning",
    AuditLog.Action.STATUS_CHANGE: "bg-label-dark",
    AuditLog.Action.PERMISSION_CHANGE: "bg-label-primary",
    AuditLog.Action.EXPORT: "bg-label-dark",
    AuditLog.Action.OTHER: "bg-label-secondary",
}

ACTION_ICONS = {
    AuditLog.Action.CREATE: "ti ti-plus",
    AuditLog.Action.UPDATE: "ti ti-edit",
    AuditLog.Action.DELETE: "ti ti-trash",
    AuditLog.Action.LOGIN: "ti ti-login",
    AuditLog.Action.LOGOUT: "ti ti-logout",
    AuditLog.Action.LOGIN_FAILED: "ti ti-alert-triangle",
    AuditLog.Action.STATUS_CHANGE: "ti ti-exchange",
    AuditLog.Action.PERMISSION_CHANGE: "ti ti-shield-lock",
    AuditLog.Action.EXPORT: "ti ti-download",
    AuditLog.Action.OTHER: "ti ti-point",
}

# Libellés français des clés de `extra` posées par le reste de l'application.
# Toute clé inconnue est simplement « déminifiée » (underscores → espaces).
EXTRA_LABELS = {
    "valeurs": "Valeurs enregistrées",
    "evenement": "Événement",
    "motif": "Motif",
    "identifiant_tente": "Identifiant saisi",
    "compte_utilisateur_cree": "Compte de connexion créé",
    "compte_utilisateur_supprime": "Compte de connexion supprimé",
    "profil_client_supprime": "Fiche client supprimée",
    "email": "Email",
    "groups": "Rôles",
    "permissions": "Permissions",
    "user_permissions": "Permissions individuelles",
}

# Clés de `extra` purement techniques : elles servent à traduire les
# modifications, les afficher en plus ferait doublon.
EXTRA_KEYS_MASQUEES = ("libelles",)

# Nombre de modifications reprises dans le résumé de la liste.
RESUME_MAX = 3

# Une valeur décimale figée par le journal (« 150000.00 »).
_DECIMAL_TEXTE = re.compile(r"^-?\d+\.\d+$")

# Espace insécable : « 150 000 » ne doit jamais se couper en fin de ligne.
_ESPACE_MILLIERS = " "


# ———————————————————————————————————————————————————————————————————————————
# Petits utilitaires de mise en français
# ———————————————————————————————————————————————————————————————————————————

def _majuscule(texte):
    """Première lettre en capitale, sans toucher au reste (contrairement à capitalize())."""
    texte = str(texte or "")
    return texte[:1].upper() + texte[1:]


def _modele_de(content_type):
    """
    Classe du modèle concerné, ou None.

    `content_type` est nul pour une connexion, et `model_class()` peut renvoyer
    None si le modèle n'existe plus dans le code : les deux cas sont normaux.
    Aucune requête n'est déclenchée (le registre des applications est en mémoire).
    """
    if content_type is None:
        return None
    try:
        return content_type.model_class()
    except Exception:  # noqa: BLE001 - un journal illisible vaut mieux qu'une page en erreur
        return None


def libelle_champ(modele, nom):
    """
    Nom lisible d'un champ : « unit_price » → « Prix unitaire ».

    On s'appuie sur le `verbose_name` déjà défini (et déjà en français) dans les
    modèles. Repli sur le nom déminifié pour les clés synthétiques du journal
    (ex. « compte_email » posé par la photo d'un client).
    """
    if modele is not None:
        try:
            return _majuscule(modele._meta.get_field(nom).verbose_name)
        except Exception:  # noqa: BLE001 - champ renommé ou supprimé depuis
            pass
    return _majuscule(str(nom).replace("_", " "))


def embellir(valeur):
    """
    « 150000.00 » → « 150 000 », « 150000.50 » → « 150 000,50 ».

    Volontairement limité aux valeurs décimales (chiffres + point + décimales),
    c'est-à-dire à ce que produit un DecimalField : on ne veut surtout pas
    reformater un numéro de téléphone ou une référence produit.
    """
    if not isinstance(valeur, str):
        return valeur
    brut = valeur.strip()
    if not _DECIMAL_TEXTE.match(brut):
        return valeur
    try:
        nombre = Decimal(brut)
    except (InvalidOperation, ValueError):
        return valeur
    entier = int(nombre)
    milliers = f"{entier:,}".replace(",", _ESPACE_MILLIERS)
    decimales = format(abs(nombre - entier), "f").split(".")[1]
    if int(decimales) == 0:
        return milliers
    return f"{milliers},{decimales}"


def _texte(valeur):
    """Valeur brute du journal rendue en texte lisible, puis embellie."""
    return embellir(AuditLog._format_valeur(valeur))


# ———————————————————————————————————————————————————————————————————————————
# Traduction d'une entrée pour les gabarits
# ———————————————————————————————————————————————————————————————————————————

def changements_lisibles(entree):
    """
    Liste des modifications, prête à afficher :

        [{"champ": "Prix unitaire", "avant": "150 000", "apres": "180 000"}]

    On part de `AuditLog.changes_display` (fourni par le modèle) et on enrichit :
    - le nom du champ devient son libellé métier ;
    - si les vues du back-office ont figé la traduction d'un champ à choix dans
      `extra["libelles"]` (« pending » → « En attente »), elle est préférée à la
      valeur technique.
    """
    modele = _modele_de(entree.content_type)
    traductions = entree.extra.get("libelles") if isinstance(entree.extra, dict) else None
    if not isinstance(traductions, dict):
        traductions = {}

    lignes = []
    for ligne in entree.changes_display:
        champ = ligne["champ"]
        traduction = traductions.get(champ)
        if isinstance(traduction, dict):
            avant = _texte(traduction.get("avant"))
            apres = _texte(traduction.get("apres"))
        else:
            avant = embellir(ligne["avant"])
            apres = embellir(ligne["apres"])
        lignes.append({"champ": libelle_champ(modele, champ), "avant": avant, "apres": apres})
    return lignes


def contexte_lisible(entree):
    """
    Contenu de `extra` déplié en blocs affichables.

    C'est indispensable : certaines entrées n'ont AUCUNE modification et portent
    toute l'information ici (changement de mot de passe, identifiant tenté lors
    d'un échec de connexion, photo complète d'un objet supprimé).

    Chaque bloc vaut soit {"titre", "valeur"} (une information simple), soit
    {"titre", "lignes"} (un sous-tableau champ/valeur).
    """
    extra = entree.extra if isinstance(entree.extra, dict) else {}
    modele = _modele_de(entree.content_type)
    blocs = []
    for cle, valeur in extra.items():
        if cle in EXTRA_KEYS_MASQUEES:
            continue
        titre = EXTRA_LABELS.get(cle) or _majuscule(str(cle).replace("_", " "))
        if isinstance(valeur, dict):
            lignes = [
                {"champ": libelle_champ(modele, sous_cle), "valeur": _texte(sous_valeur)}
                for sous_cle, sous_valeur in valeur.items()
            ]
            if lignes:
                blocs.append({"titre": titre, "lignes": lignes, "valeur": None})
        else:
            blocs.append({"titre": titre, "lignes": None, "valeur": _texte(valeur)})
    return blocs


def resume_lisible(entree):
    """
    Résumé d'une ligne de liste : « Prix unitaire : 150 000 → 180 000 ».

    Si l'entrée n'a pas de modification, on retombe sur la première information
    de `extra` : une ligne du journal ne doit jamais paraître vide de sens.
    """
    if entree.modifications:
        extrait = " ; ".join(
            f"{ligne['champ']} : {ligne['avant']} → {ligne['apres']}"
            for ligne in entree.modifications[:RESUME_MAX]
        )
        reste = len(entree.modifications) - RESUME_MAX
        if reste > 0:
            return f"{extrait} … (+{reste})"
        return extrait
    for bloc in entree.contexte:
        if bloc["valeur"]:
            return f"{bloc['titre']} : {bloc['valeur']}"
        if bloc["lignes"]:
            nombre = len(bloc["lignes"])
            return f"{bloc['titre']} : {nombre} information{'s' if nombre > 1 else ''}"
    return ""


def preparer_entree(entree):
    """
    Attache à une entrée tout ce dont les gabarits ont besoin.

    Fait en Python plutôt qu'en balises de gabarit : la logique reste testable et
    le HTML lisible. Aucune requête supplémentaire n'est déclenchée ici.
    """
    entree.pastille = ACTION_BADGES.get(entree.action, "bg-label-secondary")
    entree.icone = ACTION_ICONS.get(entree.action, "ti ti-point")
    entree.modifications = changements_lisibles(entree)
    entree.contexte = contexte_lisible(entree)
    entree.resume = resume_lisible(entree)
    # Auteur disparu : le compte a été supprimé mais le libellé figé subsiste.
    # Un échec de connexion n'a jamais d'auteur : ce n'est pas un compte supprimé.
    entree.compte_supprime = (
        entree.actor_id is None
        and bool(entree.actor_label)
        and entree.action != AuditLog.Action.LOGIN_FAILED
    )
    return entree


def _debut_de_journee(jour):
    """Minuit (heure locale) du jour donné, en datetime conscient du fuseau."""
    instant = datetime.combine(jour, time.min)
    if timezone.is_naive(instant):
        instant = timezone.make_aware(instant, timezone.get_current_timezone())
    return instant


# ———————————————————————————————————————————————————————————————————————————
# Vues
# ———————————————————————————————————————————————————————————————————————————

class AuditLogListView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, ListView):
    """
    Journal d'audit filtrable.

    Les filtres se cumulent (ET logique) et sont conservés dans les liens de
    pagination via `parametres` : changer de page ne remet jamais la liste à zéro.
    """

    permission_required = "audit.view_auditlog"
    raise_exception = True
    model = AuditLog
    template_name = "admin/gestion/audit_list.html"
    context_object_name = "entrees"
    paginate_by = 25

    def get_filtres(self):
        """Formulaire de filtres, construit une seule fois par requête."""
        if not hasattr(self, "_filtres"):
            # `or None` : sans paramètre dans l'URL, le formulaire est non lié et
            # n'affiche donc aucune erreur au premier affichage de la page.
            self._filtres = AuditFilterForm(self.request.GET or None)
            self._filtres.is_valid()  # peuple cleaned_data
        return self._filtres

    def get_queryset(self):
        # select_related : sans lui, l'auteur et le type d'objet coûteraient
        # deux requêtes PAR LIGNE affichée.
        queryset = AuditLog.objects.select_related("actor", "content_type").order_by("-created_at")
        donnees = self.get_filtres().valeurs

        auteur = donnees.get("auteur")
        if auteur:
            queryset = queryset.filter(actor=auteur)  # index (actor, -created_at)

        action = donnees.get("action")
        if action:
            queryset = queryset.filter(action=action)  # index (action, -created_at)

        # Bornes de dates traduites en intervalle de datetimes : un filtre sur
        # `created_at__date` empêcherait l'utilisation de l'index created_at.
        debut = donnees.get("debut")
        if debut:
            queryset = queryset.filter(created_at__gte=_debut_de_journee(debut))
        fin = donnees.get("fin")
        if fin:
            queryset = queryset.filter(created_at__lt=_debut_de_journee(fin + timedelta(days=1)))

        recherche = (donnees.get("q") or "").strip()
        if recherche:
            queryset = queryset.filter(
                Q(object_repr__icontains=recherche) | Q(actor_label__icontains=recherche)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # La page est déjà chargée en mémoire : préparer chaque entrée ne coûte
        # aucune requête supplémentaire.
        entrees = [preparer_entree(entree) for entree in context["object_list"]]
        context["object_list"] = entrees
        context["entrees"] = entrees

        filtres = self.get_filtres()
        context["filtres"] = filtres
        context["filtres_actifs"] = filtres.actifs
        # Paramètres à recoller aux liens de pagination (tout sauf « page »).
        parametres = self.request.GET.copy()
        parametres.pop("page", None)
        context["parametres"] = parametres.urlencode()
        # Querystring complète (filtres + page) pour revenir au bon endroit
        # depuis la page de détail.
        context["retour"] = self.request.GET.urlencode()
        return context


class AuditLogDetailView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, DetailView):
    """
    Détail d'une entrée du journal.

    Page dédiée plutôt que dépliage dans la liste : une suppression conserve la
    photo COMPLÈTE de l'objet dans `extra["valeurs"]` (souvent une quinzaine de
    lignes). Déplier cela dans le tableau alourdirait chaque page de 25 entrées
    et rendrait la lecture pénible ; une page dédiée reste par ailleurs
    partageable par simple URL, ce qui compte en cas d'incident.
    """

    permission_required = "audit.view_auditlog"
    raise_exception = True
    model = AuditLog
    template_name = "admin/gestion/audit_detail.html"
    context_object_name = "entree"

    def get_queryset(self):
        return AuditLog.objects.select_related("actor", "content_type")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entree = preparer_entree(context["entree"])
        # Une entrée ne doit jamais paraître vide : si elle n'a ni modification
        # ni contexte, le gabarit explique que le fait, c'est l'action elle-même.
        context["sans_detail"] = not entree.modifications and not entree.contexte
        # Retour à la liste en conservant filtres ET numéro de page.
        parametres = self.request.GET.urlencode()
        context["retour_liste"] = reverse("gestion:audit-list") + (
            f"?{parametres}" if parametres else ""
        )
        return context
