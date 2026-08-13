/**
 * AIRPLUS HVAC — Socle de retour utilisateur (notifications, confirmations, chargement)
 * =====================================================================================
 *
 * Ce module s'appuie sur SweetAlert2 (déjà chargé par templates/admin/layout/partials/scripts.html)
 * et expose une API unique pour tout le back-office. Aucune dépendance externe, aucun CDN.
 *
 * ---------------------------------------------------------------------------
 * 1) API IMPÉRATIVE (à appeler depuis votre propre JavaScript)
 * ---------------------------------------------------------------------------
 *
 *   window.airplusToast(type, message, title)
 *       type    : 'success' | 'error' | 'warning' | 'info'
 *       message : texte affiché (obligatoire)
 *       title   : titre court facultatif
 *       Toast non bloquant en haut à droite, auto-fermeture après 4000 ms,
 *       barre de progression, aucun bouton. La minuterie se met en pause au survol.
 *
 *   window.airplusConfirm(options) -> Promise<boolean>
 *       options = {
 *         title             : question posée              (défaut « Confirmer l'action ? »)
 *         text              : texte explicatif             (facultatif)
 *         confirmButtonText : libellé du bouton OK         (défaut « Confirmer »)
 *         cancelButtonText  : libellé du bouton Annuler    (défaut « Annuler »)
 *         style             : 'danger' | 'warning' | 'question'  (défaut 'danger')
 *       }
 *       Résout à true si l'utilisateur confirme, false sinon (annulation, Échap, clic extérieur).
 *       En style 'danger', le focus par défaut est placé sur ANNULER (garde-fou).
 *
 *   window.airplusLoading(message)       ouvre une modale bloquante avec spinner (non fermable)
 *   window.airplusLoadingClose()         referme la modale de chargement
 *
 * ---------------------------------------------------------------------------
 * 2) CONTRAT DÉCLARATIF — data-airplus-confirm  (le plus utilisé)
 * ---------------------------------------------------------------------------
 *
 * Aucun JavaScript à écrire : il suffit de poser des attributs sur un bouton ou un lien.
 * Le gestionnaire est délégué sur `document` en phase de CAPTURE, il fonctionne donc aussi
 * sur du contenu injecté dynamiquement (AJAX, modales, tableaux rechargés…).
 *
 *   data-airplus-confirm="Supprimer ce client ?"        (OBLIGATOIRE — déclenche le mécanisme)
 *   data-airplus-confirm-text="Cette action est définitive."   (facultatif)
 *   data-airplus-confirm-button="Oui, supprimer"        (facultatif, défaut « Confirmer »)
 *   data-airplus-confirm-cancel="Non, garder"           (facultatif, défaut « Annuler »)
 *   data-airplus-confirm-style="danger|warning|question" (facultatif, défaut « danger »)
 *   data-airplus-post="/gestion/clients/12/supprimer/"  (facultatif — voir ci-dessous)
 *
 * Au clic : preventDefault + stopPropagation, puis affichage de la confirmation.
 * SI l'utilisateur confirme, dans cet ordre de priorité :
 *   1. data-airplus-post présent  -> un <form method="post" action="CETTE_URL"> est construit
 *                                    à la volée avec le jeton CSRF, ajouté au DOM et soumis ;
 *   2. sinon, élément dans un <form> -> ce formulaire est soumis ;
 *   3. sinon, élément <a href>       -> navigation vers href.
 * Dans les trois cas, airplusLoading() est affiché juste avant de quitter la page.
 * Si l'utilisateur annule, rien ne se passe (aucune soumission, aucune navigation).
 *
 * Exemples :
 *   <button type="submit" class="btn btn-danger"
 *           data-airplus-confirm="Supprimer ce devis ?"
 *           data-airplus-confirm-button="Oui, supprimer">Supprimer</button>
 *
 *   <a href="#" class="dropdown-item text-danger"
 *      data-airplus-confirm="Archiver cette facture ?"
 *      data-airplus-confirm-style="warning"
 *      data-airplus-post="{% url 'facture_archiver' f.pk %}">Archiver</a>
 *
 * ---------------------------------------------------------------------------
 * 3) MESSAGES DJANGO -> TOASTS (amélioration progressive)
 * ---------------------------------------------------------------------------
 *
 * Le serveur continue de rendre des alertes Bootstrap classiques
 * (templates/admin/layout/partials/messages.html). Si ce script n'est pas exécuté,
 * l'utilisateur voit ces alertes normales : rien n'est cassé.
 * Quand ce script tourne, les alertes sont converties en toasts puis retirées du DOM.
 * Les tags 'error' ET 'danger' sont gérés (MESSAGE_TAGS n'est pas encore configuré).
 *
 * Pour qu'une alerte échappe à la conversion, lui poser l'attribut `data-airplus-keep`.
 *
 * ---------------------------------------------------------------------------
 * 4) JETON CSRF
 * ---------------------------------------------------------------------------
 * Lu depuis le champ caché global #airplus-csrf (rendu dans scripts.html pour toutes
 * les pages du back-office), avec repli sur n'importe quel champ csrfmiddlewaretoken
 * de la page, puis sur le cookie 'csrftoken'.
 */

'use strict';

(function (window, document) {
  // ---------------------------------------------------------------------------
  // Outils internes
  // ---------------------------------------------------------------------------

  /** SweetAlert2 est-il disponible ? (garde-fou : le socle ne doit jamais lever d'erreur) */
  function swalDispo() {
    return typeof window.Swal !== 'undefined';
  }

  /** Récupère le jeton CSRF : champ caché global, puis n'importe quel champ, puis cookie. */
  function getCsrfToken() {
    var champ =
      document.querySelector('#airplus-csrf input[name="csrfmiddlewaretoken"]') ||
      document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (champ && champ.value) {
      return champ.value;
    }
    var cookies = document.cookie ? document.cookie.split(';') : [];
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf('csrftoken=') === 0) {
        return decodeURIComponent(c.substring('csrftoken='.length));
      }
    }
    return '';
  }

  /** Normalise un type de notification vers les icônes SweetAlert2. */
  function normaliserType(type) {
    switch (String(type || '').toLowerCase()) {
      case 'success':
        return 'success';
      case 'error':
      case 'danger':
        return 'error';
      case 'warning':
        return 'warning';
      default:
        return 'info';
    }
  }

  // Styles des boîtes de confirmation (habillage Vuexy : classes Bootstrap, pas de style natif)
  var STYLES_CONFIRMATION = {
    danger: { icon: 'warning', bouton: 'btn-danger' },
    warning: { icon: 'warning', bouton: 'btn-warning' },
    question: { icon: 'question', bouton: 'btn-primary' }
  };

  // ---------------------------------------------------------------------------
  // a) Toasts
  // ---------------------------------------------------------------------------

  var _toast = null;

  function toastMixin() {
    if (_toast) {
      return _toast;
    }
    _toast = window.Swal.mixin({
      toast: true,
      position: 'top-end',
      showConfirmButton: false,
      timer: 4000,
      timerProgressBar: true,
      customClass: { popup: 'airplus-toast' },
      didOpen: function (el) {
        // La minuterie se met en pause au survol : l'utilisateur a le temps de lire.
        el.addEventListener('mouseenter', window.Swal.stopTimer);
        el.addEventListener('mouseleave', window.Swal.resumeTimer);
      }
    });
    return _toast;
  }

  /**
   * Affiche un toast non bloquant en haut à droite.
   * @param {string} type    'success' | 'error' | 'warning' | 'info'
   * @param {string} message texte du message
   * @param {string} [title] titre court facultatif
   */
  window.airplusToast = function (type, message, title) {
    if (!swalDispo()) {
      return;
    }
    var icone = normaliserType(type);
    var options = { icon: icone };
    if (title) {
      options.title = title;
      options.text = message || '';
    } else {
      options.title = message || '';
    }
    toastMixin().fire(options);
  };

  // ---------------------------------------------------------------------------
  // b) Confirmation
  // ---------------------------------------------------------------------------

  /**
   * Demande une confirmation à l'utilisateur.
   * @param   {Object} options voir l'en-tête de ce fichier
   * @returns {Promise<boolean>} true si confirmé, false sinon
   */
  window.airplusConfirm = function (options) {
    options = options || {};
    var titre = options.title || "Confirmer l'action ?";
    var texte = options.text || '';
    var libelleOk = options.confirmButtonText || 'Confirmer';
    var libelleAnnuler = options.cancelButtonText || 'Annuler';
    var style = Object.prototype.hasOwnProperty.call(STYLES_CONFIRMATION, options.style) ? options.style : 'danger';
    var conf = STYLES_CONFIRMATION[style];

    // Repli sans SweetAlert2 : confirmation native du navigateur.
    if (!swalDispo()) {
      return Promise.resolve(window.confirm(texte ? titre + '\n\n' + texte : titre));
    }

    return window.Swal.fire({
      title: titre,
      text: texte,
      icon: conf.icon,
      showCancelButton: true,
      confirmButtonText: libelleOk,
      cancelButtonText: libelleAnnuler,
      // Sur une action destructrice, le focus part sur « Annuler » : on évite l'accident.
      focusCancel: style === 'danger',
      buttonsStyling: false,
      customClass: {
        confirmButton: 'btn ' + conf.bouton + ' me-2 waves-effect waves-light',
        cancelButton: 'btn btn-outline-secondary waves-effect'
      }
    }).then(function (resultat) {
      return !!(resultat && resultat.isConfirmed);
    });
  };

  // ---------------------------------------------------------------------------
  // c) Modale de chargement
  // ---------------------------------------------------------------------------

  /** Ouvre une modale bloquante avec spinner (ni Échap ni clic extérieur). */
  window.airplusLoading = function (message) {
    if (!swalDispo()) {
      return;
    }
    window.Swal.fire({
      title: message || 'Traitement en cours…',
      allowOutsideClick: false,
      allowEscapeKey: false,
      showConfirmButton: false,
      customClass: { popup: 'airplus-loading' },
      didOpen: function () {
        window.Swal.showLoading();
      }
    });
  };

  /** Referme la modale de chargement. */
  window.airplusLoadingClose = function () {
    if (swalDispo()) {
      window.Swal.close();
    }
  };

  // ---------------------------------------------------------------------------
  // d) Contrat déclaratif : data-airplus-confirm
  // ---------------------------------------------------------------------------

  /** Construit et soumet un formulaire POST jetable vers l'URL donnée. */
  function soumettrePost(url) {
    var form = document.createElement('form');
    form.setAttribute('method', 'post');
    form.setAttribute('action', url);
    form.style.display = 'none';

    var jeton = document.createElement('input');
    jeton.type = 'hidden';
    jeton.name = 'csrfmiddlewaretoken';
    jeton.value = getCsrfToken();
    form.appendChild(jeton);

    document.body.appendChild(form);
    form.submit();
  }

  /** Soumet le formulaire parent en conservant, si possible, le nom/valeur du bouton cliqué. */
  function soumettreFormulaire(form, element) {
    var estBoutonDuForm =
      element.form === form &&
      (element.tagName === 'BUTTON' || element.tagName === 'INPUT') &&
      (element.type === 'submit' || element.type === 'image');

    if (typeof form.requestSubmit === 'function') {
      if (estBoutonDuForm) {
        form.requestSubmit(element);
      } else {
        form.requestSubmit();
      }
    } else {
      form.submit();
    }
  }

  /** Exécute l'action demandée une fois la confirmation obtenue. */
  function executerAction(element) {
    var url = element.getAttribute('data-airplus-post');
    var form = element.closest ? element.closest('form') : null;
    var href = element.getAttribute('href');

    if (url) {
      window.airplusLoading();
      soumettrePost(url);
      return;
    }
    if (form) {
      // La modale de chargement ne doit s'ouvrir QUE si la soumission a
      // réellement lieu. Si la validation native du navigateur échoue (un champ
      // requis laissé vide), requestSubmit() ne soumet pas : une modale
      // bloquante resterait alors affichée indéfiniment, sans aucun moyen d'en
      // sortir autrement qu'en rechargeant la page.
      // On l'ouvre donc depuis l'événement « submit », qui n'est émis que si le
      // formulaire part vraiment.
      var ouvrirChargement = function () {
        window.airplusLoading();
      };
      form.addEventListener('submit', ouvrirChargement, { once: true });
      soumettreFormulaire(form, element);
      // requestSubmit() est synchrone : si aucun « submit » n'a été émis,
      // l'écouteur est devenu inutile, on le retire.
      form.removeEventListener('submit', ouvrirChargement);
      return;
    }
    if (href && href !== '#') {
      window.airplusLoading();
      window.location.href = href;
    }
    // Aucun des trois cas : rien à faire (l'appelant gère lui-même la suite).
  }

  // Phase de CAPTURE : on intercepte avant tout autre gestionnaire de la page,
  // y compris ceux posés sur l'élément lui-même. Le clic ne « passe » que si l'on confirme.
  document.addEventListener(
    'click',
    function (event) {
      var cible = event.target;
      if (!cible || typeof cible.closest !== 'function') {
        return;
      }
      var element = cible.closest('[data-airplus-confirm]');
      if (!element) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      window
        .airplusConfirm({
          title: element.getAttribute('data-airplus-confirm'),
          text: element.getAttribute('data-airplus-confirm-text') || '',
          confirmButtonText: element.getAttribute('data-airplus-confirm-button') || 'Confirmer',
          cancelButtonText: element.getAttribute('data-airplus-confirm-cancel') || 'Annuler',
          style: element.getAttribute('data-airplus-confirm-style') || 'danger'
        })
        .then(function (confirme) {
          if (confirme) {
            executerAction(element);
          }
        });
    },
    true
  );

  // ---------------------------------------------------------------------------
  // e) Conversion des messages Django rendus par le serveur en toasts
  // ---------------------------------------------------------------------------

  /** Déduit le type de notification à partir de l'élément d'alerte. */
  function typeDepuisAlerte(alerte) {
    var niveau = alerte.getAttribute('data-airplus-level');
    if (niveau) {
      // level_tag Django : debug / info / success / warning / error
      return normaliserType(niveau === 'debug' ? 'info' : niveau);
    }
    var classes = alerte.className || '';
    if (classes.indexOf('alert-success') !== -1) return 'success';
    if (classes.indexOf('alert-danger') !== -1 || classes.indexOf('alert-error') !== -1) return 'error';
    if (classes.indexOf('alert-warning') !== -1) return 'warning';
    return 'info';
  }

  /** Extrait le texte du message sans le bouton de fermeture. */
  function texteDepuisAlerte(alerte) {
    var copie = alerte.cloneNode(true);
    var boutons = copie.querySelectorAll('.btn-close, button');
    for (var i = 0; i < boutons.length; i++) {
      boutons[i].parentNode.removeChild(boutons[i]);
    }
    return (copie.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function convertirMessagesServeur() {
    if (!swalDispo()) {
      return; // Sans SweetAlert2, les alertes Bootstrap restent affichées : comportement dégradé correct.
    }

    var conteneur = document.querySelector('[data-airplus-messages]');
    var alertes;

    if (conteneur) {
      // Cas normal : le partial messages.html est présent (layouts vertical et horizontal).
      alertes = conteneur.querySelectorAll('.alert');
    } else {
      // Repli : layout sans le partial (layout_blank : connexion, inscription…).
      // On ne cible que les alertes clairement produites par le framework de messages
      // Django (dismissible + role="alert"), pour ne jamais toucher aux alertes
      // statiques d'une page (erreurs de formulaire, encarts d'information…).
      alertes = document.querySelectorAll('.alert-dismissible[role="alert"]');
    }

    var dejaVus = {};
    for (var i = 0; i < alertes.length; i++) {
      var alerte = alertes[i];
      if (alerte.hasAttribute('data-airplus-keep')) {
        continue;
      }
      var texte = texteDepuisAlerte(alerte);
      if (!texte) {
        alerte.parentNode && alerte.parentNode.removeChild(alerte);
        continue;
      }
      var type = typeDepuisAlerte(alerte);
      var cle = type + '|' + texte;
      if (!dejaVus[cle]) {
        dejaVus[cle] = true;
        window.airplusToast(type, texte);
      }
      // L'alerte inline disparaît : le toast la remplace.
      alerte.parentNode && alerte.parentNode.removeChild(alerte);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', convertirMessagesServeur);
  } else {
    convertirMessagesServeur();
  }
})(window, document);
