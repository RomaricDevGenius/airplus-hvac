from django.urls import path

from . import views

app_name = "gestion"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="index"),
    path("connexion/", views.UnifiedLoginView.as_view(), name="login"),
    path("deconnexion/", views.gestion_logout_view, name="logout"),
    # Produits
    path("produits/", views.ProductListView.as_view(), name="product-list"),
    path("produits/ajout/", views.ProductCreateView.as_view(), name="product-create"),
    path("produits/<int:pk>/modifier/", views.ProductUpdateView.as_view(), name="product-update"),
    path("produits/<int:pk>/supprimer/", views.ProductDeleteView.as_view(), name="product-delete"),
    path("produits/<int:product_id>/mouvement-stock/", views.StockMovementView.as_view(), name="stock-movement"),
    # Clients
    path("clients/", views.ClientListView.as_view(), name="client-list"),
    path("clients/ajout/", views.ClientCreateView.as_view(), name="client-create"),
    path("clients/<int:pk>/", views.ClientDetailView.as_view(), name="client-detail"),
    path("clients/<int:pk>/modifier/", views.ClientUpdateView.as_view(), name="client-update"),
    path("clients/<int:pk>/supprimer/", views.ClientDeleteView.as_view(), name="client-delete"),
    # Demandes de devis
    path("devis/", views.QuoteRequestListView.as_view(), name="quote-list"),
    path("devis/<int:pk>/", views.QuoteRequestDetailView.as_view(), name="quote-detail"),
    path("devis/<int:pk>/traiter/", views.QuoteRequestProcessView.as_view(), name="quote-process"),
    path("devis/<int:pk>/modifier/", views.QuoteRequestUpdateView.as_view(), name="quote-update"),
    path("devis/<int:pk>/supprimer/", views.QuoteRequestDeleteView.as_view(), name="quote-delete"),
    # Profil & Historique
    path("profil/", views.ProfileView.as_view(), name="profile"),
    path("profil/changer-mot-de-passe/", views.GestionPasswordChangeView.as_view(), name="password_change"),
    path("historique/", views.HistoriqueView.as_view(), name="historique"),
    # Administration (superuser)
    path("utilisateurs/", views.UserListView.as_view(), name="user-list"),
    path("utilisateurs/ajout/", views.UserCreateView.as_view(), name="user-create"),
    path("utilisateurs/<int:pk>/modifier/", views.UserUpdateView.as_view(), name="user-update"),
    path("utilisateurs/<int:pk>/supprimer/", views.UserDeleteView.as_view(), name="user-delete"),
    path("roles/", views.RoleListView.as_view(), name="role-list"),
    path("roles/ajout/", views.RoleCreateView.as_view(), name="role-create"),
    path("roles/<int:pk>/", views.RoleDetailView.as_view(), name="role-detail"),
    path("roles/<int:pk>/modifier/", views.RoleUpdateView.as_view(), name="role-update"),
    path("roles/<int:pk>/supprimer/", views.RoleDeleteView.as_view(), name="role-delete"),
    # Notifications
    path("notifications/<int:pk>/lire/", views.notification_mark_read, name="notif-read"),
    path("notifications/tout-lire/", views.notification_mark_all_read, name="notif-read-all"),
]
