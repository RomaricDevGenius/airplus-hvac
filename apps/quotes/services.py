"""
Service envoi email demande de devis vers l'admin (Gmail).
"""
import os
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings
from django.core.mail import get_connection
from django.utils.html import escape


def send_quote_request_email(quote_request):
    """
    Envoie un email HTML professionnel à l'admin avec les détails de la demande de devis.
    Le logo est embarqué via CID (Content-ID), compatible Gmail.
    """
    to_email = getattr(settings, "EMAIL_ADMIN_QUOTES", None) or settings.DEFAULT_FROM_EMAIL
    client = quote_request.client
    client_name = escape(client.get_full_name() or client.username)
    client_email = client.email or "(non renseigné)"
    subject_text = escape(quote_request.subject)
    message_text = escape(quote_request.message).replace("\n", "<br>")

    subject = f"[AIRPLUS HVAC] Nouvelle demande de devis – {quote_request.subject}"

    text_body = (
        f"Nouvelle demande de devis reçue.\n\n"
        f"Client : {client.get_full_name() or client.username}\n"
        f"Email : {client_email}\n\n"
        f"Objet : {quote_request.subject}\n\n"
        f"Message :\n{quote_request.message}\n\n"
        f"---\n"
        f"Répondre directement à {client_email} pour traiter la demande."
    )

    html_body = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: #f0f2f5; margin: 0; padding: 0; }}
    .wrapper {{ max-width: 580px; margin: 36px auto; background: #ffffff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 8px rgba(0,0,0,0.10); border-top: 3px solid #1a5276; }}
    /* HEADER */
    .header {{ background: #ffffff; padding: 20px 36px 20px 6px; border-bottom: 1px solid #eaecef; }}
    .header-inner {{ display: flex; align-items: center; gap: 24px; }}
    .header img {{ height: 56px; width: auto; flex-shrink: 0; border: 1px solid #e2e6ea; border-radius: 5px; padding: 5px; background: #fff; }}
    .header-divider {{ width: 1px; height: 44px; background: #dde2e8; flex-shrink: 0; margin: 0 4px; }}
    .header-text .company {{ font-size: 17px; font-weight: 700; color: #1a2b42; margin: 0 0 4px; letter-spacing: .3px; }}
    .header-text .tagline {{ font-size: 12px; color: #9aa4b0; margin: 0; letter-spacing: .2px; }}
    /* BADGE */
    .badge {{ margin: 28px 36px 0; background: #f3f8ff; border-left: 3px solid #1a5276; padding: 13px 18px; border-radius: 4px; }}
    .badge p {{ margin: 0; font-size: 14px; font-weight: 600; color: #1a3a5c; }}
    /* BODY */
    .body {{ padding: 28px 36px 36px; }}
    .section-title {{ font-size: 10.5px; font-weight: 700; color: #9aa4b0; text-transform: uppercase; letter-spacing: 1.3px; margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #f0f2f5; }}
    .section-title:first-child {{ margin-top: 0; }}
    .info-table {{ width: 100%; border-collapse: collapse; }}
    .info-table tr:last-child td {{ border-bottom: none; }}
    .info-table td {{ padding: 11px 0; font-size: 13.5px; color: #1a2b42; border-bottom: 1px solid #f4f5f7; vertical-align: top; }}
    .info-table td.label {{ color: #9aa4b0; width: 120px; font-weight: 600; font-size: 13px; }}
    .info-table a {{ color: #1a5276; text-decoration: none; }}
    .message-box {{ background: #f8f9fa; border: 1px solid #e8eaed; border-radius: 4px; padding: 16px 18px; font-size: 13.5px; color: #3d4d5c; line-height: 1.75; margin-top: 6px; }}
    .cta {{ text-align: center; margin: 32px 0 6px; }}
    .cta a {{ background: #1a5276; color: #ffffff; padding: 12px 34px; border-radius: 4px; text-decoration: none; font-size: 14px; font-weight: 600; display: inline-block; letter-spacing: .3px; }}
    /* FOOTER */
    .footer {{ background: #f8f9fa; border-top: 1px solid #dde2e8; padding: 20px 36px 20px 6px; }}
    .footer-inner {{ display: flex; align-items: center; gap: 24px; }}
    .footer img {{ height: 56px; width: auto; flex-shrink: 0; border: 1px solid #e2e6ea; border-radius: 5px; padding: 5px; background: #fff; }}
    .footer-divider {{ width: 1px; height: 44px; background: #dde2e8; flex-shrink: 0; margin: 0 4px; }}
    .footer-info .footer-name {{ font-size: 13px; font-weight: 700; color: #1a2b42; margin: 0 0 5px; }}
    .footer-info p {{ margin: 0; font-size: 11.5px; color: #8a96a3; line-height: 1.8; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <!-- EN-TÊTE -->
    <div class="header">
      <div class="header-inner">
        <img src="cid:logo_airplus" alt="AIRPLUS HVAC" />
        <div class="header-divider"></div>
        <div class="header-text">
          <p class="company">AIRPLUS HVAC</p>
          <p class="tagline">Climatisation &nbsp;&middot;&nbsp; Ventilation &nbsp;&middot;&nbsp; Génie Climatique</p>
        </div>
      </div>
    </div>
    <!-- BADGE -->
    <div class="badge">
      <p>Nouvelle demande de devis reçue</p>
    </div>
    <!-- CONTENU -->
    <div class="body">
      <div class="section-title">Informations client</div>
      <table class="info-table">
        <tr><td class="label">Nom</td><td>{client_name}</td></tr>
        <tr><td class="label">Email</td><td><a href="mailto:{client_email}">{client_email}</a></td></tr>
      </table>
      <div class="section-title">Détail de la demande</div>
      <table class="info-table">
        <tr><td class="label">Objet</td><td>{subject_text}</td></tr>
        <tr><td class="label">Date</td><td>{quote_request.created_at.strftime("%d/%m/%Y à %H:%M")}</td></tr>
      </table>
      <div class="section-title">Message</div>
      <div class="message-box">{message_text}</div>
      <div class="cta">
        <a href="mailto:{client_email}">Répondre au client</a>
      </div>
    </div>
    <!-- FOOTER -->
    <div class="footer">
      <div class="footer-inner">
        <img src="cid:logo_airplus" alt="AIRPLUS HVAC" />
        <div class="footer-divider"></div>
        <div class="footer-info">
          <p class="footer-name">AIRPLUS HVAC</p>
          <p>8CMR+GV2, rue 17.127, Pissy, Ouagadougou<br>+226 76 90 90 01</p>
        </div>
      </div>
    </div>
  </div>
</body>
</html>"""

    # ------------------------------------------------------------------ #
    # Construction MIME correcte : multipart/mixed                        #
    #   └─ multipart/alternative                                          #
    #        ├─ text/plain                                                #
    #        └─ multipart/related                                         #
    #             ├─ text/html                                            #
    #             └─ image/jpeg  (CID — non visible comme pièce jointe)  #
    # ------------------------------------------------------------------ #
    logo_path = os.path.join(settings.BASE_DIR, "src", "assets", "site", "img", "logo.jpg")
    with open(logo_path, "rb") as f:
        logo_data = f.read()

    logo_img = MIMEImage(logo_data, "jpeg")
    logo_img.add_header("Content-ID", "<logo_airplus>")

    related = MIMEMultipart("related")
    related.attach(MIMEText(html_body, "html", "utf-8"))
    related.attach(logo_img)

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(text_body, "plain", "utf-8"))
    alternative.attach(related)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = settings.DEFAULT_FROM_EMAIL
    msg["To"] = to_email
    msg["Reply-To"] = client_email
    msg.attach(alternative)

    connection = get_connection()
    connection.open()
    connection.connection.sendmail(
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
        msg.as_string(),
    )
    connection.close()

