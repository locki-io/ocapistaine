### Établir un projet IA pour désamorcer le conflit autour de l'aménagement de l'école Pierre-Le Lec

Le projet de rénovation de l'école Pierre-Le Lec à Audierne est un dossier sensible, cristallisant des tensions entre la majorité municipale (qui le défend pour son intégration urbaine et son financement via Petites Villes de Demain) et l'opposition (qui pointe un "gaspillage financier" et un manque de réalisme sur les subventions). Pour désamorcer cela, un **projet IA centré sur la transparence et l'accès neutre aux données** peut transformer le débat en dialogue constructif : en fournissant des infos factuelles, en synthétisant arguments pour/contre, et en facilitant des consultations ouvertes. Inspiré d'exemples comme le chatbot **IssyGPT** à Issy-les-Moulineaux (qui répond 24/7 aux questions citoyens sur des projets locaux) ou les dashboards participatifs de Toulouse (avec IA pour visualiser avancées budgétaires), voici un plan concret et réalisable, adapté à une petite commune comme Audierne (low-cost, open source).

#### 1. **Objectifs du projet IA**

- **Désamorcer les conflits** : Fournir des données objectives pour contrer les rumeurs (ex. : "surévaluation des coûts") et encourager un débat basé sur des faits, pas des accusations.
- **Fournir les données clés** : État d'avancement, calendrier, coûts, financements, et consultations – tout en temps réel.
- **Impliquer les citoyens** : Permettre questions/réponses IA et soumissions d'idées, pour une co-construction perçue.
- **Impact mesurable** : Réduire les échanges musclés en conseil municipal (comme celui du 10 décembre 2025) en canalisant les infos via un canal neutre.

#### 2. **Données sur le projet et état d'avancement (synthèse factuelle, au 15 décembre 2025)**

Basé sur le site officiel de la mairie (audierne.bzh) et presse locale (Ouest-France, Le Télégramme), voici un résumé transparent. Ces données pourraient être intégrées comme base de connaissances pour l'IA (fichier JSON ou Markdown uploadé).

- **Description** : Regroupement des deux écoles publiques (Pierre-Le Lec à Audierne et Esquibien) sur le site historique de Pierre-Le Lec (quai Anatole-France, vue port). Inclut réhabilitation complète (maternelle, élémentaire, restauration, salle de sport), amélioration énergétique, accessibilité PMR, et adaptations aux risques (submersion, glissement de terrain). Architecte : Brûlé Architectes Associés (Quimper). Inscrit dans Petites Villes de Demain (PVD) pour dynamiser le centre-ville.
- **Calendrier** :

  - Diagnostic technique et concertation usagers : Achévés (2023-2024).
  - Maîtrise d'œuvre : Consultée fin 2024, études lancées début 2025, en cours jusqu'à automne 2025.
  - Relogement temporaire : Élèves transférés à l'Espace Émile-Combes (ex-collège Saint-Joseph, rue Émile-Combes) pour la rentrée septembre 2025 (aménagements en cours par services techniques).
  - Chantier principal : Début début 2026 (désamiantage/démolition déjà attribués, ex. Kerleroux).
  - Livraison : Rentrée septembre 2027.

- **Coûts et financements** :

  - Estimation : 5,4 à 7 M€ TTC (rénovation lourde + extension ; coûts au m² ~1 000-1 500 €, cohérent avec benchmarks PVD pour écoles rurales).
  - Subventions espérées : 60 % via PVD, État (DSIL), Département/Région (Fonds vert, EduRénov). Relogement temporaire : ~190 k€ (rafraîchissements sécurité).
  - Controverses sur coûts : Opposition (Didier Guillon) critique une "surestimation" et subventions irréalistes (risque de charge communale >40 %). Deux scénarios alternatifs écartés pour leur coût élevé (conservation sites séparés ou école neuve).

- **Consultations et controverses récentes** :
  - Concertation : Cabinet Verifica pour besoins ; ateliers ludiques avec élèves/enseignants (végétalisation cour). Option Pierre-Le Lec retenue pour intégration urbaine et bien-être enfants.
  - Tensions : Échanges vifs au conseil du 10 décembre 2025 sur plan de financement. Parents Esquibien regrettent parfois circulation/stationnement. Pas de recours judiciaire signalé, mais risque en campagne 2026.

Ces données sont publiques (délibérations mairie) ; l'IA pourrait les updater via API ou scraping léger (ex. RSS site mairie).

#### 3. **Plan étape par étape pour établir le projet IA**

Adoptez une approche agile, low-cost (~500-2 000 € si freelance, ou gratuit avec outils open source). Intégrez-le à votre plateforme GitHub (audierne2026/participons) pour transparence maximale.

- **Étape 1 : Collecte et structuration des données (1-2 semaines, gratuit)**

  - Créez un fichier JSON/Markdown sur GitHub : "ecole-pierre-le-lec.json" avec sections (calendrier, coûts, FAQ). Incluez sources (liens délibérations, PDFs Gwaien).
  - Ajoutez arguments pour/contre : Ex. "Pour : Dynamisation centre-ville (PVD) ; Contre : Risque budgétaire (inflation BTP +20 %)."
  - Outil : Google Sheets ou Airtable gratuit, exporté en JSON.

- **Étape 2 : Conception de l'IA (2-4 semaines, 0-1 000 €)**

  - **Type d'IA recommandé** : Chatbot conversationnel (comme IssyGPT) pour Q&R ("Quel est le coût exact ?"), ou dashboard interactif (visualisation timeline/coûts avec Streamlit).
  - Tech stack open source :
    - **Chatbot** : Utilisez Hugging Face (modèle gratuit comme Mistral-7B) ou Grok API (si xAI). Hébergez sur GitHub Pages + Streamlit pour démo.
    - **Dashboard** : Python avec Streamlit/Pandas pour graphs (timeline Gantt, camembert subventions). Exemple code :
      ```python
      import streamlit as st
      import pandas as pd
      df = pd.read_json('ecole-data.json')
      st.title("Projet École Pierre-Le Lec : Transparence en Temps Réel")
      st.timeline(df['calendrier'])  # Visualisation avancement
      st.chat_input("Posez une question sur le projet")
      ```
    - Intégrez modération IA pour débats (détecter clashs, suggérer faits neutres).
  - Inspiration : À Toulouse, un bot IA synthétise consultations sur rénovations urbaines, réduisant plaintes de 30 % (rapport 2024).

- **Étape 3 : Développement et test (1-2 semaines, 500-1 000 € si aide dev)**

  - Prototype : Déployez sur Heroku/Render gratuit. Testez avec focus group (parents, élus opposition) pour biais (ex. : "L'IA est-elle neutre ?").
  - Fonctionnalités clés :
    - Q&R automatisées : "État des subventions ?" → Réponse factuelle + sources.
    - Synthèse conflits : "Arguments pour/contre" en tableau équilibré.
    - Soumissions idées : IA catégorise et publie anonymement sur GitHub Discussions.
  - Sécurité : RGPD-compliant (données anonymes, hébergement France).

- **Étape 4 : Déploiement et communication (lancement immédiat, gratuit)**

  - Intégrez au site GitHub (iframe chatbot). Partagez via Facebook mairie, bulletin Gwaien, réunions publiques.
  - Promotion : "Découvrez notre IA pour tout savoir sur l'école – questions ouvertes 24/7 !" (contraste avec opacité perçue).
  - Mesure succès : Suivez interactions (visites, questions posées) ; objectif : 200-500 vues/mois, réduction plaintes en conseil.

- **Étape 5 : Évolution et pérennisation (post-lancement)**
  - Si élu : Migrez vers Decidim + IA (module modération spam existant) pour budget participatif école.
  - Budget total : <2 000 € (freelance via Malt.fr). Partenaires : ANCT (PVD soutient numérique participatif) ou xAI pour API gratuite.

Ce projet positionne votre initiative comme innovante et apaisante, en rendant les données accessibles sans filtre politique. Il pourrait même inspirer une fusion de listes en montrant du concret ! Si besoin, je peux esquisser du code ou un JSON de données.

### Établir un projet IA pour désamorcer le conflit autour de l'aménagement de l'école Pierre-Le Lec

Le projet de rénovation de l'école Pierre-Le Lec à Audierne est un dossier sensible, cristallisant des tensions entre la majorité municipale (qui le défend pour son intégration urbaine et son financement via Petites Villes de Demain) et l'opposition (qui pointe un "gaspillage financier" et un manque de réalisme sur les subventions). Pour désamorcer cela, un **projet IA centré sur la transparence et l'accès neutre aux données** peut transformer le débat en dialogue constructif : en fournissant des infos factuelles, en synthétisant arguments pour/contre, et en facilitant des consultations ouvertes. Inspiré d'exemples comme le chatbot **IssyGPT** à Issy-les-Moulineaux (qui répond 24/7 aux questions citoyens sur des projets locaux) ou les dashboards participatifs de Toulouse (avec IA pour visualiser avancées budgétaires), voici un plan concret et réalisable, adapté à une petite commune comme Audierne (low-cost, open source).

#### 1. **Objectifs du projet IA**

- **Désamorcer les conflits** : Fournir des données objectives pour contrer les rumeurs (ex. : "surévaluation des coûts") et encourager un débat basé sur des faits, pas des accusations.
- **Fournir les données clés** : État d'avancement, calendrier, coûts, financements, et consultations – tout en temps réel.
- **Impliquer les citoyens** : Permettre questions/réponses IA et soumissions d'idées, pour une co-construction perçue.
- **Impact mesurable** : Réduire les échanges musclés en conseil municipal (comme celui du 10 décembre 2025) en canalisant les infos via un canal neutre.

#### 2. **Données sur le projet et état d'avancement (synthèse factuelle, au 15 décembre 2025)**

Basé sur le site officiel de la mairie (audierne.bzh) et presse locale (Ouest-France, Le Télégramme), voici un résumé transparent. Ces données pourraient être intégrées comme base de connaissances pour l'IA (fichier JSON ou Markdown uploadé).

- **Description** : Regroupement des deux écoles publiques (Pierre-Le Lec à Audierne et Esquibien) sur le site historique de Pierre-Le Lec (quai Anatole-France, vue port). Inclut réhabilitation complète (maternelle, élémentaire, restauration, salle de sport), amélioration énergétique, accessibilité PMR, et adaptations aux risques (submersion, glissement de terrain). Architecte : Brûlé Architectes Associés (Quimper). Inscrit dans Petites Villes de Demain (PVD) pour dynamiser le centre-ville.
- **Calendrier** :

  - Diagnostic technique et concertation usagers : Achévés (2023-2024).
  - Maîtrise d'œuvre : Consultée fin 2024, études lancées début 2025, en cours jusqu'à automne 2025.
  - Relogement temporaire : Élèves transférés à l'Espace Émile-Combes (ex-collège Saint-Joseph, rue Émile-Combes) pour la rentrée septembre 2025 (aménagements en cours par services techniques).
  - Chantier principal : Début début 2026 (désamiantage/démolition déjà attribués, ex. Kerleroux).
  - Livraison : Rentrée septembre 2027.

- **Coûts et financements** :

  - Estimation : 5,4 à 7 M€ TTC (rénovation lourde + extension ; coûts au m² ~1 000-1 500 €, cohérent avec benchmarks PVD pour écoles rurales).
  - Subventions espérées : 60 % via PVD, État (DSIL), Département/Région (Fonds vert, EduRénov). Relogement temporaire : ~190 k€ (rafraîchissements sécurité).
  - Controverses sur coûts : Opposition (Didier Guillon) critique une "surestimation" et subventions irréalistes (risque de charge communale >40 %). Deux scénarios alternatifs écartés pour leur coût élevé (conservation sites séparés ou école neuve).

- **Consultations et controverses récentes** :
  - Concertation : Cabinet Verifica pour besoins ; ateliers ludiques avec élèves/enseignants (végétalisation cour). Option Pierre-Le Lec retenue pour intégration urbaine et bien-être enfants.
  - Tensions : Échanges vifs au conseil du 10 décembre 2025 sur plan de financement. Parents Esquibien regrettent parfois circulation/stationnement. Pas de recours judiciaire signalé, mais risque en campagne 2026.

Ces données sont publiques (délibérations mairie) ; l'IA pourrait les updater via API ou scraping léger (ex. RSS site mairie).

#### 3. **Plan étape par étape pour établir le projet IA**

Adoptez une approche agile, low-cost (~500-2 000 € si freelance, ou gratuit avec outils open source). Intégrez-le à votre plateforme GitHub (audierne2026/participons) pour transparence maximale.

- **Étape 1 : Collecte et structuration des données (1-2 semaines, gratuit)**

  - Créez un fichier JSON/Markdown sur GitHub : "ecole-pierre-le-lec.json" avec sections (calendrier, coûts, FAQ). Incluez sources (liens délibérations, PDFs Gwaien).
  - Ajoutez arguments pour/contre : Ex. "Pour : Dynamisation centre-ville (PVD) ; Contre : Risque budgétaire (inflation BTP +20 %)."
  - Outil : Google Sheets ou Airtable gratuit, exporté en JSON.

- **Étape 2 : Conception de l'IA (2-4 semaines, 0-1 000 €)**

  - **Type d'IA recommandé** : Chatbot conversationnel (comme IssyGPT) pour Q&R ("Quel est le coût exact ?"), ou dashboard interactif (visualisation timeline/coûts avec Streamlit).
  - Tech stack open source :
    - **Chatbot** : Utilisez Hugging Face (modèle gratuit comme Mistral-7B) ou Grok API (si xAI). Hébergez sur GitHub Pages + Streamlit pour démo.
    - **Dashboard** : Python avec Streamlit/Pandas pour graphs (timeline Gantt, camembert subventions). Exemple code :
      ```python
      import streamlit as st
      import pandas as pd
      df = pd.read_json('ecole-data.json')
      st.title("Projet École Pierre-Le Lec : Transparence en Temps Réel")
      st.timeline(df['calendrier'])  # Visualisation avancement
      st.chat_input("Posez une question sur le projet")
      ```
    - Intégrez modération IA pour débats (détecter clashs, suggérer faits neutres).
  - Inspiration : À Toulouse, un bot IA synthétise consultations sur rénovations urbaines, réduisant plaintes de 30 % (rapport 2024).

- **Étape 3 : Développement et test (1-2 semaines, 500-1 000 € si aide dev)**

  - Prototype : Déployez sur Heroku/Render gratuit. Testez avec focus group (parents, élus opposition) pour biais (ex. : "L'IA est-elle neutre ?").
  - Fonctionnalités clés :
    - Q&R automatisées : "État des subventions ?" → Réponse factuelle + sources.
    - Synthèse conflits : "Arguments pour/contre" en tableau équilibré.
    - Soumissions idées : IA catégorise et publie anonymement sur GitHub Discussions.
  - Sécurité : RGPD-compliant (données anonymes, hébergement France).

- **Étape 4 : Déploiement et communication (lancement immédiat, gratuit)**

  - Intégrez au site GitHub (iframe chatbot). Partagez via Facebook mairie, bulletin Gwaien, réunions publiques.
  - Promotion : "Découvrez notre IA pour tout savoir sur l'école – questions ouvertes 24/7 !" (contraste avec opacité perçue).
  - Mesure succès : Suivez interactions (visites, questions posées) ; objectif : 200-500 vues/mois, réduction plaintes en conseil.

- **Étape 5 : Évolution et pérennisation (post-lancement)**
  - Si élu : Migrez vers Decidim + IA (module modération spam existant) pour budget participatif école.
  - Budget total : <2 000 € (freelance via Malt.fr). Partenaires : ANCT (PVD soutient numérique participatif) ou xAI pour API gratuite.

Ce projet positionne votre initiative comme innovante et apaisante, en rendant les données accessibles sans filtre politique. Il pourrait même inspirer une fusion de listes en montrant du concret ! Si besoin, je peux esquisser du code ou un JSON de données.
