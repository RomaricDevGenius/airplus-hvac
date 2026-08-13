"""
Filtres de la page « Audit & Logs » (/gestion/audit/).

Le formulaire est en méthode GET : il ne sert pas à saisir des données mais à
VALIDER et NETTOYER ce qui arrive dans l'URL. Tous les champs sont donc
facultatifs, et un paramètre farfelu dans l'URL ne doit jamais faire planter la
page — au pire il est ignoré.
"""
from django import forms
from django.contrib.auth import get_user_model

from .models import AuditLog

# Champs qui, une fois renseignés, signifient « un filtre est actif ».
FILTER_FIELDS = ("q", "auteur", "action", "debut", "fin")


def acting_users():
    """
    Personnes ayant RÉELLEMENT agi d'après le journal.

    On ne propose pas l'annuaire complet du personnel : une liste déroulante de
    200 comptes dont 3 seulement ont laissé une trace serait inutilisable. La
    sous-requête s'appuie sur l'index (actor, -created_at).
    """
    identifiants = (
        AuditLog.objects.filter(actor__isnull=False)
        .values_list("actor_id", flat=True)
        .distinct()
    )
    return (
        get_user_model()
        .objects.filter(pk__in=identifiants)
        .order_by("first_name", "last_name", "username")
    )


def nom_lisible(utilisateur):
    """« Prénom Nom » si disponible, sinon l'email, sinon l'identifiant."""
    nom = (utilisateur.get_full_name() or "").strip()
    return nom or getattr(utilisateur, "email", "") or utilisateur.get_username()


class AuditFilterForm(forms.Form):
    """Filtres cumulatifs du journal d'audit : ils s'appliquent tous ensemble."""

    q = forms.CharField(
        label="Recherche",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Nom d'une personne ou d'un objet…",
        }),
    )
    auteur = forms.ModelChoiceField(
        label="Auteur",
        required=False,
        queryset=get_user_model().objects.none(),  # rempli dans __init__ (pas d'accès base à l'import)
        empty_label="Tous les auteurs",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    action = forms.ChoiceField(
        label="Action",
        required=False,
        choices=(("", "Toutes les actions"),) + tuple(AuditLog.Action.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    debut = forms.DateField(
        label="Du",
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )
    fin = forms.DateField(
        label="Au",
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["auteur"].queryset = acting_users()
        # Affiche « Prénom Nom » plutôt que le __str__ technique du modèle User.
        self.fields["auteur"].label_from_instance = nom_lisible

    def clean(self):
        donnees = super().clean()
        debut, fin = donnees.get("debut"), donnees.get("fin")
        if debut and fin and debut > fin:
            self.add_error(
                "fin",
                "La date de fin doit être postérieure à la date de début.",
            )
        return donnees

    @property
    def valeurs(self):
        """Valeurs nettoyées, même si le formulaire porte des erreurs partielles."""
        return getattr(self, "cleaned_data", None) or {}

    @property
    def actifs(self):
        """True si au moins un filtre est réellement renseigné."""
        donnees = self.valeurs
        return any(donnees.get(nom) for nom in FILTER_FIELDS)
