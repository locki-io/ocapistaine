### Compte rendu final : Stratégie numérique pour une campagne municipale transparente à Audierne-Esquibien (2026)

Au 14 décembre 2025, la campagne pour les municipales de mars 2026 à Audierne-Esquibien (3 700 habitants) est très animée avec **quatre listes déclarées** :

- **Florent Lardic** (avec Carine Thomas) : Liste de renouveau, lancée tôt (juin 2025), axée sur des bases saines et apaisées ; page Facebook active.
- **Michel Van Praët** : Liste « S’unir pour Audierne-Esquibien », focus sur politique apaisée, solidarité et écologie ; discussions possibles de fusion.
- **Éric Bosser** : Liste « Construisons l’avenir », service aux habitants sans politicienne ; origines locales fortes.
- **Didier Guillon** : Liste « Passons à l’action ! » (annoncée le 4 décembre), double parité, priorités logement/associations/patrimoine ; style incisif connu.

Le maire sortant Gurvan Kerloc’h ne se représente pas, et les tensions passées persistent (ex. débats houleux sur l’école Pierre-Le Lec en décembre 2025).

Votre approche, centrée sur **transparence, collaboratif et apaisement**, se différencie parfaitement : un site open source dès la campagne montre un engagement concret, réutilisable si élu (migration vers RVVN/Decidim officielle).

#### Plan de mise en place de la plateforme (janvier-mars 2026)

Priorité : **GitHub Pages statique** (gratuit, simple, transparent) pour démarrer vite. Tout open source sur GitHub → traçabilité publique des modifications.

| Phase                           | Délai                           | Actions techniques                                                                                                                                                                                                                                                                                                                                                                                                                   | Contenus & fonctionnalités                                                                                                                                                                                                                                                                                                       | Coût estimé                             |
| ------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| **Préparation & lancement**     | Décembre 2025 - 10 janvier 2026 | - Créer repo GitHub (ex. username.github.io ou repo dédié avec gh-pages).<br>- Choisir générateur : Jekyll (support natif GitHub) ou Hugo (plus rapide).<br>- Thème gratuit : Minimal (simple), ou adapter "Clean Blog" / "Agency" Jekyll pour look pro/campagne (recherche thèmes politiques : souvent basiques, personnalisez avec logo/slogan).<br>- Domaine custom : Acheter votreliste-audierne.fr (~10€/an) et lier via CNAME. | - Page d'accueil : Slogan ("Audierne-Esquibien ensemble : écoutons, co-construisons"), présentation liste, appel à contributions.<br>- Sections : Programme évolutif, Actualités, Contact.<br>- Embed formulaires (Framaforms/Google Forms gratuit) pour idées citoyens (thèmes : logement, associations, école, environnement). | 0-50€ (domaine).                        |
| **Collaboratif basique**        | 11-31 janvier 2026              | - Intégrer formulaires pour consultations thématiques.<br>- Page "Vos idées" : Publiez synthèses manuelles (PDF/Markdown) des réponses reçues → transparence immédiate.<br>- Ajouter RSS ou newsletter (Brevo gratuit).                                                                                                                                                                                                              | - Lancer 3-4 consultations (ex. "Priorités logement ?", "Soutien associations ?").<br>- Restitution publique (réunions + site).<br>- Lien vers Facebook pour mobilisation.                                                                                                                                                       | Gratuit.                                |
| **Amélioration & mobilisation** | Février 2026                    | - Ajouter blog Jekyll pour actualités/synthèses.<br>- Version mobile optimisée.<br>- Exports CSV des idées (pour future migration).                                                                                                                                                                                                                                                                                                  | - Programme final co-construit affiché.<br>- Carte interactive simple (Leaflet embed) des propositions locales si pertinent.                                                                                                                                                                                                     | Gratuit.                                |
| **Post-élection (si victoire)** | Avril 2026+                     | - Contacter RVVN pour adhésion/instance Decidim (mutualisée, coûts rationalisés ~1-3k€/an pour petite commune).<br>- Importer données campagne (idées/synthèses) comme "processus historique".<br>- Garder GitHub Pages comme archive/vitrine complémentaire.                                                                                                                                                                        | - Plateforme officielle Decidim pour budget participatif annuel, consultations permanentes.                                                                                                                                                                                                                                      | Devis RVVN (bas pour petites communes). |

**Avantages clés** :

- Transparence radicale (code public sur GitHub).
- Inclusivité (formulaires anonymes + versions papier en réunions).
- Réutilisabilité totale : Vos efforts servent la campagne **et** la future mairie.
- Différenciation : Montrez que vous êtes prêt à gouverner avec outils modernes, contrairement aux clashes perçus ailleurs.

Lancez dès janvier : un site live renforcera votre crédibilité et attirera les habitants lassés des divisions. Si besoin d’un thème Jekyll spécifique ou d’aide pour le setup, précisez ! Bonne route pour la campagne.

comparatif :
Oui, exactement ! Ce que vous cherchez s'appelle **GitHub Pages**.

C'est le service gratuit de GitHub qui permet d'héberger directement un **site statique** (fichiers HTML, CSS, JS, Markdown, images...) depuis un repository GitHub. Vous poussez vos modifications, et le site est mis à jour automatiquement – zéro serveur à gérer, zéro coût.

### Pourquoi c'est encore plus simple pour votre campagne à Audierne ?

- **Ultra-rapide à mettre en place** : Créez un repo nommé `votreusername.github.io` (ou dans un repo normal avec branche gh-pages/docs), ajoutez un index.html, et c'est live en minutes.
- **Pas besoin de générateur complexe** au départ : Commencez avec du HTML pur, ou ajoutez un thème gratuit (ex. : Minimal Mistakes, Beautiful Jekyll).
- **Intégration parfaite avec générateurs statiques** (SSG) :
  - **Jekyll** : Le plus simple avec GitHub Pages (support natif, pas de build manuel).
  - **Hugo** : Très rapide, mais nécessite GitHub Actions pour build auto.
  - Autres populaires : Eleventy (11ty), Astro, Zola – tous open source et hébergés sur GitHub.
- **Transparence maximale** : Tout le code source est public sur GitHub → les habitants voient exactement ce que vous publiez, modifications trackées (historique des commits). Parfait pour différencier votre liste par "ouvert et traçable".
- **Domaine custom gratuit** : Ajoutez un CNAME pour avoir votreliste-audierne.fr.

### Comparaison rapide pour votre cas (campagne low-cost, transparence)

| Option                               | Simplicité                  | Transparence            | Collaboratif                   | Coût             | Recommandé pour Audierne                                |
| ------------------------------------ | --------------------------- | ----------------------- | ------------------------------ | ---------------- | ------------------------------------------------------- |
| **GitHub Pages pur (HTML statique)** | ⭐⭐⭐⭐⭐ (le plus simple) | ⭐⭐⭐⭐ (code visible) | ⭐⭐ (éditable par équipe Git) | Gratuit          | Idéal pour démarrer vite, site vitrine + programme PDF. |
| **GitHub Pages + Jekyll**            | ⭐⭐⭐⭐                    | ⭐⭐⭐⭐⭐              | ⭐⭐⭐                         | Gratuit          | Ajoute blog/actualités faciles, thèmes pros.            |
| **GitHub Pages + Hugo/Eleventy**     | ⭐⭐⭐                      | ⭐⭐⭐⭐⭐              | ⭐⭐⭐⭐                       | Gratuit          | Plus rapide/performant, si vous avez un dev.            |
| **Decidim (Ruby on Rails)**          | ⭐⭐                        | ⭐⭐⭐⭐⭐              | ⭐⭐⭐⭐⭐                     | 1-5k€/an hébergé | Pour consultations avancées, mais plus lourd.           |

Pour une campagne municipale comme la vôtre : commencez par **GitHub Pages avec HTML/Jekyll** – c'est le plus simple et suffisant pour un site clair (présentation liste, programme évolutif, formulaire contact via Google Forms embeddé). Ajoutez Decidim plus tard (sous-domaine) si vous voulez des votes/consultations poussées.

Tutoriel rapide : Allez sur https://pages.github.com/ – en 5 minutes, vous avez un site live. Si besoin d'aide pour un thème campagne, dites-moi ! Cela renforcera votre image "moderne et ouverte".
