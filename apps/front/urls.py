from django.urls import path

from apps.sample.views import UnifiedLoginView
from . import views

app_name = "front"

urlpatterns = [
    path("", views.SiteIndexView.as_view(), name="index"),
    # Ancienne page boutique → redirection propre vers l'accueil
    path("boutique/", lambda r: __import__('django.shortcuts', fromlist=['redirect']).redirect('front:index'), name="store"),
    path("produit/<int:pk>/", views.SiteProductView.as_view(), name="product"),
    path("page/", views.SiteBlankView.as_view(), name="blank"),
    # Panier
    path("panier/", views.cart_detail_view, name="cart_detail"),
    path("panier/ajouter/", views.cart_add, name="cart_add"),
    path("panier/supprimer/", views.cart_remove, name="cart_remove"),
    path("panier/devis/", views.cart_quote_view, name="cart_quote"),
    # Connexion unifiée (même formulaire pour admin et clients)
    path("connexion/", UnifiedLoginView.as_view(), name="login"),
    path("deconnexion/", views.client_logout_view, name="logout"),
    path("inscription/", views.ClientRegisterView.as_view(), name="register"),
    # Demande de devis (AJAX modal uniquement, plus de page dédiée)
    path("devis/", lambda r: __import__('django.shortcuts', fromlist=['redirect']).redirect('front:index'), name="quote_request"),
    path("devis/<int:product_pk>/", lambda r, product_pk: __import__('django.shortcuts', fromlist=['redirect']).redirect('front:index'), name="quote_request_product"),
    path("devis/succes/", views.quote_success_view, name="quote_success"),
    path("devis/ajax/envoi/", views.quote_request_ajax, name="quote_request_ajax"),
    # Formulaire de contact (AJAX)
    path("contact/envoi/", views.contact_send_view, name="contact_send"),
    # Ancien checkout → accueil
    path("checkout/", views.site_checkout_redirect),
]
