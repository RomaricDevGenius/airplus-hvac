"""
Vues site client : accueil, boutique (produits réels), détail produit, auth, demande de devis.
"""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.catalog.models import Product
from apps.quotes.models import QuoteRequest, QuoteRequestItem
from apps.quotes.services import send_quote_request_email

from .forms import ClientRegistrationForm, QuoteRequestForm

User = get_user_model()


# ——— Pages statiques ———

class SiteIndexView(TemplateView):
    """Page d'accueil : produits en avant (visibles)."""
    template_name = "site web/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["featured_products"] = Product.objects.filter(is_visible=True).order_by("reference")[:8]
        return context


class SiteStoreView(ListView):
    """Boutique : liste des produits visibles."""
    model = Product
    template_name = "site web/store.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        return Product.objects.filter(is_visible=True).order_by("reference")


class SiteProductView(DetailView):
    """Détail d'un produit."""
    model = Product
    template_name = "site web/product.html"
    context_object_name = "product"

    def get_queryset(self):
        return Product.objects.filter(is_visible=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        context["related_products"] = (
            Product.objects.filter(is_visible=True)
            .exclude(pk=product.pk)
            .order_by("reference")[:4]
        )
        return context


class SiteBlankView(TemplateView):
    """Page vierge (à propos, etc.)."""
    template_name = "site web/blank.html"


# ——— Auth client ———

class ClientLoginView(LoginView):
    """Connexion : redirige vers l'accueil ou la page demandée."""
    template_name = "site web/auth/login.html"
    redirect_authenticated_user = True
    next_page = reverse_lazy("front:index")


def client_logout_view(request):
    """Déconnexion."""
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL or "front:index")


class ClientRegisterView(FormView):
    """Inscription client (création User + ClientProfile). Même style que la page de connexion."""
    template_name = "admin/gestion/register.html"
    form_class = ClientRegistrationForm
    success_url = reverse_lazy("front:index")

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, "Inscription réussie. Vous êtes connecté.")
        return redirect(self.success_url)


# ——— Demande de devis ———

def quote_request_view(request, product_pk=None):
    """
    Demande de devis. Nécessite un client connecté.
    Si product_pk fourni, préremplit l'objet avec le produit.
    """
    if not request.user.is_authenticated:
        messages.warning(request, "Connectez-vous pour demander un devis.")
        return redirect(f"{settings.LOGIN_URL}?next={request.path}")
    product = None
    if product_pk:
        product = get_object_or_404(Product, pk=product_pk, is_visible=True)
    if request.method == "POST":
        form = QuoteRequestForm(request.POST)
        if form.is_valid():
            quote = form.save(commit=False)
            quote.client = request.user
            quote.save()
            if product:
                QuoteRequestItem.objects.create(quote_request=quote, product=product, quantity=1)
            send_quote_request_email(quote)
            return redirect("front:quote_success")
    else:
        initial = {}
        if product:
            initial["subject"] = f"Devis pour {product.reference} – {product.designation}"
        form = QuoteRequestForm(initial=initial)
    return render(request, "site web/quotes/quote_request.html", {"form": form, "product": product})


# Redirection checkout → accueil (hors logique e‑commerce)
def site_checkout_redirect(request):
    return redirect("front:index")


def quote_success_view(request):
    """Page de confirmation après envoi d'une demande de devis."""
    return render(request, "site web/quotes/quote_success.html")


@require_POST
def contact_send_view(request):
    """AJAX : envoi du formulaire de contact depuis la page d'accueil."""
    from django.core.mail import send_mail

    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    subject = request.POST.get("subject", "").strip()
    message = request.POST.get("message", "").strip()

    if not name or not email or not message:
        return JsonResponse(
            {"ok": False, "error": "Veuillez remplir tous les champs obligatoires."},
            status=400,
        )

    try:
        send_mail(
            subject=f"[Contact AIRPLUS HVAC] {subject or 'Message depuis le site'}",
            message=f"De : {name} ({email})\nTél : {phone}\n\n{message}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.EMAIL_HOST_USER],
            fail_silently=False,
        )
        return JsonResponse({"ok": True})
    except Exception:
        return JsonResponse(
            {"ok": False, "error": "Erreur lors de l'envoi. Veuillez réessayer."},
            status=500,
        )


@require_POST
def quote_request_ajax(request):
    """AJAX : envoi d'une demande de devis depuis le panneau produit (sans rechargement)."""
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "Vous devez être connecté pour envoyer une demande."}, status=403)

    product_pk = request.POST.get("product_pk")
    product = None
    if product_pk:
        try:
            product = Product.objects.get(pk=product_pk, is_visible=True)
        except Product.DoesNotExist:
            pass

    form = QuoteRequestForm(request.POST)
    if form.is_valid():
        quote = form.save(commit=False)
        quote.client = request.user
        quote.save()
        if product:
            QuoteRequestItem.objects.create(quote_request=quote, product=product, quantity=1)
        try:
            send_quote_request_email(quote)
        except Exception:
            pass  # L'email est non-bloquant
        return JsonResponse({"ok": True})

    errors = {field: errs[0] for field, errs in form.errors.items()}
    return JsonResponse({"ok": False, "errors": errors}, status=400)


# ——— Panier ———


def _get_cart(session):
    """
    Récupère le panier depuis la session sous forme de dict {str(product_id): int(quantity)}.
    """
    cart = session.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}
    cleaned = {}
    for key, value in cart.items():
        try:
            qty = int(value)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            cleaned[str(key)] = qty
    return cleaned


def _save_cart(session, cart):
    session["cart"] = cart
    session.modified = True


@login_required
def cart_detail_view(request):
    """
    Affiche le contenu du panier courant de l'utilisateur.
    """
    cart = _get_cart(request.session)
    if not cart:
        items = []
    else:
        product_ids = [int(pk) for pk in cart.keys()]
        products = Product.objects.filter(pk__in=product_ids, is_visible=True)
        # On préserve grossièrement l'ordre d'ajout via cart.keys()
        product_map = {p.pk: p for p in products}
        items = []
        for key in cart.keys():
            pk = int(key)
            product = product_map.get(pk)
            if not product:
                continue
            qty = cart.get(key, 0)
            try:
                qty_int = int(qty)
            except (TypeError, ValueError):
                continue
            if qty_int <= 0:
                continue
            items.append(
                {
                    "product": product,
                    "quantity": qty_int,
                }
            )

    total_quantity = sum(item["quantity"] for item in items)

    # Formulaire simple basé sur QuoteRequestForm pour sujet/message
    if request.method == "POST":
        form = QuoteRequestForm(request.POST)
    else:
        form = QuoteRequestForm()

    context = {
        "items": items,
        "total_quantity": total_quantity,
        "form": form,
    }
    return render(request, "site web/cart.html", context)


@require_POST
def cart_add(request):
    """
    Ajoute un produit au panier (AJAX ou POST classique).
    """
    if not request.user.is_authenticated:
        login_url = settings.LOGIN_URL
        next_url = request.META.get("HTTP_REFERER") or "/"
        return JsonResponse(
            {
                "ok": False,
                "login_url": f"{login_url}?next={next_url}",
            },
            status=403,
        )

    product_id = request.POST.get("product_id")
    quantity = request.POST.get("quantity", "1")
    try:
        product = Product.objects.get(pk=product_id, is_visible=True)
    except (Product.DoesNotExist, ValueError, TypeError):
        # Produit introuvable ou non visible
        response_data = {"ok": False, "error": "Produit introuvable."}
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(response_data, status=404)
        messages.error(request, "Ce produit n'est plus disponible.")
        return redirect("front:store")

    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        qty = 1
    if qty <= 0:
        qty = 1

    cart = _get_cart(request.session)
    key = str(product.pk)
    cart[key] = cart.get(key, 0) + qty
    _save_cart(request.session, cart)

    total_quantity = sum(cart.values())

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "cart_count": total_quantity})

    return redirect("front:cart_detail")


@require_POST
def cart_remove(request):
    """
    Réduit la quantité d'un produit dans le panier ou le retire complètement.

    Paramètres:
      - product_id
      - delta (optionnel, int, par défaut -1). Si après application la quantité <= 0, le produit est retiré.
    """
    if not request.user.is_authenticated:
        login_url = settings.LOGIN_URL
        next_url = request.META.get("HTTP_REFERER") or "/"
        return JsonResponse(
            {
                "ok": False,
                "login_url": f"{login_url}?next={next_url}",
            },
            status=403,
        )

    product_id = request.POST.get("product_id")
    try:
        delta = int(request.POST.get("delta", "-1"))
    except (TypeError, ValueError):
        delta = -1

    cart = _get_cart(request.session)
    key = str(product_id)
    if key in cart:
        new_qty = cart[key] + delta
        if new_qty > 0:
            cart[key] = new_qty
        else:
            cart.pop(key, None)
        _save_cart(request.session, cart)

    total_quantity = sum(cart.values())

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "cart_count": total_quantity})

    return redirect("front:cart_detail")


@login_required
@require_POST
def cart_quote_view(request):
    """
    Crée une demande de devis à partir de tous les produits présents dans le panier.
    """
    cart = _get_cart(request.session)
    if not cart:
        messages.warning(request, "Votre panier est vide.")
        return redirect("front:cart_detail")

    form = QuoteRequestForm(request.POST)
    if not form.is_valid():
        # On réutilise cart_detail_view pour réafficher le formulaire avec erreurs
        items = []
        product_ids = [int(pk) for pk in cart.keys()]
        products = Product.objects.filter(pk__in=product_ids, is_visible=True)
        product_map = {p.pk: p for p in products}
        for key in cart.keys():
            pk = int(key)
            product = product_map.get(pk)
            if not product:
                continue
            qty = cart.get(key, 0)
            try:
                qty_int = int(qty)
            except (TypeError, ValueError):
                continue
            if qty_int <= 0:
                continue
            items.append({"product": product, "quantity": qty_int})
        total_quantity = sum(item["quantity"] for item in items)
        context = {
            "items": items,
            "total_quantity": total_quantity,
            "form": form,
        }
        return render(request, "site web/cart.html", context)

    # Création de la demande de devis
    quote = form.save(commit=False)
    quote.client = request.user
    quote.save()

    product_ids = [int(pk) for pk in cart.keys()]
    products = Product.objects.filter(pk__in=product_ids, is_visible=True)
    product_map = {p.pk: p for p in products}
    for key, qty in cart.items():
        try:
            pk = int(key)
            qty_int = int(qty)
        except (TypeError, ValueError):
            continue
        if qty_int <= 0:
            continue
        product = product_map.get(pk)
        if not product:
            continue
        QuoteRequestItem.objects.create(
            quote_request=quote,
            product=product,
            quantity=qty_int,
        )

    try:
        send_quote_request_email(quote)
    except Exception:
        # L'email ne doit pas bloquer la création du devis
        pass

    # On vide le panier
    request.session["cart"] = {}
    request.session.modified = True

    messages.success(request, "Votre demande de devis pour les produits du panier a bien été envoyée.")
    return redirect("front:quote_success")
