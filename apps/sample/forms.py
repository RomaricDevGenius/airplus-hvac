"""
Formulaires du back-office (gestion).
"""
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError

from apps.clients.models import ClientProfile

User = get_user_model()


class EmailAuthenticationForm(AuthenticationForm):
    """
    Formulaire d'authentification par email avec messages d'erreur personnalisés.
    """
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'votre@email.com',
            'autocomplete': 'email',
            'autofocus': True,
            'required': True
        })
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe',
            'autocomplete': 'current-password',
            'required': True
        })
    )

    error_messages = {
        'invalid_login': "Email ou mot de passe incorrect. Vérifiez que vous utilisez le bon email.",
        'inactive': "Ce compte est désactivé.",
    }

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password
            )
            if self.user_cache is None:
                raise ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


# Permissions proposées dans les rôles, regroupées par section.
# Chaque permission est listée explicitement (app_label, codename) : rien n'entre
# par accident, et l'ordre des tuples est l'ordre d'affichage du formulaire.
# La section « Administration » permet de déléguer la gestion du personnel et des
# rôles à un Administrateur, sans lui donner le statut technique de superuser.
PERMISSION_SECTIONS = (
    ("Catalogue (produits & stock)", (
        ("catalog", "view_product"),
        ("catalog", "add_product"),
        ("catalog", "change_product"),
        ("catalog", "delete_product"),
        ("catalog", "view_stockmovement"),
        ("catalog", "add_stockmovement"),
        ("catalog", "change_stockmovement"),
        ("catalog", "delete_stockmovement"),
    )),
    ("Clients", (
        ("clients", "view_clientprofile"),
        ("clients", "add_clientprofile"),
        ("clients", "change_clientprofile"),
        ("clients", "delete_clientprofile"),
    )),
    ("Demandes de devis", (
        ("quotes", "view_quoterequest"),
        ("quotes", "change_quoterequest"),
        ("quotes", "delete_quoterequest"),
    )),
    ("Tableau de bord", (
        ("accounts", "view_dashboard"),
    )),
    ("Administration", (
        ("accounts", "view_user"),
        ("accounts", "add_user"),
        ("accounts", "change_user"),
        ("accounts", "delete_user"),
        ("auth", "view_group"),
        ("auth", "add_group"),
        ("auth", "change_group"),
        ("auth", "delete_group"),
        ("audit", "view_auditlog"),
    )),
)

# Libellés métier en français pour chaque permission (app_label, codename) -> label
PERMISSION_LABELS = {
    # Catalogue / Produits
    ("catalog", "view_product"): "Voir les produits",
    ("catalog", "add_product"): "Ajouter un produit",
    ("catalog", "change_product"): "Modifier un produit",
    ("catalog", "delete_product"): "Supprimer un produit",
    # Mouvements de stock (add = entrée/sortie via le formulaire)
    ("catalog", "add_stockmovement"): "Ajouter un mouvement de stock",
    ("catalog", "change_stockmovement"): "Modifier un mouvement de stock",
    ("catalog", "delete_stockmovement"): "Supprimer un mouvement de stock",
    ("catalog", "view_stockmovement"): "Voir l'historique",
    # Clients
    ("clients", "view_clientprofile"): "Voir les clients",
    ("clients", "add_clientprofile"): "Ajouter un client",
    ("clients", "change_clientprofile"): "Modifier un client",
    ("clients", "delete_clientprofile"): "Supprimer un client",
    # Demandes de devis
    ("quotes", "view_quoterequest"): "Voir les demandes de devis",
    ("quotes", "change_quoterequest"): "Modifier une demande de devis",
    ("quotes", "delete_quoterequest"): "Supprimer une demande de devis",
    # Tableau de bord
    ("accounts", "view_dashboard"): "Voir le tableau de bord",
    # Administration — personnel
    ("accounts", "view_user"): "Voir le personnel",
    ("accounts", "add_user"): "Ajouter un membre du personnel",
    ("accounts", "change_user"): "Modifier un membre du personnel",
    ("accounts", "delete_user"): "Supprimer un membre du personnel",
    # Administration — rôles
    ("auth", "view_group"): "Voir les rôles",
    ("auth", "add_group"): "Créer un rôle",
    ("auth", "change_group"): "Modifier un rôle",
    ("auth", "delete_group"): "Supprimer un rôle",
    # Administration — journal d'audit (lecture seule)
    ("audit", "view_auditlog"): "Consulter le journal d'audit",
}

# (app_label, codename) -> libellé de la section qui contient la permission
PERMISSION_SECTION_BY_KEY = {
    key: label for label, keys in PERMISSION_SECTIONS for key in keys
}


def get_business_permissions_queryset():
    """Permissions sélectionnables dans un rôle : celles listées dans PERMISSION_SECTIONS."""
    from django.db.models import Q

    query = Q()
    for _, keys in PERMISSION_SECTIONS:
        for app_label, codename in keys:
            query |= Q(content_type__app_label=app_label, codename=codename)
    return Permission.objects.filter(query).select_related("content_type")


def get_permission_label(permission):
    """Retourne le libellé métier en français pour une permission."""
    key = (permission.content_type.app_label, permission.codename)
    return PERMISSION_LABELS.get(key, permission.name)


def get_permission_section(permission):
    """Retourne le libellé de la section à laquelle appartient une permission."""
    key = (permission.content_type.app_label, permission.codename)
    return PERMISSION_SECTION_BY_KEY.get(key, permission.content_type.app_label)


def get_permissions_grouped():
    """Permissions regroupées par section, dans l'ordre défini par PERMISSION_SECTIONS."""
    by_key = {
        (p.content_type.app_label, p.codename): p
        for p in get_business_permissions_queryset()
    }
    grouped = []
    for label, keys in PERMISSION_SECTIONS:
        items = [(by_key[key], get_permission_label(by_key[key])) for key in keys if key in by_key]
        if items:
            grouped.append((label, items))
    return grouped


class EmailChangeForm(forms.Form):
    """Modification de l'email de l'utilisateur connecté."""

    new_email = forms.EmailField(
        label="Nouvel email",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "nouveau@email.com", "autocomplete": "email"}),
    )
    password_confirm = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirmez avec votre mot de passe", "autocomplete": "current-password"}),
        help_text="Saisissez votre mot de passe pour confirmer le changement.",
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_new_email(self):
        email = self.cleaned_data.get("new_email", "").strip().lower()
        if not email:
            raise forms.ValidationError("L'email est requis.")
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Cet email est déjà utilisé par un autre compte.")
        return email

    def clean_password_confirm(self):
        password = self.cleaned_data.get("password_confirm")
        if password and not self.user.check_password(password):
            raise forms.ValidationError("Mot de passe incorrect.")
        return password

    def save(self):
        self.user.email = self.cleaned_data["new_email"]
        self.user.save(update_fields=["email"])
        return self.user


# ——— Utilisateurs (admin) ———

class UserCreateForm(forms.ModelForm):
    """Création d'un utilisateur back-office (connexion par email)."""
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": "form-control"}))
    password1 = forms.CharField(label="Mot de passe", widget=forms.PasswordInput(attrs={"class": "form-control"}))
    password2 = forms.CharField(label="Confirmer le mot de passe", widget=forms.PasswordInput(attrs={"class": "form-control"}))

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "is_staff", "groups")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "groups": forms.SelectMultiple(attrs={"class": "form-select"}),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un utilisateur avec cet email existe déjà.")
        return email

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Les deux mots de passe ne correspondent pas.")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data["email"]
        user.username = email
        user.email = email
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class UserUpdateForm(forms.ModelForm):
    """Édition d'un utilisateur (email = identifiant de connexion)."""
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": "form-control"}))

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "is_staff", "is_active", "groups")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "groups": forms.SelectMultiple(attrs={"class": "form-select"}),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Un utilisateur avec cet email existe déjà.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = user.email
        if commit:
            user.save()
            self.save_m2m()
        return user


# ——— Clients (création par l'admin) ———

class ClientCreateForm(forms.Form):
    """Création d'un client par l'admin (User + ClientProfile, is_staff=False)."""
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": "form-control"}))
    password1 = forms.CharField(label="Mot de passe", widget=forms.PasswordInput(attrs={"class": "form-control"}))
    password2 = forms.CharField(label="Confirmer le mot de passe", widget=forms.PasswordInput(attrs={"class": "form-control"}))
    first_name = forms.CharField(label="Prénom", max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    last_name = forms.CharField(label="Nom", max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    company_name = forms.CharField(label="Raison sociale / Entreprise", max_length=255, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    phone = forms.CharField(label="Téléphone", max_length=32, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    address = forms.CharField(label="Adresse", required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un client avec cet email existe déjà.")
        return email

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Les deux mots de passe ne correspondent pas.")
        return p2

    def save(self):
        email = self.cleaned_data["email"]
        user = User.objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
            is_staff=False,
        )
        ClientProfile.objects.create(
            user=user,
            company_name=self.cleaned_data.get("company_name", ""),
            phone=self.cleaned_data.get("phone", ""),
            address=self.cleaned_data.get("address", ""),
        )
        return user


class ClientUpdateForm(forms.Form):
    """Modification d'un client (User + ClientProfile). Mot de passe optionnel."""
    email = forms.EmailField(label="Email (identifiant de connexion)", widget=forms.EmailInput(attrs={"class": "form-control"}))
    password1 = forms.CharField(
        label="Nouveau mot de passe (laisser vide pour ne pas changer)",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmer le mot de passe",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )
    first_name = forms.CharField(label="Prénom", max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    last_name = forms.CharField(label="Nom", max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    company_name = forms.CharField(label="Raison sociale / Entreprise", max_length=255, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    phone = forms.CharField(label="Téléphone", max_length=32, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    address = forms.CharField(label="Adresse", required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))

    def __init__(self, client_profile, *args, **kwargs):
        self.client_profile = client_profile
        self.user = client_profile.user
        super().__init__(*args, **kwargs)
        self.fields["email"].initial = self.user.email
        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name
        self.fields["company_name"].initial = client_profile.company_name
        self.fields["phone"].initial = client_profile.phone
        self.fields["address"].initial = client_profile.address

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Un autre compte utilise déjà cet email.")
        return email

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 or p2:
            if p1 != p2:
                raise forms.ValidationError("Les deux mots de passe ne correspondent pas.")
        return p2

    def save(self):
        self.user.email = self.cleaned_data["email"]
        self.user.username = self.cleaned_data["email"]
        self.user.first_name = self.cleaned_data.get("first_name", "")
        self.user.last_name = self.cleaned_data.get("last_name", "")
        if self.cleaned_data.get("password1"):
            self.user.set_password(self.cleaned_data["password1"])
        self.user.save()
        self.client_profile.company_name = self.cleaned_data.get("company_name", "")
        self.client_profile.phone = self.cleaned_data.get("phone", "")
        self.client_profile.address = self.cleaned_data.get("address", "")
        self.client_profile.save()
        return self.client_profile


# ——— Rôles (Group) ———

class GroupForm(forms.ModelForm):
    """Création / édition d'un rôle (groupe Django). Permissions = logique métier uniquement."""
    class Meta:
        model = Group
        fields = ("name", "permissions")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex. Vendeur, Gestionnaire stock"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].queryset = get_business_permissions_queryset()
        self.fields["permissions"].required = False
        # Widget caché : le template affiche les cases à cocher en cartes
        self.fields["permissions"].widget = forms.CheckboxSelectMultiple()
