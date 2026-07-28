# Veille hebdo ENGIE Green — Solaire au sol (>1 MW) / Éolien / BESS / Hydro-STEP

Outil autonome (indépendant de Claude Code) pour générer la synthèse
hebdomadaire. Sources publiques (Tecsol Quotidien, PV Magazine) scrapées
automatiquement ; GreenUnivers via PDF déposés manuellement (voir section 3,
raison légale). Utilise l'API Mistral pour la synthèse.

La web app a deux onglets :
- **"Veille automatique"** : le workflow d'origine (scrape + PDF GreenUnivers +
  Mistral juge l'in_scope/la priorité + synthèse hebdo P1/P2), voir section 2.
- **"Résumés PDF"** : dépose des PDF en vrac, Mistral rédige juste titre +
  résumé (même nomenclature) sans décider s'ils sont dans le périmètre — tu
  gardes la main sur la sélection en choisissant quoi déposer, voir
  section 2bis.

Dossier auto-contenu : tout est ici (code, config, PDF en attente, archives)
pour une passation facile — copier ce dossier suffit.

## 1. Installation (une seule fois, déjà faite sur ce PC)

```powershell
cd "C:\Users\BZ6740\OneDrive - ENGIE\Bureau\veille-engie-green"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

`.env` existe déjà avec la clé Mistral configurée. `.env.example` documente
chaque variable si besoin de les revoir.

**Pas d'authentification sur la web app** (accès direct, sans code) — elle
n'est censée être accessible que sur ton réseau local de confiance. N'expose
pas ce PC/port sur Internet sans ajouter une protection.

## 2. Lancement manuel — le workflow au quotidien

Double-clique le raccourci **"Veille ENGIE Green"** sur le Bureau. Une
fenêtre s'ouvre (le serveur tourne dedans) et le navigateur s'ouvre tout
seul sur la page. **Fermer cette fenêtre arrête l'application** — pas besoin
d'autre chose, un seul raccourci pour tout.

*(Alternative sans raccourci : `start_veille.bat` dans le dossier, ou
`.venv\Scripts\python.exe webapp.py` pour voir les logs directement.)*

Dans la page :

1. **Déposer** les PDF des articles GreenUnivers repérés dans la newsletter
   (export depuis ton accès abonné) — plusieurs fichiers en une seule fois.
   Pas besoin de saisir de titre : il est deviné automatiquement depuis le
   contenu du PDF.
2. **Ajouter un lien ou coller du texte** : pour une source qui n'est pas un
   PDF GreenUnivers (article en accès libre, post LinkedIn, communiqué...).
   Rejoint la même file d'attente que les PDF, traité de la même façon (pas
   de filtrage périmètre, seulement la priorité est jugée).
3. Cliquer **"Générer / régénérer la veille"** : récupère automatiquement
   Tecsol + PV Magazine de la semaine, ajoute les PDF/liens/textes déposés,
   appelle Mistral. Un indicateur de chargement s'affiche pendant les 10-30
   secondes que ça prend. Le statut de chaque source (nombre d'articles
   trouvés, ou échec) s'affiche ensuite en évidence — si une source échoue
   ou ne retourne rien, c'est signalé par un badge orange/rouge et un
   encadré d'avertissement, impossible de rater ça.
   - Tecsol/PV Magazine (scrapés) passent par le jugement complet de Mistral
     (in_scope + priorité P1/P2, voir section 6 pour le détail des règles).
   - Les PDF/liens/textes déposés à la main, eux, ne sont PAS filtrés sur le
     périmètre : c'est toi qui as déjà décidé qu'ils comptent en les
     déposant. Mistral juge en revanche réellement leur priorité P1/P2 (pas
     automatiquement P1, ex. les résultats financiers d'un groupe étranger
     sans lien avec la France restent P2).
   - Dans les deux cas, un article de thème CONCURRENCE n'est P1 que s'il a
     un impact France ou touche le périmètre proche d'ENGIE Green (solaire
     au sol, éolien terrestre, stockage, hydro/STEP) — un mouvement de
     concurrence purement étranger reste P2.
4. **Aperçu — modifie puis valide** : chaque actu retenue s'affiche avec une
   case "Garder" (décoche pour l'exclure — cas par cas fréquent : un article
   pas pertinent malgré tout) et un sélecteur de priorité P1/P2 (à changer
   si le jugement de Mistral ne convient pas). Rien n'est perdu tant que tu
   n'as pas cliqué sur un bouton de validation : tu peux réafficher la page,
   redéposer un PDF et régénérer autant de fois que voulu. Deux boutons,
   indépendants l'un de l'autre :
   - **"Copier le texte"** : copie l'aperçu tel qu'édité (actus décochées
     exclues, priorités à jour) dans le presse-papier, sans rien enregistrer
     ni toucher au classeur Excel — pratique pour relire/coller ailleurs
     avant de valider pour de bon.
   - **"Valider (enregistrer + intégrer à l'Excel)"** : reconstruit la
     synthèse à partir de tes modifications, l'enregistre dans
     `archive/veille_<date>.txt`, déplace les PDF/notes utilisés hors de la
     file d'attente (ils ne réapparaîtront plus au prochain lancement), et
     intègre automatiquement le résultat au classeur Excel de suivi. Le
     texte final validé s'affiche ensuite avec son propre bouton "Copier le
     texte" pour le coller directement dans un mail.
   *(Un PDF/lien/texte dont tu as décoché l'actu ci-dessus est quand même
   archivé une fois "Valider" cliqué, pas remis en attente pour la semaine
   suivante — décocher exclut l'actu de la synthèse, ce n'est pas un
   "reporter à plus tard". Supprime-le plutôt à l'étape 1/2 si tu veux le
   retraiter une autre semaine.)*

Dépôt de PDF et ajout de lien sont protégés contre les doublons : un PDF dont
le contenu est déjà en attente (même si le nom de fichier diffère, ex. export
recommencé) est ignoré au dépôt, et un lien déjà dans la file d'attente est
refusé avec un message d'erreur — inutile de vérifier toi-même avant de
déposer/coller.

## 2bis. Onglet "Résumés PDF" — automatiser titre/résumé sans filtrage

Cet onglet est fait pour aller plus vite quand tu as déjà décidé quels PDF
tu veux garder (contrairement à l'onglet "Veille automatique", Mistral n'y
juge jamais l'in_scope/la priorité — tout PDF déposé est automatiquement
résumé et gardé) :

1. **Déposer** un ou plusieurs PDF (même mécanique de dépôt que l'autre
   onglet, mais dans une file d'attente séparée — les deux onglets ne se
   mélangent jamais).
2. **Ajouter un lien ou coller du texte** : pour une source qui n'est pas un
   PDF GreenUnivers (article en accès libre, post LinkedIn, communiqué...).
   Remplis soit un lien (scrapé automatiquement, voir `web_scrape.py`), soit
   un texte collé à la main si le lien ne s'y prête pas (page anti-bot,
   contenu déjà copié). Rejoint la même file d'attente que les PDF.
3. Cliquer **"Générer / régénérer les résumés"** : Mistral rédige, pour
   chaque PDF/lien/texte, un titre reformulé + un résumé factuel de 2 lignes
   + un thème, exactement dans la nomenclature "[THEME] Titre" / résumé /
   source de la veille hebdo (voir `pdf_solo.py`, `summarize_solo` dans
   `summarize_mistral.py`).
4. Deux façons d'exporter, indépendantes l'une de l'autre et réutilisables
   autant de fois que voulu avant de valider :
   - **"Copier le texte"** : même format "[THEME] Titre" / résumé / source
     que la veille hebdo — à coller directement dans un mail.
   - **"Télécharger le PDF (résumés + sources)"** : un seul fichier PDF
     téléchargé, avec la page de résumés en premier (même contenu que le
     texte, mise en page via reportlab) suivie de tous les PDF sources
     déposés, compilés à la suite dans le même ordre (fusion via pypdf, voir
     `pdf_solo.build_combined_pdf`). Une note .txt/.md déposée à la main n'a
     pas de PDF à compiler : elle apparaît sur la page de résumés mais n'a
     pas de page source associée.
5. Cliquer **"Valider"** archive les PDF traités dans
   `archive/pdf_solo/<date>/` (séparé de `archive/greenunivers/<date>/`, pour
   ne pas mélanger les deux workflows) et vide la file d'attente. Le cache
   des résumés déjà générés vit dans `.cache/pdf_solo.json` (même logique que
   `.cache/articles.json` : régénérer après avoir ajouté un PDF ne repaie pas
   les précédents).

## 3. GreenUnivers — pourquoi pas de scraping, et comment déposer les PDF

GreenUnivers est un contenu par abonnement dont les mentions légales
interdisent explicitement les requêtes automatisées vers le site (login/
scraping). On ne construit donc pas de robot qui se connecte tout seul —
risque réel de résiliation d'abonnement et de contentieux. L'export PDF
manuel (la personne abonnée l'enregistre depuis son propre accès) et son
utilisation en interne pour en tirer un résumé factuel est ce qui a été
retenu ici.

Le script extrait le texte du PDF localement pour générer le résumé factuel
de 2 lignes (même format que les autres sources) — **le PDF lui-même n'est
jamais joint/republié** dans le texte final. Le texte extrait localement
peut être imprécis si le PDF est scanné/mal converti — l'aperçu avant
validation sert aussi à vérifier ça.

Alternative sans PDF : glisser directement un fichier `.txt`/`.md` dans
`inbox_greenunivers/` avec titre/lien/contexte tapés à la main — reconnu
par le même mécanisme.

## 4. Où sont les résultats

- `archive/veille_<jeudi>.txt` : synthèse texte de chaque semaine validée
  (onglet "Veille automatique").
- `archive/greenunivers/<date>/` : PDF/notes GreenUnivers traités par l'onglet
  "Veille automatique", conservés.
- `archive/pdf_solo/<date>/` : PDF traités par l'onglet "Résumés PDF" (séparé
  du dossier ci-dessus pour garder une trace distincte de chaque workflow).
- `.cache/articles.json` : mémoire des articles déjà classés par Mistral pour
  l'onglet "Veille automatique" (inclus ou non, priorité, titre, résumé).
  Permet de régénérer après avoir ajouté/retiré un PDF sans renvoyer tous les
  articles à Mistral : seuls les articles jamais vus sont classés, le reste
  est relu depuis ce fichier (0 token). Peut être supprimé sans risque si
  besoin de tout reclasser (juste plus lent/coûteux le temps de le repeupler).
- `.cache/pdf_solo.json` : même mécanisme de cache, pour l'onglet "Résumés PDF".

## 5. (Optionnel) Planifier une exécution automatique non supervisée

Le mode manuel (raccourci + validation à la main) est actif par défaut —
rien n'est planifié. La CLI (`python main.py`) reste disponible pour une
automatisation future via le Planificateur de tâches Windows, mais dans ce
mode personne ne clique "Valider" : la synthèse est directement enregistrée/
archivée sans passer par l'étape d'édition de la web app, donc à réserver à
un usage où le tri manuel n'est pas nécessaire.

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\BZ6740\OneDrive - ENGIE\Bureau\veille-engie-green\run_veille.bat"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At 8:00am
Register-ScheduledTask -TaskName "Veille ENGIE Green" -Action $action -Trigger $trigger -Description "Veille hebdo renouvelables - genere et archive chaque jeudi"
```

Dans ce mode automatique, les PDF GreenUnivers doivent être déposés dans
`inbox_greenunivers/` (via la web app ou manuellement) *avant* l'heure
planifiée. Logs dans `logs/run_<date>.log`.

## 6. Ajuster le tri / la priorisation

Toute la logique de périmètre, d'exclusion et de priorisation P1/P2 est dans
le prompt système de `summarize_mistral.py` (`SYSTEM_PROMPT`). C'est le
point à modifier si le tri dévie de ce qui est attendu.

Une seule règle est appliquée en dur dans `main.py` (`build_draft`), pas dans
le prompt : toute note/PDF GreenUnivers (source "GreenUnivers") est
automatiquement in_scope=true (pas de jugement de périmètre par Mistral pour
ces entrées, la sélection est déjà faite par l'utilisateur au dépôt) — voir
`classify_greenunivers_notes` dans `summarize_mistral.py`. La priorité P1/P2,
elle, reste une vraie décision de Mistral pour ces notes aussi (un PDF
GreenUnivers n'est pas automatiquement P1), avec le même critère CONCURRENCE
+ impact France que pour les sources scrapées (voir `GREENUNIVERS_SYSTEM_PROMPT`).

Si tu modifies le `SYSTEM_PROMPT` (nouvelle exclusion/inclusion), les
articles déjà en cache ne seront PAS reclassés automatiquement — supprime
(ou édite) `.cache/articles.json` si tu veux que le changement s'applique
rétroactivement aux articles déjà vus cette semaine.

## 7. Si une source échoue (403, timeout...)

Ce n'est plus silencieux : la web app affiche un badge et un avertissement
explicite si Tecsol ou PV Magazine échouent ou reviennent vides (voir
section 2). Historique connu : PV Magazine bloquait systématiquement à
cause d'un User-Agent contenant un domaine placeholder ("example.com"),
filtré par le proxy réseau de l'entreprise — corrigé dans
`sources/wp_source.py` (`USER_AGENT`). Si un nouveau blocage apparaît,
regarder d'abord le User-Agent/en-têtes avant de soupçonner le site cible.

## 8. Intégration au classeur Excel de suivi

Depuis l'onglet "Veille automatique", cliquer **"Valider (enregistrer +
intégrer à l'Excel)"** (section 2, étape 4) intègre automatiquement la
synthèse au classeur `Veille_marché_ENR.xlsx` (onglet "Suivi veille", à la
racine du dossier `Veille hebdo/`, un cran au-dessus de
`veille-engie-green/`) — aucune étape manuelle supplémentaire :

- Chaque actu ("[THEME] Titre" / résumé / "Source : ...") est détectée
  indépendamment des autres — tu peux avoir ajouté/retiré des actus ou changé
  le texte, tant que cette structure par bloc est conservée pour chaque actu
  gardée.
- Un appel Mistral (voir `summarize_mistral.classify_for_tracker`) détermine,
  pour chaque actu, la bonne colonne thème du classeur (ÉOLIEN, SOLAIRE,
  BATTERIES/STOCKAGE...) et l'acteur concerné (colonne "THEMES" : nom de
  société si l'actu en cible une, sinon "DIVERS/ <sujet>").
- Les liens sources sont repris tels quels dans les colonnes LIENS. Limite
  connue : les actus issues d'un PDF GreenUnivers n'ont pas de lien public
  (juste "(GreenUnivers -voir pdf)" dans le texte) — la colonne LIENS affiche
  "intégrer lien pdf" comme pense-bête pour ces lignes, à remplacer à la main
  si besoin (ex. lien SharePoint vers le PDF une fois déposé, comme pour les
  anciennes lignes du classeur).
- Les nouvelles lignes reprennent la mise en forme (police, surlignage,
  alignement, bordures, format de cellule) de la dernière ligne existante du
  classeur, pour rester visuellement cohérentes avec le reste du suivi.
- Une copie de sauvegarde du classeur (`Veille_marché_ENR.backup-<horodatage>.xlsx`)
  est créée avant chaque ajout, à côté du fichier original.

Voir `tracker_excel.py` pour le détail du parsing/classement/écriture.
