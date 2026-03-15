"""
Services métier catalogue : mouvements de stock, alertes stock.
"""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from .models import Product, StockMovement
from .repositories import ProductRepository, StockMovementRepository


class StockService:
    """
    Gestion des mouvements de stock.
    - Création d'un mouvement (entrée/sortie) avec mise à jour de la quantité.
    - Envoi d'une alerte email si le stock passe sous le seuil.
    """
    repo = StockMovementRepository()
    product_repo = ProductRepository()

    @classmethod
    def apply_movement(cls, product_id, movement_type, quantity, note, user):
        """
        Applique un mouvement (entrée ou sortie) et met à jour le stock.
        Raises ValueError si sortie et stock insuffisant.
        """
        movement = cls.repo.create(product_id, movement_type, quantity, note, user)
        product = Product.objects.get(pk=product_id)
        if product.is_low_stock:
            cls._send_stock_alert(product)
        return movement

    @classmethod
    def _send_stock_alert(cls, product):
        """Envoie un email HTML à l'admin et crée une notification back-office."""
        to_email = getattr(settings, "EMAIL_ADMIN_STOCK_ALERT", None)
        if not to_email:
            return

        subject = f"[AIRPLUS HVAC] Alerte stock – {product.reference} {product.designation}"
        site_url = getattr(settings, "SITE_URL", "http://localhost:8000")

        text_body = (
            f"Alerte stock – {product.reference}\n\n"
            f"Produit : {product.reference} – {product.designation}\n"
            f"Stock actuel : {product.quantity} unité(s)\n"
            f"Seuil d'alerte : {product.alert_threshold} unité(s)\n\n"
            f"Veuillez réapprovisionner ce produit dans les meilleurs délais.\n\n"
            f"—\nAIRPLUS HVAC"
        )

        html_body = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: #f0f2f5; margin: 0; padding: 0; }}
    .wrapper {{ max-width: 560px; margin: 36px auto; background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 8px rgba(0,0,0,.10); border-top: 3px solid #e67e22; }}
    .header {{ background: #fff; padding: 22px 36px; border-bottom: 1px solid #eaecef; display: flex; align-items: center; gap: 14px; }}
    .header-icon {{ width: 44px; height: 44px; background: #fff3e0; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
    .header-icon svg {{ width: 22px; height: 22px; fill: #e67e22; }}
    .header-text .company {{ font-size: 16px; font-weight: 700; color: #1a2b42; margin: 0 0 2px; }}
    .header-text .tagline {{ font-size: 11.5px; color: #9aa4b0; margin: 0; }}
    .badge-bar {{ margin: 24px 36px 0; background: #fff8f0; border-left: 3px solid #e67e22; padding: 12px 16px; border-radius: 4px; }}
    .badge-bar p {{ margin: 0; font-size: 13.5px; font-weight: 600; color: #b85c00; }}
    .body {{ padding: 24px 36px 32px; }}
    .section-title {{ font-size: 10.5px; font-weight: 700; color: #9aa4b0; text-transform: uppercase; letter-spacing: 1.2px; margin: 24px 0 10px; padding-bottom: 5px; border-bottom: 1px solid #f0f2f5; }}
    .section-title:first-child {{ margin-top: 0; }}
    .info-table {{ width: 100%; border-collapse: collapse; }}
    .info-table td {{ padding: 10px 0; font-size: 13.5px; color: #1a2b42; border-bottom: 1px solid #f4f5f7; vertical-align: top; }}
    .info-table tr:last-child td {{ border-bottom: none; }}
    .info-table td.label {{ color: #9aa4b0; width: 130px; font-weight: 600; font-size: 13px; }}
    .stock-value {{ font-weight: 700; color: #c0392b; font-size: 15px; }}
    .threshold-value {{ color: #7f8c8d; font-size: 13.5px; }}
    .cta {{ text-align: center; margin: 28px 0 6px; }}
    .cta a {{ background: #e67e22; color: #fff; padding: 12px 32px; border-radius: 4px; text-decoration: none; font-size: 14px; font-weight: 600; display: inline-block; }}
    .footer {{ background: #f8f9fa; border-top: 1px solid #dde2e8; padding: 16px 36px; }}
    .footer p {{ margin: 0; font-size: 11.5px; color: #8a96a3; }}
    .footer strong {{ color: #5a6473; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <div class="header-icon">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
        </svg>
      </div>
      <div class="header-text">
        <p class="company">AIRPLUS HVAC</p>
        <p class="tagline">Climatisation &nbsp;&middot;&nbsp; Ventilation &nbsp;&middot;&nbsp; G&eacute;nie Climatique</p>
      </div>
    </div>
    <div class="badge-bar">
      <p>&#9888;&nbsp; Alerte rupture de stock imminente</p>
    </div>
    <div class="body">
      <div class="section-title">Produit concern&eacute;</div>
      <table class="info-table">
        <tr><td class="label">R&eacute;f&eacute;rence</td><td><strong>{product.reference}</strong></td></tr>
        <tr><td class="label">D&eacute;signation</td><td>{product.designation}</td></tr>
      </table>
      <div class="section-title">Situation du stock</div>
      <table class="info-table">
        <tr>
          <td class="label">Stock actuel</td>
          <td><span class="stock-value">{product.quantity} unit&eacute;(s)</span></td>
        </tr>
        <tr>
          <td class="label">Seuil d&apos;alerte</td>
          <td><span class="threshold-value">{product.alert_threshold} unit&eacute;(s)</span></td>
        </tr>
      </table>
      <div class="cta">
        <a href="{site_url}/gestion/produits/{product.pk}/modifier/">R&eacute;approvisionner le produit</a>
      </div>
    </div>
    <div class="footer">
      <p><strong>AIRPLUS HVAC</strong> &nbsp;&bull;&nbsp; 8CMR+GV2, rue 17.127, Pissy, Ouagadougou &nbsp;&bull;&nbsp; +226 76 90 90 01</p>
    </div>
  </div>
</body>
</html>"""

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to_email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=True)
        except Exception:
            pass

        # Création de la notification back-office
        try:
            from apps.accounts.models import Notification
            Notification.objects.create(
                notif_type=Notification.STOCK_ALERT,
                title=f"Alerte stock – {product.reference}",
                message=f"{product.designation} : stock actuel {product.quantity} unité(s) (seuil : {product.alert_threshold})",
                link=f"/gestion/produits/{product.pk}/modifier/",
            )
        except Exception:
            pass


def send_stock_alert_if_needed(product):
    """
    À appeler après save d'un Product : envoie l'email d'alerte si quantity <= alert_threshold.
    Utilisé depuis un signal post_save.
    """
    if product.is_low_stock and product.quantity > 0:
        StockService._send_stock_alert(product)

