"""
Formulaires site client : inscription, demande de devis.
"""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from apps.clients.models import ClientProfile
from apps.quotes.models import QuoteRequest

User = get_user_model()


class ClientRegistrationForm(UserCreationForm):
    """Inscription client : username, email, mot de passe + infos profil."""
    email = forms.EmailField(required=True, label="Email", widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "votre@email.com", "autocomplete": "email"}))
    first_name = forms.CharField(max_length=150, required=True, label="Prénom", widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex. Jean"}))
    last_name = forms.CharField(max_length=150, required=True, label="Nom", widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex. Dupont"}))
    company_name = forms.CharField(max_length=255, required=True, label="Raison sociale / Entreprise", widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex. Ma Société SARL"}))
    phone = forms.CharField(max_length=32, required=True, label="Téléphone", widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex. +226 70 00 00 00"}))
    address = forms.CharField(widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Ex. Ouagadougou, secteur 15, rue 17.127"}), required=True, label="Adresse")

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password1", "password2")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "Identifiant de connexion"}),
            "password1": forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Mot de passe", "autocomplete": "new-password", "id": "id_password1"}),
            "password2": forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirmer le mot de passe", "autocomplete": "new-password", "id": "id_password2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Appliquer form-control et placeholder sur password1 et password2
        self.fields["password1"].widget = forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Mot de passe", "autocomplete": "new-password", "id": "id_password1"})
        self.fields["password2"].widget = forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirmer le mot de passe", "autocomplete": "new-password", "id": "id_password2"})
        # Masquer le help_text par défaut (remplacé par l'indicateur de force en JS)
        self.fields["password1"].help_text = None
        self.fields["password2"].help_text = None

    def save(self, commit=True):
        user = super().save(commit=commit)
        user.is_staff = False
        if commit:
            user.save()
            ClientProfile.objects.create(
                user=user,
                company_name=self.cleaned_data.get("company_name", ""),
                phone=self.cleaned_data.get("phone", ""),
                address=self.cleaned_data.get("address", ""),
            )
        return user


class QuoteRequestForm(forms.ModelForm):
    """Formulaire demande de devis (objet + message)."""
    class Meta:
        model = QuoteRequest
        fields = ("subject", "message")
        widgets = {
            "subject": forms.TextInput(attrs={"class": "input", "placeholder": "Objet de votre demande"}),
            "message": forms.Textarea(attrs={"class": "input", "rows": 5, "placeholder": "Décrivez votre demande (produits, quantités, délais…)"}),
        }
        labels = {"subject": "Objet", "message": "Message"}
