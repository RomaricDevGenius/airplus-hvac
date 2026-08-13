/**
 * AIRPLUS HVAC — Anti double-soumission et indicateur de chargement des formulaires
 * =================================================================================
 *
 * Problème traité : à la soumission d'un formulaire du back-office, l'utilisateur
 * n'avait aucun retour visuel. Sur une connexion lente (envoi d'image produit
 * notamment), l'absence de retour pousse à recliquer — et un double clic sur
 * « Enregistrer » crée DEUX enregistrements. C'est un bug de données, pas un
 * simple confort.
 *
 * ---------------------------------------------------------------------------
 * 1) ACTIVATION AUTOMATIQUE
 * ---------------------------------------------------------------------------
 * Aucun code à écrire dans les gabarits : tout <form method="post"> de la page
 * est pris en charge (ce script n'est chargé que par le layout du back-office).
 * Les formulaires en GET (recherche, filtres) ne sont jamais concernés.
 *
 * Exclusion explicite, sur le <form> ou sur le bouton :
 *
 *   <form method="post" data-airplus-no-loader> …
 *   <button type="submit" data-airplus-no-loader>…</button>
 *
 * Texte d'attente personnalisé (sur le bouton, sinon sur le formulaire) :
 *
 *   <button type="submit" data-airplus-loading-text="Enregistrement…">Enregistrer</button>
 *
 * Variante utilisée uniquement si un fichier est réellement joint (téléversement,
 * donc attente plus longue) — sinon c'est le texte normal qui s'affiche :
 *
 *   <button type="submit"
 *           data-airplus-loading-text="Enregistrement…"
 *           data-airplus-loading-text-file="Envoi de l'image…">Enregistrer</button>
 *
 * Sans attribut, le texte par défaut est « Traitement… » : neutre, il convient
 * aussi bien à un enregistrement qu'à une suppression ou une déconnexion.
 *
 * ---------------------------------------------------------------------------
 * 2) COMPORTEMENT
 * ---------------------------------------------------------------------------
 *  - le contenu du bouton est remplacé par un spinner Bootstrap + le texte d'attente,
 *    la largeur d'origine étant figée (min-width) pour que la mise en page ne saute pas ;
 *  - le bouton est désactivé et toute soumission ultérieure du même formulaire est bloquée
 *    (couvre aussi la touche Entrée, pas seulement le double clic) ;
 *  - si l'utilisateur revient par le bouton « Précédent » du navigateur, l'état initial
 *    est restauré : pas de bouton figé et inutilisable.
 *
 * ---------------------------------------------------------------------------
 * 3) LES DEUX PIÈGES CLASSIQUES, ET COMMENT ILS SONT ÉVITÉS
 * ---------------------------------------------------------------------------
 * a) Validation HTML5 : on écoute l'événement `submit` du formulaire, JAMAIS le
 *    `click` du bouton. Quand un champ `required` est vide, le navigateur bloque
 *    la soumission et n'émet PAS `submit` : le bouton n'est donc jamais gelé et
 *    l'utilisateur peut corriger puis resoumettre. Un script branché sur `click`
 *    aurait figé le bouton sur un formulaire jamais parti.
 *
 * b) Nom/valeur du bouton soumetteur : un `<button name="action" value="x">`
 *    désactivé n'est plus inclus dans les données envoyées. La désactivation est
 *    donc différée d'un tour de boucle (setTimeout 0), après la construction des
 *    données de formulaire par le navigateur. Idem, la `value` d'un
 *    `<input type="submit">` n'est jamais modifiée : elle serait envoyée au serveur.
 *
 * ---------------------------------------------------------------------------
 * 4) COEXISTENCE AVEC src/assets/js/airplus-feedback.js
 * ---------------------------------------------------------------------------
 *  - Confirmation ANNULÉE : le socle fait preventDefault sur le `click`, donc aucun
 *    événement `submit` n'est émis. Ce module n'est jamais déclenché, le bouton
 *    reste utilisable. C'est une conséquence directe du choix « submit, pas click ».
 *  - Confirmation ACCEPTÉE : le socle ouvre sa modale plein écran (airplusLoading)
 *    puis appelle form.requestSubmit(), ce qui émet bien `submit`. On détecte alors
 *    la présence de cette modale (.airplus-loading) et on n'applique QUE le verrou
 *    anti double-soumission, sans toucher au bouton : pas de double indicateur.
 *  - Si SweetAlert2 est absent, le socle retombe sur window.confirm et n'affiche
 *    aucune modale : la modale n'étant pas détectée, le spinner du bouton prend
 *    le relais. L'utilisateur a toujours un retour visuel.
 *
 * Aucune dépendance : JavaScript natif, pas de jQuery, pas de CDN.
 */

'use strict';

(function (window, document) {
  // Attribut d'exclusion (posable sur le <form> ou sur le bouton)
  var ATTR_EXCLUSION = 'data-airplus-no-loader';
  // Attribut de personnalisation du texte d'attente
  var ATTR_TEXTE = 'data-airplus-loading-text';
  // Variante du texte d'attente utilisée quand un fichier est réellement joint
  var ATTR_TEXTE_FICHIER = 'data-airplus-loading-text-file';
  // Marqueur posé sur le formulaire pendant l'envoi
  var ATTR_EN_COURS = 'data-airplus-envoi-en-cours';
  // Texte d'attente par défaut, volontairement neutre
  var TEXTE_DEFAUT = 'Traitement…';

  /** Vrai si l'élément (ou son formulaire) demande explicitement à être ignoré. */
  function estExclu(element) {
    return !!(element && element.hasAttribute && element.hasAttribute(ATTR_EXCLUSION));
  }

  /**
   * La modale de chargement du socle airplus-feedback.js est-elle affichée ?
   * Elle est identifiée par la classe `airplus-loading` (customClass.popup).
   * Si oui, l'écran est déjà bloqué : inutile (et disgracieux) d'habiller le bouton.
   */
  function chargementSocleAffiche() {
    var modale = document.querySelector('.airplus-loading');
    if (!modale) {
      return false;
    }
    // Une modale retirée ou masquée ne compte pas : on ne se prive du spinner
    // que si l'écran est réellement couvert.
    return !!(modale.offsetParent || modale.getClientRects().length);
  }

  /** Liste des boutons susceptibles de soumettre ce formulaire. */
  function boutonsDeSoumission(form, soumetteur) {
    var trouves = [];
    var candidats = form.querySelectorAll(
      'button[type="submit"], button:not([type]), input[type="submit"], input[type="image"]'
    );
    for (var i = 0; i < candidats.length; i++) {
      trouves.push(candidats[i]);
    }
    // Bouton rattaché au formulaire par l'attribut `form=""` : hors de l'arbre du <form>.
    if (soumetteur && trouves.indexOf(soumetteur) === -1) {
      trouves.push(soumetteur);
    }
    return trouves;
  }

  /** Un fichier est-il réellement joint à ce formulaire ? (téléversement = attente longue) */
  function fichierJoint(form) {
    var champs = form.querySelectorAll('input[type="file"]');
    for (var i = 0; i < champs.length; i++) {
      if (champs[i].files && champs[i].files.length > 0) {
        return true;
      }
    }
    return false;
  }

  /** Lit un attribut sur le bouton, à défaut sur le formulaire. */
  function attributBoutonOuForm(form, bouton, nom) {
    var valeur = bouton && bouton.getAttribute ? bouton.getAttribute(nom) : null;
    return valeur || form.getAttribute(nom);
  }

  /**
   * Texte d'attente : variante « fichier » si un fichier est joint (le téléversement
   * est la vraie attente sur une connexion lente), sinon texte normal, sinon défaut.
   */
  function texteAttente(form, bouton) {
    var texteFichier = attributBoutonOuForm(form, bouton, ATTR_TEXTE_FICHIER);
    if (texteFichier && fichierJoint(form)) {
      return texteFichier;
    }
    return attributBoutonOuForm(form, bouton, ATTR_TEXTE) || TEXTE_DEFAUT;
  }

  /** Habille un bouton : largeur figée, spinner, texte d'attente, désactivation différée. */
  function habillerBouton(bouton, texte) {
    if (bouton._airplusEtat) {
      return; // déjà traité
    }

    // Mémorisation de l'état initial pour pouvoir le restaurer (retour arrière navigateur).
    var etat = {
      html: bouton.innerHTML,
      minWidth: bouton.style.minWidth,
      desactive: bouton.disabled,
      ariaBusy: bouton.getAttribute('aria-busy')
    };
    bouton._airplusEtat = etat;

    // La largeur d'origine est figée AVANT de changer le contenu : la mise en page ne bouge pas.
    var largeur = bouton.getBoundingClientRect().width;
    if (largeur > 0) {
      bouton.style.minWidth = Math.ceil(largeur) + 'px';
    }
    bouton.setAttribute('aria-busy', 'true');

    // Un <input type="submit"> envoie sa `value` au serveur : on n'y touche pas,
    // seule la désactivation s'applique. Les <button> reçoivent le spinner.
    if (bouton.tagName === 'BUTTON') {
      var libelle = (bouton.textContent || '').trim();

      var spinner = document.createElement('span');
      spinner.className = 'spinner-border spinner-border-sm';
      spinner.setAttribute('role', 'status');
      spinner.setAttribute('aria-hidden', 'true');

      bouton.textContent = '';
      bouton.appendChild(spinner);

      // Bouton icône seule (tableaux, barres d'actions) : spinner sans texte,
      // sinon la ligne du tableau se déformerait.
      if (libelle) {
        var etiquette = document.createElement('span');
        etiquette.className = 'ms-2';
        etiquette.textContent = texte;
        bouton.appendChild(etiquette);
      }
    }

    // Désactivation différée : au moment du `submit`, le navigateur n'a pas encore
    // construit les données du formulaire. Désactiver tout de suite ferait perdre le
    // couple name/value du bouton soumetteur. Un tour de boucle suffit à l'éviter.
    window.setTimeout(function () {
      bouton.disabled = true;
    }, 0);
  }

  /** Restaure un bouton dans son état d'avant soumission. */
  function restaurerBouton(bouton) {
    var etat = bouton._airplusEtat;
    if (!etat) {
      return;
    }
    bouton.innerHTML = etat.html;
    bouton.style.minWidth = etat.minWidth || '';
    bouton.disabled = !!etat.desactive;
    if (etat.ariaBusy === null || typeof etat.ariaBusy === 'undefined') {
      bouton.removeAttribute('aria-busy');
    } else {
      bouton.setAttribute('aria-busy', etat.ariaBusy);
    }
    bouton._airplusEtat = null;
  }

  /** Ce formulaire est-il déjà parti ? */
  function envoiEnCours(form) {
    return form.hasAttribute(ATTR_EN_COURS);
  }

  // ---------------------------------------------------------------------------
  // a) Blocage des soumissions suivantes — phase de CAPTURE
  // ---------------------------------------------------------------------------
  // En capture, on passe avant tout gestionnaire de la page : la deuxième
  // soumission est coupée net, quoi que fasse le reste du code.
  document.addEventListener(
    'submit',
    function (event) {
      var form = event.target;
      if (!form || form.tagName !== 'FORM') {
        return;
      }
      if (envoiEnCours(form)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true
  );

  // ---------------------------------------------------------------------------
  // b) Première soumission : verrou + habillage — phase de BOUILLONNEMENT
  // ---------------------------------------------------------------------------
  // En bouillonnement, les gestionnaires de la page (validation maison, etc.) ont
  // déjà tourné : si l'un d'eux a annulé la soumission, on ne verrouille rien.
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form || form.tagName !== 'FORM') {
      return;
    }
    // Soumission annulée par un autre script : le formulaire ne part pas.
    if (event.defaultPrevented) {
      return;
    }
    // Formulaires en GET (recherche, filtres) : aucun risque de doublon.
    if ((form.getAttribute('method') || 'get').toLowerCase() !== 'post') {
      return;
    }
    if (estExclu(form) || envoiEnCours(form)) {
      return;
    }

    var soumetteur = event.submitter || null;
    if (estExclu(soumetteur)) {
      return;
    }

    // Ceinture et bretelles : si la validation HTML5 échouait malgré tout,
    // on laisse le formulaire intact (le navigateur n'émet normalement pas `submit`).
    if (!form.noValidate && typeof form.checkValidity === 'function' && !form.checkValidity()) {
      return;
    }

    // Le verrou est posé dans tous les cas : c'est lui qui empêche le doublon.
    form.setAttribute(ATTR_EN_COURS, '1');

    // Le socle airplus-feedback.js affiche déjà sa modale plein écran après
    // confirmation : on s'arrête au verrou pour ne pas doubler l'indicateur.
    if (chargementSocleAffiche()) {
      return;
    }

    var boutons = boutonsDeSoumission(form, soumetteur);
    // Liste conservée sur le formulaire : elle sert à la restauration au retour arrière,
    // y compris pour un bouton rattaché par l'attribut `form=""` (hors de l'arbre du <form>).
    form._airplusBoutons = boutons;
    for (var i = 0; i < boutons.length; i++) {
      var bouton = boutons[i];
      if (estExclu(bouton)) {
        continue;
      }
      habillerBouton(bouton, texteAttente(form, bouton));
    }
  });

  // ---------------------------------------------------------------------------
  // c) Retour par le bouton « Précédent » du navigateur
  // ---------------------------------------------------------------------------
  // Avec le cache de navigation (bfcache), la page revient telle qu'elle a été
  // quittée : bouton désactivé, spinner tournant, formulaire verrouillé. On remet
  // tout à l'état initial, sinon la page est inutilisable.
  window.addEventListener('pageshow', function (event) {
    var vientDuCache = event.persisted;
    if (!vientDuCache && window.performance && typeof window.performance.getEntriesByType === 'function') {
      var nav = window.performance.getEntriesByType('navigation');
      if (nav && nav.length && nav[0].type === 'back_forward') {
        vientDuCache = true;
      }
    }
    if (!vientDuCache) {
      return;
    }

    var formulaires = document.querySelectorAll('form[' + ATTR_EN_COURS + ']');
    for (var i = 0; i < formulaires.length; i++) {
      var form = formulaires[i];
      form.removeAttribute(ATTR_EN_COURS);
      var boutons = form._airplusBoutons || boutonsDeSoumission(form, null);
      for (var j = 0; j < boutons.length; j++) {
        restaurerBouton(boutons[j]);
      }
      form._airplusBoutons = null;
    }
  });
})(window, document);
