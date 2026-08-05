# StratIA — Veille hebdo ENGIE Green — Solaire au sol (>1 MW) / Éolien / BESS / Hydro-STEP

Outil autonome (indépendant de Claude Code) pour générer la synthèse
hebdomadaire. Sources publiques (Tecsol Quotidien, PV Magazine) scrapées
automatiquement ; GreenUnivers via PDF déposés manuellement (voir section 3,
raison légale). Utilise l'API Mistral pour la synthèse.

La web app est une page unique (voir section 2). Un bouton **"Activer/
désactiver le scraping automatique"** en haut de page contrôle le mode :
- **Activé** (par défaut) : Tecsol + PV Magazine sont scrapés et jugés par
  Mistral (in_scope + priorité), en plus des PDF/liens déposés.
- **Désactivé** : aucun scraping, seuls les PDF/liens déposés sont traités,
  tous inclus sans aucun jugement de périmètre ni de priorité (priorité par
  défaut "P2", modifiable ensuite dans l'aperçu) — pratique une semaine où
  on ne veut traiter que du GreenUnivers sans bruit de scraping.

Dossier auto-contenu : tout est ici (code, config, PDF en attente, archives)
pour une passation facile — copier ce dossier suffit.

## 1. Installation (une seule fois, déjà faite sur ce PC)

```powershell
cd "C:\Users\BZ6740\OneDrive - ENGIE\Bureau\Veille hebdo\stratia"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

`.env` existe déjà avec la clé Mistral configurée. `.env.example` documente
chaque variable si besoin de les revoir.

**Pas d'authentification sur la web app** (accès direct, sans code) — elle
n'est censée être accessible que sur ton réseau local de confiance. N'expose
pas ce PC/port sur Internet sans ajouter une protection.

## 2. Lancement manuel — le workflow au quotidien

Double-clique le raccourci **"StratIA"** sur le Bureau. Une
fenêtre s'ouvre (le serveur tourne dedans) et le navigateur s'ouvre tout
seul sur la page. **Fermer cette fenêtre arrête l'application** — pas besoin
d'autre chose, un seul raccourci pour tout.

*(Alternative sans raccourci : `start_veille.bat` dans le dossier, ou
`.venv\Scripts\python.exe webapp.py` pour voir les logs directement.)*

Dans la page :

0. **Scraping automatique** (bouton en haut de page) : bascule entre les deux
   modes décrits en introduction. Le réglage est mémorisé (survit à un
   redémarrage de l'app).
1. **Déposer PDF P1/P2** (des PDF GreenUnivers) — glisser-déposer directement sur la
   zone, ou cliquer pour parcourir ; plusieurs fichiers en une seule fois.
   Pas besoin de saisir de titre : il est deviné automatiquement depuis le
   contenu du PDF. Un dépôt dont le contenu est déjà en attente (même si le
   nom de fichier diffère, ex. export recommencé) est ignoré automatiquement
   — inutile de vérifier toi-même avant de déposer.
2. **Déposer PDF P1 uniquement** (PDF de communication ENGIE, encart séparé, même mécanique
   de dépôt) : pour les communiqués/notes que le service Communication
   envoie directement (pas du GreenUnivers, pas de jugement de périmètre).
   Contrairement aux PDF GreenUnivers, ces documents sont **toujours
   priorité P1** (jamais jugée), et leur thème est choisi par Mistral parmi
   une liste fermée dédiée à 3 valeurs : `ENGIE R&B`, `ENGIE`, `ACTU GENERAL
   ENERGIE` (voir section 6) — modifiable ensuite dans l'aperçu comme
   n'importe quel thème si besoin. File d'attente et archive (`archive/comm/`)
   séparées de celles de GreenUnivers.
3. **Ajouter un lien ou coller du texte** : pour une source qui n'est pas un
   PDF (article en accès libre, post LinkedIn, communiqué...). Rejoint la
   même file d'attente que les PDF GreenUnivers (pas celle de communication
   ENGIE). Un lien déjà en attente est refusé avec un message d'erreur.
4. Cliquer **"Générer / régénérer la veille"** : une barre de progression
   réelle (pas juste "10-30 secondes") suit chaque étape — récupération des
   sources, appels Mistral, dédoublonnage. Le statut de chaque source
   scrapée (nombre d'articles trouvés, ou échec) s'affiche ensuite en
   évidence.
   - **Scraping activé** : Tecsol/PV Magazine passent par le jugement complet
     de Mistral (in_scope + priorité P1/P2, voir section 6). Les PDF/liens
     déposés, eux, ne sont PAS filtrés sur le périmètre (sélection déjà faite
     en les déposant) mais leur priorité P1/P2 est réellement jugée (pas
     automatiquement P1 — ex. les résultats financiers d'un groupe étranger
     sans lien avec la France restent P2). Un article de thème CONCURRENCE
     n'est P1 que s'il a un impact France ou touche le périmètre proche
     d'ENGIE Green (solaire au sol, éolien terrestre, stockage, hydro/STEP).
   - **Scraping désactivé** : aucun appel à Tecsol/PV Magazine ; les PDF/liens
     déposés sont résumés sans aucun jugement (ni périmètre, ni priorité) —
     tout est inclus, priorité par défaut "P2" modifiable dans l'aperçu.
5. **Aperçu — modifie puis valide** : chaque actu retenue s'affiche avec :
   - une case **"Garder"** (décoche pour l'exclure) ;
   - un sélecteur de **priorité P1/P2** ;
   - un sélecteur de **thème**, modifiable au même titre que la priorité,
     parmi la liste fermée (voir section 6) — utile quand Mistral choisit un
     thème un peu à côté ;
   - le **titre et le résumé directement éditables** (Mistral rédige mal
     parfois — pas besoin de retoucher après coup dans le mail) ;
   - une **poignée ⠿** pour réordonner par glisser-déposer (une ligne verte
     indique où l'actu atterrira, et un flash confirme sa nouvelle place).

   Une barre d'outils au-dessus affiche un **compteur "X P1 · Y P2
   conservé(s)"** mis à jour en direct, un **filtre par thème** et un
   **filtre par priorité** (P1 uniquement / P2 uniquement) — purement
   visuels pour "Valider" (n'affectent pas ce qui sera intégré à l'Excel),
   mais pris en compte par "Télécharger le PDF" ci-dessous : si tu filtres
   sur "P1 uniquement" puis télécharges, le PDF ne contient que les P1
   affichés à l'écran.

   Rien n'est perdu tant que tu n'as pas cliqué sur un bouton de validation
   (l'aperçu est même sauvegardé sur disque : un redémarrage de l'app ne le
   fait pas perdre). Trois actions, indépendantes les unes des autres :
   - **"Valider (enregistrer + intégrer à l'Excel)"** : reconstruit la
     synthèse à partir de tes modifications (y compris l'ordre), l'enregistre
     dans `archive/veille_<date>.txt`, déplace les PDF/notes utilisés hors de
     la file d'attente, et intègre automatiquement le résultat au classeur
     Excel de suivi. Le texte final s'affiche ensuite avec son propre bouton
     "Copier le texte" pour le coller directement dans un mail.
   - **"Copier le texte"** : copie l'aperçu tel qu'édité dans le presse-papier,
     sans rien enregistrer ni toucher au classeur Excel.
   - **"Télécharger le PDF (résumés + sources)"** : un seul fichier PDF mis en
     page en bleu ENGIE (voir `combined_pdf.py`), avec :
     - la synthèse en premier (1-2 pages selon le volume), actus triées P1
       puis P2 (sans étiquette/encadré visuel — l'export ne sert en pratique
       presque qu'aux P1), avec le thème de chaque actu ;
     - à la suite, les PDF sources déposés, regroupés par thème derrière une
       page de garde dédiée (thème en grand, dans l'ordre où il apparaît dans
       la synthèse) ;
     - chaque **titre est cliquable** dans la synthèse : vers la page du PDF
       source correspondant s'il y en a un embarqué plus loin dans le
       document, sinon vers le lien de l'article pour une source ouverte
       (Tecsol, PV Magazine...). Un article sans PDF ni lien (ex. note
       GreenUnivers à accès abonné) reste en texte simple, non cliquable.
     Reprend tes éditions en cours (thème/titre/résumé/priorité, actus
     décochées, ordre) et respecte les filtres thème/priorité actifs dans la
     barre d'outils au moment du clic — voir le point précédent. Les articles
     scrapés ou notes texte sans PDF n'ont simplement pas de page source
     derrière leur titre. Chaque page (synthèse et pages de garde) se termine
     par un pied de page "Réalisé avec StratIA — Service Marketing" (petit
     logo + mention, voir `_draw_credit_footer`).

     Le logo ENGIE affiché dans l'en-tête, le pied de page et les pages de
     garde (`assets/engie_logo.png`, fond damier gris/blanc retiré) est encodé en base64
     directement dans `combined_pdf.py` (`_ENGIE_LOGO_B64`, même mécanisme
     que le logo StratIA de la webapp, `webapp._LOGO_B64`) — si cette
     constante est vidée, un monogramme "E" de repli s'affiche à la place.
     Pour remplacer le logo : dépose le nouveau fichier dans `assets/`,
     encode-le en base64 (`base64.b64encode(Path(...).read_bytes()).decode()`)
     et remplace la valeur de `_ENGIE_LOGO_B64` — aucun autre changement de
     code nécessaire (`_draw_logo` déduit la largeur du ratio réel de
     l'image).

     Chaque page de garde affiche aussi un pictogramme du thème
     (`_draw_theme_icon`) : pour EOLIEN/SOLAIRE/AGRIVOLTAÏSME/BATTERIES-
     STOCKAGE/HYDROELECTRIQUE, ce sont les pictos fournis (`assets/picto_*.png`,
     encodés dans `_THEME_PICTO_B64`) ; pour les autres thèmes (HYBRIDE,
     PARTAGE DE LA VALEUR, REPOWERING, CONCURRENCE, ENGIE, ENGIE R&B, ACTU
     GENERAL ENERGIE), ce sont des pictogrammes dessinés en primitives
     reportlab (`_THEME_ICON_DRAWERS`), en attendant d'éventuels pictos
     officiels pour ceux-là aussi — même procédure d'ajout que pour le logo
     (fichier dans `assets/`, encodage base64, entrée dans `_THEME_PICTO_B64`
     avec le libellé de thème exact comme clé).
   *(Un PDF/lien/texte dont tu as décoché l'actu ci-dessus est quand même
   archivé une fois "Valider" cliqué, pas remis en attente pour la semaine
   suivante — décocher exclut l'actu de la synthèse, ce n'est pas un
   "reporter à plus tard". Supprime-le plutôt à l'étape 1/2 si tu veux le
   retraiter une autre semaine.)*

Un bouton clair/sombre en haut à droite force un thème (mémorisé), sinon la
page suit le thème du système.

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

- `archive/veille_<jeudi>.txt` : synthèse texte de chaque semaine validée.
- `archive/greenunivers/<date>/` : PDF/notes traités, conservés (scraping
  activé ou non).
- `.cache/articles.json` : mémoire des articles/PDF déjà classés par Mistral
  (inclus ou non, priorité, titre, résumé). Permet de régénérer après avoir
  ajouté/retiré un PDF sans renvoyer tous les articles à Mistral : seuls les
  articles jamais vus sont classés, le reste est relu depuis ce fichier
  (0 token). Peut être supprimé sans risque si besoin de tout reclasser
  (juste plus lent/coûteux le temps de le repeupler).
- `.cache/pending_draft.pkl` : aperçu en cours (avant validation), pour
  survivre à un redémarrage de l'app. Supprimé automatiquement une fois
  "Valider" cliqué.
- `.cache/scraping_enabled.txt` : dernier état du bouton "scraping
  automatique".

## 5. (Optionnel) Planifier une exécution automatique non supervisée

Le mode manuel (raccourci + validation à la main) est actif par défaut —
rien n'est planifié. La CLI (`python main.py`) reste disponible pour une
automatisation future via le Planificateur de tâches Windows, mais dans ce
mode personne ne clique "Valider" : la synthèse est directement enregistrée/
archivée sans passer par l'étape d'édition de la web app, donc à réserver à
un usage où le tri manuel n'est pas nécessaire.

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\BZ6740\OneDrive - ENGIE\Bureau\Veille hebdo\stratia\run_veille.bat"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At 8:00am
Register-ScheduledTask -TaskName "StratIA" -Action $action -Trigger $trigger -Description "Veille hebdo renouvelables - genere et archive chaque jeudi"
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

Le thème affiché à côté de chaque actu (`[THEME] Titre`) est désormais une
**liste fermée** de 12 valeurs (`VEILLE_THEME_OPTIONS` dans
`summarize_mistral.py`) — plus de tag libre : `EOLIEN`, `AGRIVOLTAÏSME`,
`SOLAIRE`, `BATTERIES / STOCKAGE`, `HYBRIDE`, `HYDROELECTRIQUE`, `PARTAGE DE
LA VALEUR`, `REPOWERING`, `CONCURRENCE`, `ENGIE R&B`, `ENGIE`, `ACTU GENERAL
ENERGIE`. Une actu de marché/réglementation transverse est rattachée à la
techno la plus concernée plutôt qu'à un thème générique (voir `THEME_BLOCK`) ;
`CONCURRENCE` reste réservé aux mouvements d'acteurs concurrents (levée de
fonds, cession...) sans techno dominante, `ENGIE R&B` aux actus sur la
filiale renewables du groupe elle-même (anciennement "ENGIE Green"), `ENGIE`
aux actus groupe au sens large, et `ACTU GENERALE ENERGIE` au contexte
sectoriel qui ne cible ni acteur ni techno précise. Un filet de sécurité
Python (`_valid_veille_theme`) force vers `CONCURRENCE` toute valeur hors
liste que Mistral renverrait malgré la consigne. Le thème est aussi
**éditable manuellement** dans l'aperçu (sélecteur à côté de la priorité,
voir section 2) si le choix de Mistral ne convient pas.

Les PDF déposés dans l'encart "Communication ENGIE" (section 2) passent par
une classification à part (`classify_comm_notes`/`COMM_SYSTEM_PROMPT` dans
`summarize_mistral.py`) : Mistral choisit UNIQUEMENT parmi `ENGIE R&B`,
`ENGIE`, `ACTU GENERALE ENERGIE` (jamais les 9 autres valeurs techniques), et
ne juge ni le périmètre ni la priorité — toujours "P1", fixé dans le code
(`main.build_draft`), pas par Mistral. Filet de sécurité dédié
(`_valid_comm_theme`) : un thème hors de ces 3 valeurs retombe sur `ACTU
GENERAL ENERGIE`. Les PDF GreenUnivers, eux, continuent d'utiliser la liste
complète de 12 valeurs comme avant (en pratique surtout les 8 techniques +
`CONCURRENCE`).

Les 3 thèmes `ENGIE R&B`/`ENGIE`/`ACTU GENERALE ENERGIE` sont propres à la
veille (pas de colonne dédiée dans le classeur Excel) : le classement Excel
continue à utiliser les 8 thèmes techniques + `DIVERS` (`TRACKER_THEME_OPTIONS`,
inchangée) — voir section 8.

## 7. Si une source échoue (403, timeout...)

Ce n'est plus silencieux : la web app affiche un badge et un avertissement
explicite si Tecsol ou PV Magazine échouent ou reviennent vides (voir
section 2). Historique connu : PV Magazine bloquait systématiquement à
cause d'un User-Agent contenant un domaine placeholder ("example.com"),
filtré par le proxy réseau de l'entreprise — corrigé dans
`sources/wp_source.py` (`USER_AGENT`). Si un nouveau blocage apparaît,
regarder d'abord le User-Agent/en-têtes avant de soupçonner le site cible.

## 8. Intégration au classeur Excel de suivi

Cliquer **"Valider (enregistrer + intégrer à l'Excel)"** (section 2, étape 4)
intègre automatiquement la synthèse au classeur `Veille_marché_ENR.xlsx`
(onglet "Suivi veille", à la racine du dossier `Veille hebdo/`, un cran
au-dessus de `stratia/`) — aucune étape manuelle supplémentaire :

- Les entrées structurées de l'aperçu (celles que tu as éditées/réordonnées/
  décochées dans la webapp) sont utilisées directement, sans passer par le
  texte formaté — pas de dépendance à une mise en forme particulière.
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
- **Tableau croisé acteur x thème** : si l'acteur d'une actu a déjà une ligne
  dans le classeur (comparaison insensible à la casse) et que la case du
  thème ciblé y est encore vide, l'actu est ajoutée dans cette case plutôt
  que de créer une nouvelle ligne pour le même acteur (ex. "Nadara" a déjà
  une ligne pour EOLIEN → une nouvelle actu Nadara sur BATTERIES / STOCKAGE
  remplit la case BATTERIES / STOCKAGE de cette même ligne, et sa date est
  mise à jour). Si la case ciblée est déjà occupée par une actu précédente,
  une nouvelle ligne est créée comme avant (pas de fusion/empilement dans une
  case déjà remplie pour l'instant). Ne s'applique qu'aux futures
  validations : les lignes déjà dupliquées dans l'historique existant (ex.
  EDF sur plusieurs dizaines de lignes) ne sont pas fusionnées
  rétroactivement — voir `tracker_excel._find_existing_actor_row`.
- Une copie de sauvegarde du classeur (`Veille_marché_ENR.backup-<horodatage>.xlsx`)
  est créée avant chaque ajout, à côté du fichier original.
- Si l'intégration échoue (classeur ouvert dans Excel au moment de valider),
  la synthèse est quand même enregistrée/archivée normalement, et un bouton
  **"Réessayer l'intégration Excel"** apparaît à côté du texte final — ferme
  le classeur puis clique dessus pour rejouer l'intégration sans rien
  regénérer.

Voir `tracker_excel.py` pour le détail du classement/écriture.

## 9. Partager l'app à des collègues (packaging en .exe)

Chaque collègue peut avoir sa propre copie de l'app, sans installer Python :
un `.exe` autonome (voir `veille.spec`, généré par PyInstaller) embarque tout
(code + interpréteur Python + dépendances). La clé API Mistral reste externe,
dans un fichier `.env` à côté de l'exe — jamais codée en dur (voir
`config.py`, qui gère aussi le cas où l'exe est lancé depuis un dossier
différent de celui où il a été construit).

**Générer le paquet à livrer** (exe + `.env` + notice, zippés) :

```
package_release.bat
```

Ça reconstruit l'exe (`build_exe.bat`) puis assemble
`dist_package/StratIA.zip`, prêt à envoyer. Le zip contient le vrai
`.env` du poste de build (clé API en clair) — ne le diffuse qu'en interne, et
uniquement aux personnes qui doivent l'utiliser.

**Pour reconstruire juste l'exe** (sans repackager en zip), par exemple pour
tester après une modification de code : `build_exe.bat` seul, résultat dans
`dist\StratIA.exe`.

**Mode d'emploi côté collègue** : voir `LISEZMOI.txt` (inclus dans le zip) —
double-clic sur l'exe pour lancer (le navigateur s'ouvre automatiquement),
fermer la fenêtre noire pour arrêter. Chaque installation est indépendante :
son propre `inbox_greenunivers/`, `archive/`, `.cache/`, créés à côté de
l'exe au premier lancement — ce que dépose/génère un collègue n'apparaît pas
chez les autres.

**Limite connue** : cette app n'est pas conçue pour un usage concurrent
multi-utilisateurs sur un même process (pas de session, état en mémoire
partagé — voir `webapp.py`). Le modèle "chacun sa copie locale" évite ce
problème ; ne pas transformer ça en un unique serveur central partagé sans
revoir cette architecture.
