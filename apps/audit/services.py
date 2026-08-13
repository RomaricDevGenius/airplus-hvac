"""
API du journal d'audit — c'est le SEUL point d'entrée à utiliser depuis les vues,
les services métier et les signaux.

Règle d'or : journaliser ne doit JAMAIS faire échouer l'action métier.
`log_action()` avale toutes ses exceptions et se contente d'écrire dans le
logger « audit ». Si le journal casse, on supprime quand même le produit.

Utilisation type dans une vue du back-office :

    from apps.audit.services import capture, diff, log_action
    from apps.audit.models import AuditLog

    # --- Création ---
    produit = form.save()
    log_action(AuditLog.Action.CREATE, request=request, obj=produit)

    # --- Modification ---
    avant = capture(produit)                 # AVANT le form.save()
    produit = form.save()
    log_action(AuditLog.Action.UPDATE, request=request, obj=produit,
               changes=diff(avant, capture(produit)))

    # --- Suppression ---
    log_action(AuditLog.Action.DELETE, request=request, obj=produit,
               changes=None, extra={"valeurs": capture(produit)})
    produit.delete()                          # journaliser AVANT la suppression
"""
import logging
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.validators import validate_ipv46_address
from django.db import models
from django.utils.duration import duration_string
from django.utils.functional import Promise

logger = logging.getLogger("audit")

# ---------------------------------------------------------------------------
# Confidentialité : ces fragments de nom de champ ne sont JAMAIS journalisés.
# La comparaison est faite en minuscules, par inclusion (« password » attrape
# « password », « password1 », « old_password », « user_password »...).
# ---------------------------------------------------------------------------
SENSITIVE_FIELD_MARKERS = (
    "password",
    "passwd",
    "mot_de_passe",
    "token",
    "secret",
    "api_key",
    "apikey",
    "private_key",
    "signature",
    "session",
    "csrf",
    "salt",
    "otp",
    "cvv",
    "card_number",
    "carte_bancaire",
    "iban",
    "security_answer",
)

# Champs techniques sans intérêt pour un lecteur du journal.
DEFAULT_EXCLUDED_FIELDS = ("id", "pk", "created_at", "updated_at", "last_login")

# Valeur affichée à la place d'une donnée sensible (on trace le fait, pas la valeur).
MASKED_VALUE = "********"

# Longueurs maximales alignées sur le modèle AuditLog.
MAX_ACTOR_LABEL = 255
MAX_OBJECT_ID = 64
MAX_OBJECT_REPR = 255
MAX_USER_AGENT = 400


# ---------------------------------------------------------------------------
# Helpers confidentialité / sérialisation
# ---------------------------------------------------------------------------

def is_sensitive_field(name):
    """True si le nom de champ ressemble à une donnée confidentielle."""
    if not name:
        return False
    minuscule = str(name).lower()
    return any(marqueur in minuscule for marqueur in SENSITIVE_FIELD_MARKERS)


def to_jsonable(value, _profondeur=0):
    """
    Convertit n'importe quelle valeur Python en quelque chose que JSONField
    sait stocker : Decimal -> str, date/datetime/time -> ISO, UUID -> str,
    fichier -> nom du fichier, instance de modèle -> str(), etc.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return duration_string(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Promise):  # chaînes traduites paresseuses
        return str(value)
    if isinstance(value, File):  # ImageField / FileField
        return value.name or ""
    if isinstance(value, models.Model):
        return str(value)
    if _profondeur >= 3:  # garde-fou contre les structures profondes/cycliques
        return str(value)
    if isinstance(value, dict):
        return {
            str(cle): (MASKED_VALUE if is_sensitive_field(cle) else to_jsonable(val, _profondeur + 1))
            for cle, val in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(v, _profondeur + 1) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


# ---------------------------------------------------------------------------
# Photographie d'une instance et calcul du delta
# ---------------------------------------------------------------------------

def capture(instance, fields=None, exclude=None):
    """
    Photographie les valeurs des champs concrets d'une instance, sous forme
    d'un dict sérialisable JSON : {"nom_du_champ": valeur}.

    - Les clés étrangères sont rendues en texte (str de l'objet lié).
    - Les many-to-many sont ignorés (nécessitent une requête et un objet déjà en base).
    - Les champs sensibles (password, token...) sont totalement omis.

    :param instance: instance de modèle Django (ou None -> {}).
    :param fields: itérable de noms de champs à photographier (par défaut : tous).
    :param exclude: itérable de noms de champs à ignorer en plus des exclusions
                    par défaut (id, created_at, updated_at, last_login).
    """
    if instance is None:
        return {}

    exclusions = set(DEFAULT_EXCLUDED_FIELDS) | set(exclude or ())
    demandes = set(fields) if fields else None
    photo = {}

    try:
        champs = instance._meta.concrete_fields
    except AttributeError:
        logger.warning("audit.capture : objet non-modèle reçu (%r)", type(instance))
        return {}

    for champ in champs:
        nom = champ.name
        if demandes is not None and nom not in demandes:
            continue
        if demandes is None and nom in exclusions:
            continue
        if is_sensitive_field(nom) or is_sensitive_field(champ.attname):
            continue
        try:
            if champ.is_relation:
                # str() de l'objet lié si disponible, sinon la clé brute.
                lie = getattr(instance, nom, None)
                photo[nom] = str(lie) if lie is not None else None
            else:
                photo[nom] = to_jsonable(getattr(instance, nom, None))
        except Exception:  # noqa: BLE001 - un champ illisible ne doit pas casser la photo
            logger.debug("audit.capture : champ « %s » illisible", nom, exc_info=True)
            photo[nom] = None
    return photo


def diff(before, after):
    """
    Compare deux photos et ne retient que ce qui a réellement changé.

    :return: {"nom_du_champ": {"avant": <valeur>, "apres": <valeur>}}
    """
    before = before or {}
    after = after or {}
    resultat = {}
    for cle in list(before.keys()) + [c for c in after.keys() if c not in before]:
        if is_sensitive_field(cle):
            continue
        avant = to_jsonable(before.get(cle))
        apres = to_jsonable(after.get(cle))
        if avant != apres:
            resultat[cle] = {"avant": avant, "apres": apres}
    return resultat


# ---------------------------------------------------------------------------
# Contexte HTTP
# ---------------------------------------------------------------------------

def get_client_ip(request):
    """
    IP réelle du visiteur. Le site tourne derrière Apache/Passenger (o2switch) :
    on lit HTTP_X_FORWARDED_FOR en priorité et on prend la première adresse
    (le client d'origine), en repli sur REMOTE_ADDR.
    """
    if request is None:
        return None
    meta = getattr(request, "META", {}) or {}
    candidates = []
    transmis = meta.get("HTTP_X_FORWARDED_FOR", "")
    if transmis:
        candidates.extend(part.strip() for part in transmis.split(","))
    candidates.append((meta.get("HTTP_X_REAL_IP") or "").strip())
    candidates.append((meta.get("REMOTE_ADDR") or "").strip())

    for adresse in candidates:
        if not adresse:
            continue
        # Retire un éventuel port (« 1.2.3.4:5678 ») ou des crochets IPv6.
        if adresse.count(":") == 1 and "." in adresse:
            adresse = adresse.split(":", 1)[0]
        adresse = adresse.strip("[]")
        try:
            validate_ipv46_address(adresse)
        except ValidationError:
            continue
        return adresse
    return None


def get_user_agent(request):
    """User-agent tronqué à la taille du champ du modèle."""
    if request is None:
        return ""
    return (getattr(request, "META", {}) or {}).get("HTTP_USER_AGENT", "")[:MAX_USER_AGENT]


def build_actor_label(user):
    """
    Instantané lisible de l'acteur : « Prénom Nom (email) », à défaut le
    username, à défaut « Système ».
    """
    if user is None:
        return ""
    nom = ""
    try:
        nom = (user.get_full_name() or "").strip()
    except Exception:  # noqa: BLE001
        nom = ""
    identifiant = (
        getattr(user, "email", "")
        or getattr(user, "username", "")
        or str(user)
    )
    libelle = f"{nom} ({identifiant})" if nom and identifiant else (nom or identifiant)
    return libelle[:MAX_ACTOR_LABEL]


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def log_action(
    action,
    request=None,
    actor=None,
    obj=None,
    changes=None,
    extra=None,
    object_repr=None,
    actor_label=None,
):
    """
    Écrit une entrée dans le journal d'audit. Ne lève JAMAIS d'exception.

    :param action: valeur de AuditLog.Action (ou la chaîne équivalente : "create"...).
    :param request: HttpRequest, pour déduire l'acteur, l'IP et le user-agent.
    :param actor: utilisateur explicite (prioritaire sur request.user).
    :param obj: instance concernée, pour déduire content_type / object_id / object_repr.
    :param changes: dict au format {"champ": {"avant": ..., "apres": ...}}, typiquement
                    produit par diff(capture(avant), capture(apres)).
    :param extra: dict de contexte libre (motif, URL, identifiant tenté...).
    :param object_repr: libellé de l'objet à figer (par défaut str(obj)).
    :param actor_label: libellé d'acteur forcé — utile pour un échec de connexion
                        où aucun utilisateur n'est authentifié.
    :return: l'instance AuditLog créée, ou None en cas d'échec (jamais d'exception).
    """
    try:
        # Imports locaux : évite tout souci d'ordre de chargement des applications.
        from django.contrib.contenttypes.models import ContentType

        from .middleware import get_current_request
        from .models import AuditLog

        if request is None:
            request = get_current_request()

        # --- Acteur ---
        if actor is None and request is not None:
            candidat = getattr(request, "user", None)
            if candidat is not None and getattr(candidat, "is_authenticated", False):
                actor = candidat
        if actor is not None and not getattr(actor, "pk", None):
            actor = None  # AnonymousUser ou instance non enregistrée

        libelle_acteur = actor_label or build_actor_label(actor)

        # --- Objet concerné ---
        content_type = None
        object_id = ""
        libelle_objet = object_repr or ""
        if obj is not None:
            try:
                content_type = ContentType.objects.get_for_model(obj, for_concrete_model=True)
            except Exception:  # noqa: BLE001
                logger.debug("audit : content_type introuvable pour %r", type(obj), exc_info=True)
            pk = getattr(obj, "pk", None)
            object_id = "" if pk is None else str(pk)[:MAX_OBJECT_ID]
            if not libelle_objet:
                try:
                    libelle_objet = str(obj)
                except Exception:  # noqa: BLE001
                    libelle_objet = f"{type(obj).__name__}#{object_id}"
        libelle_objet = (libelle_objet or "")[:MAX_OBJECT_REPR]

        # --- Détail (toujours sérialisable et expurgé) ---
        changes_json = to_jsonable(changes) if changes else {}
        if not isinstance(changes_json, dict):
            changes_json = {}
        # Filet de sécurité : même si l'appelant passe un `changes` fabriqué à la
        # main, un champ sensible n'entre jamais dans le journal (diff() applique
        # déjà la même règle).
        changes_json = {
            cle: valeur for cle, valeur in changes_json.items() if not is_sensitive_field(cle)
        }
        extra_json = to_jsonable(extra) if extra else {}
        if not isinstance(extra_json, dict):
            extra_json = {"valeur": extra_json}

        return AuditLog.objects.create(
            action=str(getattr(action, "value", action))[:32],
            actor=actor,
            actor_label=libelle_acteur,
            content_type=content_type,
            object_id=object_id,
            object_repr=libelle_objet,
            changes=changes_json,
            extra=extra_json,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
    except Exception:  # noqa: BLE001 - un audit cassé ne doit jamais bloquer le métier
        logger.exception("audit : échec d'écriture du journal (action=%r, obj=%r)", action, obj)
        return None


# ---------------------------------------------------------------------------
# Raccourcis de confort (facultatifs, ils appellent tous log_action)
# ---------------------------------------------------------------------------

def log_create(obj, request=None, actor=None, extra=None):
    """Journalise la création de `obj`."""
    from .models import AuditLog

    return log_action(AuditLog.Action.CREATE, request=request, actor=actor, obj=obj, extra=extra)


def log_update(obj, before, after=None, request=None, actor=None, extra=None):
    """
    Journalise la modification de `obj`.
    `before` est la photo prise AVANT l'enregistrement (capture(obj)) ;
    `after` est calculée automatiquement si elle n'est pas fournie.
    """
    from .models import AuditLog

    if after is None:
        after = capture(obj)
    modifications = diff(before, after)
    if not modifications:
        return None  # rien n'a changé : pas de bruit dans le journal
    return log_action(
        AuditLog.Action.UPDATE,
        request=request,
        actor=actor,
        obj=obj,
        changes=modifications,
        extra=extra,
    )


def log_delete(obj, request=None, actor=None, extra=None):
    """
    Journalise la suppression de `obj`. À appeler AVANT le delete() réel :
    l'état complet de l'objet est conservé dans `extra["valeurs"]`.
    """
    from .models import AuditLog

    contexte = {"valeurs": capture(obj)}
    if extra:
        contexte.update(extra)
    return log_action(
        AuditLog.Action.DELETE, request=request, actor=actor, obj=obj, extra=contexte
    )


def log_login(user, request=None):
    """Journalise une connexion réussie au back-office."""
    from .models import AuditLog

    return log_action(AuditLog.Action.LOGIN, request=request, actor=user)


def log_logout(user, request=None):
    """Journalise une déconnexion."""
    from .models import AuditLog

    return log_action(AuditLog.Action.LOGOUT, request=request, actor=user)


def log_login_failed(identifiant, request=None, extra=None):
    """
    Journalise un échec de connexion. Aucun utilisateur n'étant authentifié,
    l'identifiant tenté est conservé dans actor_label et dans extra.
    Le mot de passe saisi n'est évidemment jamais journalisé.
    """
    from .models import AuditLog

    identifiant = (identifiant or "inconnu")[:MAX_ACTOR_LABEL]
    contexte = {"identifiant_tente": identifiant}
    if extra:
        contexte.update(extra)
    return log_action(
        AuditLog.Action.LOGIN_FAILED,
        request=request,
        actor_label=identifiant,
        extra=contexte,
    )
