from django.conf import settings


def language_code(request):
    return {"LANGUAGE_CODE": request.LANGUAGE_CODE}


def environment(request):
    return {"ENVIRONMENT": settings.ENVIRONMENT}


def notifications(request):
    """Injecte les notifications non lues dans tous les templates du back-office."""
    if request.user.is_authenticated and getattr(request.user, "is_staff", False):
        from apps.accounts.models import Notification
        unread_qs = Notification.objects.filter(is_read=False)
        return {
            "notif_count": unread_qs.count(),
            "notif_recent": list(unread_qs[:10]),
        }
    return {"notif_count": 0, "notif_recent": []}


def cart(request):
    """
    Injecte un compteur simple du panier dans tous les templates.

    Le panier est stocké en session sous la clé ``cart`` sous la forme
    d'un dict {product_id (str): quantity (int)}.
    """
    raw_cart = request.session.get("cart", {})
    try:
        total_quantity = sum(int(qty) for qty in raw_cart.values())
    except (TypeError, ValueError):
        total_quantity = 0
    return {"cart_item_count": total_quantity}
