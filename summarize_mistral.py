"""Classification + résumé par article via l'API Mistral.

Un seul appel Mistral classe un LOT d'articles NOUVEAUX (jamais vus, voir
cache.py) : inclus ou non dans le périmètre, priorité 1/2, titre reformulé,
résumé factuel de 2 lignes. Chaque article est jugé sur son seul contenu
(pas de comparaison inter-articles nécessaire pour ces critères), ce qui
permet de classer uniquement les nouveaux arrivants à chaque régénération
sans perdre en cohérence — l'assemblage du document final (mise en forme,
regroupement par priorité) est fait en Python, voir main.py.
"""
import html
import json
import re

import requests

from config import MISTRAL_API_KEY, MISTRAL_MODEL

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# Blocs communs entre SYSTEM_PROMPT (articles scrapés Tecsol/PV Magazine,
# in_scope + priorité jugés) et GREENUNIVERS_SYSTEM_PROMPT (PDF GreenUnivers,
# déjà sélectionnés par l'utilisateur donc in_scope pas jugé, mais la
# priorité P1/P2 doit rester une vraie décision — pas un P1 systématique,
# voir ex. un article Iberdrola correctement jugé P2 car hors périmètre
# France/pas un mouvement de concurrent).
HIERARCHIE_BLOCK = """HIÉRARCHISATION (pour les articles in_scope=true) — pense en termes de \
lectorat, pas seulement d'ampleur de l'info :
- RÈGLE PRIORITAIRE : un article de thème CONCURRENCE (mouvement d'un acteur \
concurrent — projet, levée de fonds, réorganisation, nomination/départ, \
cession, fusion/acquisition, nouvel entrant...) est "P1" UNIQUEMENT s'il a un \
impact sur le marché français ou touche le périmètre proche d'ENGIE Green \
(solaire au sol, éolien terrestre, stockage BESS, hydro/STEP). Un mouvement \
de concurrence purement étranger et sans lien avec la France/le périmètre \
(ex. résultats financiers périodiques d'un groupe étranger, acquisition d'un \
actif hors périmètre à l'étranger) reste "P2" même si l'acteur est un \
concurrent notoire — le simple fait d'être thème CONCURRENCE ne suffit pas, \
regarde le contenu réel de l'info. Applique cette règle avant les critères \
généraux ci-dessous.
- "P1" : niveau Comité de Direction — actualités stratégiques majeures \
(nouveaux acteurs, appels d'offres, réformes réglementaires structurantes, \
mouvements capitalistiques importants, levées de fonds significatives, \
fusions/acquisitions) qui méritent l'attention de dirigeants.
- "P2" : niveau équipes métiers/opérationnelles — actualités utiles au \
quotidien mais plus secondaires ou locales (contentieux, faits divers \
sectoriels, annonces mineures, produits, détails techniques ou \
réglementaires qui intéressent les équipes terrain plus que la direction)."""

THEME_BLOCK = """THÈME (un tag court affiché à côté de chaque article, \
indépendant de la priorité P1/P2 ci-dessus) : un ou deux mots en MAJUSCULES \
qui résument le sujet de l'article, comme le ferait un humain qui trie ses \
actus au fil de l'eau — pas de liste figée, pas de règle stricte, utilise \
ton jugement. Exemples déjà vus pour donner le ton (à titre indicatif, libre \
d'en utiliser d'autres) : FRANCE, EUROPE, CONCURRENCE, MARCHÉ, RTE, SOLAIRE, \
HYDROÉLECTRICITÉ, DÉCARBONATION INDUSTRIELLE, IA."""

STYLE_BLOCK = """STYLE :
- title : une REFORMULATION synthétique et percutante à toi, jamais un \
copier-coller du titre original de l'article source.
- summary : 2 lignes MAXIMUM, factuel, ton neutre et professionnel, aucun \
commentaire personnel ni appréciation, en priorisant chiffres et acteurs. \
Texte brut uniquement (pas de Markdown : pas de **, pas de liens).
- INTERDICTION FORMELLE D'INVENTER : n'ajoute aucun chiffre, acteur, citation \
ou détail qui n'est pas explicitement présent dans le texte fourni pour cet \
article, même si tu "sais" par ailleurs des informations plausibles sur le \
sujet. Si le texte fourni est trop court/vague pour un résumé fiable de 2 \
lignes, reformule uniquement ce qui est explicitement écrit."""

SYSTEM_PROMPT = """Tu es un analyste expert en intelligence économique et \
stratégique travaillant spécifiquement pour ENGIE Green, filiale d'ENGIE dont \
le cœur de métier est le développement, la construction et l'exploitation de \
projets d'énergie renouvelable de grande taille. Tu classes des articles pour \
la veille hebdomadaire du marché à destination du Board et des équipes \
opérationnelles et Marketing-Communication.

PÉRIMÈTRE MÉTIER (in_scope=true UNIQUEMENT pour ces sujets) :
- Solaire photovoltaïque : uniquement les parcs au sol de grande puissance \
(typiquement supérieure à 1 MW), y compris l'AgriPV/agrivoltaïsme quand il s'agit \
de grands projets de puissance comparable (même seuil que le solaire classique).
- Éolien terrestre.
- Stockage d'énergie stationnaire par batteries (BESS), souvent connecté à des \
actifs de production.
- Hydro / STEP (hydroélectricité, pompage-turbinage).
- Cadre réglementaire, politique publique et marché DE GROS de l'électricité \
en France pour ce périmètre, même sans projet précis derrière : mécanismes \
de soutien (PPE, SNBC, CEE, appels d'offres), règles du marché de gros/prix \
négatifs/mécanisme de capacité, raccordement réseau, positions ou décisions \
des autorités (CRE, DGEC, Ademe) et des syndicats professionnels (SER, \
France Renouvelables, Enerplan...), tendances des prix DE GROS/de marché \
(pas les tarifs grand public), projets de loi ou propositions politiques \
affectant le secteur (ex. moratoire, fiscalité). Un article \
institutionnel/gouvernance sur un acteur de ce périmètre (ex. réorganisation \
de l'Ademe) compte aussi.

À EXCLURE IMPÉRATIVEMENT (in_scope=false) même si l'article mentionne un mot-clé \
du périmètre en passant :
- Solaire de petite taille (< 1 MW), y compris l'agrivoltaïsme de petite taille.
- Solaire en toiture ou sur bâtiment, quelle que soit la taille du bâtiment \
(résidentiel, tertiaire, industriel, agricole).
- Autoconsommation, individuelle ou collective, quel que soit le porteur \
(particulier, entreprise, collectivité) : hors périmètre même si le volume \
en MW/MWc est mentionné.
- Ombrières de parking (y compris ombrières agricoles/agrivoltaïques de petite \
envergure — seuls les grands projets agrivoltaïques comptent, pas les ombrières).
- Articles de type "point/récap hebdomadaire du marché" (bilan de la semaine, \
synthèse périodique de prix ou d'actualités déjà couvertes) qui ne portent pas \
une actualité précise et nouvelle mais un simple recueil récapitulatif : \
EXCLURE, même si des chiffres ou acteurs du périmètre y figurent.
- Autres énergies (hydrogène, biogaz, etc.).
- Fourniture/tarifs d'électricité aux particuliers ou aux entreprises (ex. \
"hausse de 2,5% des tarifs pour les foyers", offres d'un fournisseur \
d'électricité) : ENGIE Green ne fournit pas d'électricité aux \
consommateurs, c'est un développeur/producteur d'actifs de grande taille — \
hors périmètre, même si le sujet est "l'électricité" au sens large.
- Fabricants et équipementiers (panneaux/cellules solaires, turbines, \
onduleurs, cellules de batteries, etc.), y compris leurs classements/labels \
(ex. "Tier 1 Cleantech Company", palmarès sectoriels) : ce sont des \
fournisseurs dans la chaîne de valeur, pas des concurrents d'ENGIE Green — \
un concurrent est un développeur/producteur indépendant d'électricité (IPP) \
sur le même segment (grand solaire/éolien/stockage/hydro), pas un vendeur de \
matériel.
- Data centers et infrastructures physiques liées à l'IA (serveurs, \
refroidissement, raccordement électrique d'un site de calcul, etc.), même si \
l'article parle de leur consommation électrique, de leurs besoins en \
stockage/batteries ou l'exprime en MW/GW : ce sont des CONSOMMATEURS \
d'électricité, pas des acteurs de la production/développement d'actifs EnR — \
hors périmètre. Exceptions qui restent in_scope (voir aussi la règle \
CONCURRENCE ci-dessous) : (a) un projet EnR concret (parc solaire/éolien ou \
BESS de grande puissance développé pour alimenter un data center via PPA), \
jugé sur ce projet, pas sur le data center ; (b) un article dont le sujet \
réel est une SOCIÉTÉ ou des ACTEURS du secteur EnR (ex. d'anciens dirigeants \
d'un développeur EnR qui lancent une nouvelle société), même si cette \
société cible les data centers — c'est le mouvement de l'acteur EnR qui \
compte, pas la techno visée.
- Plus généralement, tout sujet qui parle d'électricité/d'énergie sans porter \
sur un actif de PRODUCTION renouvelable du périmètre ci-dessus (ex. réseaux de \
recharge VE, consommation industrielle, data centers, gestion de la demande) \
est hors périmètre, même si les volumes (MW/GW) ou le vocabulaire (stockage, \
batterie) rappellent le secteur.
- Nominations / départs / mobilité de personnes chez un acteur du secteur \
(concurrent producteur/développeur, institution, syndicat professionnel) : \
INCLURE (thème CONCURRENCE), que la personne rejoigne/quitte une structure \
EXISTANTE ou en crée une nouvelle — ce sont des mouvements de marché à \
suivre. N'EXCLURE que si le mouvement de personne n'a aucun lien avec le \
secteur EnR (ex. un cadre qui change de secteur sans rapport avec les \
renouvelables).
- Tout article hors périmètre même s'il n'y a "rien d'autre à mettre" : ne force \
jamais un article hors périmètre à être in_scope=true.

PÉRIMÈTRE GÉOGRAPHIQUE :
- Priorité 1 : France — c'est le marché principal, toute information pertinente \
sur le marché français dans le périmètre métier ci-dessus est capitale.
- Priorité 2 (Europe, veille ciblée uniquement, SÉLECTIF PAR DÉFAUT) : une info \
européenne n'est in_scope=true QUE si elle concerne (a) une tendance \
technologique majeure, surtout pour le stockage, (b) un mouvement stratégique \
paneuropéen d'un grand concurrent (envergure groupe, pas une filiale locale), \
ou (c) une décision politique de l'UE à impact direct sur le marché français. \
Exclure (in_scope=false) le développement d'un projet local isolé par un \
concurrent dans un autre pays européen (ex. "un acteur s'implante en \
Roumanie"), même si le mouvement est notable pour ce pays. En cas de doute sur \
une info hors France, le biais par défaut est l'EXCLUSION : ne classe \
in_scope=true une info européenne que si elle remplit clairement un des trois \
critères (a)/(b)/(c) ci-dessus, pas parce qu'elle est "intéressante" en soi. \
Une info hors France in_scope=true est TOUJOURS priority="P2", jamais "P1" \
— même une tendance stockage jugée majeure reste secondaire par rapport à \
une actualité française équivalente, la France seule mérite P1.

""" + HIERARCHIE_BLOCK + """

""" + THEME_BLOCK + """

""" + STYLE_BLOCK + """

Pour chaque article de la liste fournie, décide in_scope (true/false). Si \
in_scope=false, "priority", "title" et "summary" peuvent être omis ou vides. \
Chaque article est indépendant : ne compare pas les articles entre eux, juge \
chacun sur ses seuls mérites selon les critères ci-dessus.

Réponds UNIQUEMENT avec un objet JSON de la forme :
{"articles": [{"key": "<reprends exactement la clé fournie>", "in_scope": true, \
"priority": "P1", "theme": "RTE", "title": "...", "summary": "..."}, ...]}
Un élément par article reçu, dans le même ordre, en reprenant exactement la \
clé ("key") fournie pour chacun."""


GREENUNIVERS_SYSTEM_PROMPT = """Tu es un analyste expert en intelligence \
économique et stratégique travaillant spécifiquement pour ENGIE Green, \
filiale d'ENGIE dont le cœur de métier est le développement, la construction \
et l'exploitation de projets d'énergie renouvelable de grande taille. Tu \
prépares la veille hebdomadaire du marché à destination du Board et des \
équipes opérationnelles et Marketing-Communication.

Les articles fournis ici viennent tous de PDF GreenUnivers déposés \
manuellement par l'utilisateur : il a DÉJÀ décidé qu'ils sont dans le \
périmètre en les déposant — NE JUGE PAS s'ils sont hors sujet, traite \
INCONDITIONNELLEMENT chaque article de la liste. Ton seul travail est de \
décider leur PRIORITÉ (P1/P2), leur thème, et de rédiger titre + résumé.

PRIORITÉ GÉOGRAPHIQUE (à appliquer avant la hiérarchisation générale \
ci-dessous, sauf règle CONCURRENCE qui prime toujours) :
- France : c'est le marché principal, une actualité française pertinente \
pour le périmètre (solaire au sol, éolien terrestre, stockage BESS, hydro/ \
STEP, réglementation/marché de gros France) peut mériter P1 si elle est \
stratégique.
- Hors France (résultats financiers d'un groupe étranger, actualité locale \
dans un autre pays, tendance générale non spécifique à la France) : \
TOUJOURS "P2", jamais "P1" — même une actualité notable pour son marché \
d'origine reste secondaire par rapport à une actualité française \
équivalente. Un article sur les résultats financiers ou la stratégie \
générale d'un groupe étranger (ex. Iberdrola, RWE à l'étranger) est P2 par \
défaut, sauf s'il constitue un mouvement de concurrence direct sur le \
marché français (voir thème CONCURRENCE ci-dessous, qui prime).

""" + HIERARCHIE_BLOCK + """

""" + THEME_BLOCK + """

""" + STYLE_BLOCK + """

Chaque article est indépendant : ne compare pas les articles entre eux, \
juge chacun sur ses seuls mérites selon les critères ci-dessus.

Réponds UNIQUEMENT avec un objet JSON de la forme :
{"articles": [{"key": "<reprends exactement la clé fournie>", "priority": \
"P1", "theme": "RTE", "title": "...", "summary": "..."}, ...]}
Un élément par article reçu, dans le même ordre, en reprenant exactement la \
clé ("key") fournie pour chacun."""


def classify_articles(new_articles: list[dict]) -> dict[str, dict]:
    """new_articles: liste de dicts avec au moins key/source/title/url/text.
    Retourne un dict {key: {in_scope, priority, title, summary}}."""
    if not new_articles:
        return {}
    if not MISTRAL_API_KEY:
        raise RuntimeError(
            "MISTRAL_API_KEY manquante : renseigne-la dans le fichier .env "
            "(voir .env.example)."
        )

    payload_articles = [
        {
            "key": a["key"],
            "source": a.get("source"),
            "title": a.get("title"),
            "text": a.get("content") or a.get("excerpt") or "",
        }
        for a in new_articles
    ]

    user_prompt = (
        "Articles à classer (un seul lot de nouveaux articles, jamais vus "
        "précédemment) :\n\n" + json.dumps(payload_articles, ensure_ascii=False, indent=2)
    )

    resp = requests.post(
        MISTRAL_URL,
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MISTRAL_MODEL,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    raw = data["choices"][0]["message"]["content"]
    parsed = json.loads(raw)

    results = {}
    for item in parsed.get("articles", []):
        key = item.get("key")
        if not key:
            continue
        results[key] = {
            "in_scope": bool(item.get("in_scope")),
            "priority": item.get("priority") or "",
            "theme": item.get("theme") or "AUTRE",
            "title": _clean_text(item.get("title") or ""),
            "summary": _clean_text(item.get("summary") or ""),
        }

    # Filet de sécurité : si Mistral omet une clé (ne devrait pas arriver),
    # on la marque hors périmètre plutôt que de la faire disparaître
    # silencieusement de tout futur suivi.
    for a in new_articles:
        results.setdefault(a["key"], {"in_scope": False, "priority": "", "theme": "", "title": "", "summary": ""})

    return results


def classify_greenunivers_notes(notes: list[dict]) -> dict[str, dict]:
    """notes : PDF/notes GreenUnivers (voir manual_notes.fetch), déjà jugés
    in_scope par l'utilisateur en les déposant. Contrairement à
    classify_articles, ne décide PAS in_scope (toujours true, à fixer par
    l'appelant) mais juge réellement la priorité P1/P2 selon les mêmes
    critères que la veille classique (ex. un article sur les résultats d'un
    groupe étranger comme Iberdrola doit pouvoir ressortir en P2, pas un P1
    systématique) — voir GREENUNIVERS_SYSTEM_PROMPT.
    Retourne {key: {priority, theme, title, summary}}."""
    if not notes:
        return {}
    if not MISTRAL_API_KEY:
        raise RuntimeError(
            "MISTRAL_API_KEY manquante : renseigne-la dans le fichier .env "
            "(voir .env.example)."
        )

    payload_articles = [
        {
            "key": n["key"],
            "title": n.get("title"),
            "text": n.get("content") or n.get("excerpt") or "",
        }
        for n in notes
    ]

    resp = requests.post(
        MISTRAL_URL,
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MISTRAL_MODEL,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": GREENUNIVERS_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload_articles, ensure_ascii=False, indent=2)},
            ],
        },
        timeout=180,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(raw)

    results = {}
    for item in parsed.get("articles", []):
        key = item.get("key")
        if not key:
            continue
        results[key] = {
            "priority": item.get("priority") or "P2",
            "theme": item.get("theme") or "AUTRE",
            "title": _clean_text(item.get("title") or ""),
            "summary": _clean_text(item.get("summary") or ""),
        }

    for n in notes:
        results.setdefault(n["key"], {"priority": "P2", "theme": "AUTRE", "title": n.get("title", ""), "summary": ""})

    return results


SOLO_SYSTEM_PROMPT = """Tu rédiges, pour l'onglet "Résumés PDF" de l'outil de \
veille ENGIE Green, un titre et un résumé pour chaque article fourni. \
Contrairement à la veille hebdomadaire classique, NE JUGE PAS si l'article \
est dans le périmètre métier : l'utilisateur a déjà choisi ces articles en \
les déposant, ton seul travail est de les rédiger, pas de les filtrer. \
Traite donc INCONDITIONNELLEMENT chaque article de la liste.

THÈME : un ou deux mots en MAJUSCULES qui résument le sujet de l'article \
(même logique que pour la veille hebdomadaire) : pas de liste figée, utilise \
ton jugement (ex. FRANCE, EUROPE, CONCURRENCE, MARCHÉ, RTE, SOLAIRE, \
HYDROÉLECTRICITÉ, DÉCARBONATION INDUSTRIELLE, IA).

STYLE :
- title : une REFORMULATION synthétique et percutante à toi, jamais un \
copier-coller du titre original de l'article source.
- summary : 2 lignes MAXIMUM, factuel, ton neutre et professionnel, aucun \
commentaire personnel ni appréciation, en priorisant chiffres et acteurs. \
Texte brut uniquement (pas de Markdown : pas de **, pas de liens).
- INTERDICTION FORMELLE D'INVENTER : n'ajoute aucun chiffre, acteur, citation \
ou détail qui n'est pas explicitement présent dans le texte fourni pour cet \
article, même si tu "sais" par ailleurs des informations plausibles sur le \
sujet. Si le texte fourni est trop court/vague pour un résumé fiable de 2 \
lignes, reformule uniquement ce qui est explicitement écrit.

Réponds UNIQUEMENT avec un objet JSON de la forme :
{"articles": [{"key": "<reprends exactement la clé fournie>", "theme": "RTE", \
"title": "...", "summary": "..."}, ...]}
Un élément par article reçu, dans le même ordre, en reprenant exactement la \
clé ("key") fournie pour chacun."""


def summarize_solo(articles: list[dict]) -> dict[str, dict]:
    """articles : liste de dicts avec au moins key/title/content ou excerpt \
(voir manual_notes.fetch). Retourne {key: {theme, title, summary}} SANS \
décision in_scope/priorité : contrairement à classify_articles, tout article \
fourni est traité (l'onglet "Résumés PDF" n'a pas vocation à filtrer, voir
pdf_solo.py)."""
    if not articles:
        return {}
    if not MISTRAL_API_KEY:
        raise RuntimeError(
            "MISTRAL_API_KEY manquante : renseigne-la dans le fichier .env "
            "(voir .env.example)."
        )

    payload_articles = [
        {
            "key": a["key"],
            "title": a.get("title"),
            "text": a.get("content") or a.get("excerpt") or "",
        }
        for a in articles
    ]

    resp = requests.post(
        MISTRAL_URL,
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MISTRAL_MODEL,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SOLO_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload_articles, ensure_ascii=False, indent=2)},
            ],
        },
        timeout=180,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(raw)

    results = {}
    for item in parsed.get("articles", []):
        key = item.get("key")
        if not key:
            continue
        results[key] = {
            "theme": item.get("theme") or "AUTRE",
            "title": _clean_text(item.get("title") or ""),
            "summary": _clean_text(item.get("summary") or ""),
        }

    for a in articles:
        results.setdefault(a["key"], {"theme": "AUTRE", "title": a.get("title", ""), "summary": ""})

    return results


DEDUP_SYSTEM_PROMPT = """Tu identifies, dans la liste d'articles ci-dessous \
(déjà retenus pour la veille hebdomadaire ENGIE Green), ceux qui parlent du \
MÊME événement/actualité — par exemple un article de presse et un post \
LinkedIn qui commentent tous les deux la même annonce. Objectif : ne pas \
publier deux fois la même info dans la synthèse, en fusionnant leur \
affichage (un seul texte, plusieurs sources citées).

Deux articles ne comptent comme doublons que s'ils parlent du même \
événement précis (même annonce, même opération, mêmes chiffres) — pas \
seulement du même sujet général (deux articles distincts sur le marché du \
stockage ne sont PAS des doublons).

Réponds UNIQUEMENT avec un objet JSON de la forme :
{"groups": [[0, 3], [1, 4, 5]]}
où chaque sous-liste regroupe les index (position dans la liste fournie, en \
partant de 0) des articles qui parlent du même événement. N'inclus QUE des \
groupes d'au moins 2 articles (un article sans doublon n'apparaît dans aucun \
groupe, pas besoin de le lister seul). Si aucun doublon, réponds \
{"groups": []}."""


def find_duplicate_groups(entries: list[dict]) -> list[list[int]]:
    """entries : liste ordonnée de dicts avec au moins title/summary (déjà \
classés in_scope). Retourne des groupes d'index qui parlent du même \
événement, pour fusion en une seule entrée de synthèse avec plusieurs \
sources (voir main._merge_duplicates)."""
    if len(entries) < 2 or not MISTRAL_API_KEY:
        return []

    payload = [
        {"index": i, "title": e["title"], "summary": e["summary"]}
        for i, e in enumerate(entries)
    ]

    resp = requests.post(
        MISTRAL_URL,
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MISTRAL_MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": DEDUP_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
            ],
        },
        timeout=180,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(raw)

    n = len(entries)
    groups = []
    for g in parsed.get("groups", []):
        clean = sorted({i for i in g if isinstance(i, int) and 0 <= i < n})
        if len(clean) >= 2:
            groups.append(clean)
    return groups


TRACKER_THEME_OPTIONS = [
    "EOLIEN", "AGRIVOLTAÏSME", "SOLAIRE", "BATTERIES / STOCKAGE", "HYBRIDE",
    "HYDROELECTRIQUE", "PARTAGE DE LA VALEUR", "REPOWERING", "DIVERS",
]

TRACKER_SYSTEM_PROMPT = """Tu ranges des actualités déjà rédigées (titre + \
résumé) dans un classeur Excel de suivi manuel tenu par ENGIE Green, pour \
chaque actualité tu dois décider deux choses :

1. "excel_theme" : LA colonne thématique du classeur qui correspond le mieux \
au sujet PRINCIPAL de l'actu. Choisis EXACTEMENT une valeur parmi cette \
liste fermée (recopie-la telle quelle) : """ + ", ".join(f'"{t}"' for t in TRACKER_THEME_OPTIONS) + """. \
Si l'actu touche plusieurs thèmes techniques (ex. solaire + stockage), choisis \
celui qui domine réellement le sujet de l'actu (ex. un projet présenté comme \
"projet de stockage" va dans BATTERIES / STOCKAGE même s'il est couplé à du \
solaire). "DIVERS" est le choix par défaut si rien d'autre ne convient \
clairement (marché, réglementation, sujet transverse...).

2. "acteur" : si l'actu concerne principalement UNE société/organisation \
identifiable (ex. "EDF", "CVE", "Akuo", "DGEC", "RTE"), donne son nom court \
tel qu'on l'utiliserait comme étiquette (pas de phrase). Si l'actu ne \
concerne pas un acteur précis mais un sujet général (marché, réglementation, \
tendance...), renvoie null pour "acteur" et propose à la place un \
"sujet_divers" court (2-4 mots, MAJUSCULES/casse libre) résumant le sujet \
(ex. "TENSION MOYEN-ORIENT", "DÉCARBONATION INDUSTRIELLE").

Réponds UNIQUEMENT avec un objet JSON de la forme :
{"items": [{"index": 0, "excel_theme": "SOLAIRE", "acteur": "EDF", \
"sujet_divers": null}, ...]}
Un élément par actu reçue, dans le même ordre, en reprenant exactement \
l'"index" fourni."""


def classify_for_tracker(entries: list[dict]) -> list[dict]:
    """entries : liste ordonnée de dicts avec au moins title/summary (déjà \
rédigés pour la synthèse finale). Retourne, dans le même ordre, une liste de \
dicts {"excel_theme": ..., "acteur": ... ou None, "sujet_divers": ... ou None} \
pour classer chaque actu dans le classeur Excel de suivi (voir tracker_excel.py)."""
    if not entries:
        return []
    if not MISTRAL_API_KEY:
        raise RuntimeError(
            "MISTRAL_API_KEY manquante : renseigne-la dans le fichier .env "
            "(voir .env.example)."
        )

    payload = [
        {"index": i, "title": e["title"], "summary": e["summary"]}
        for i, e in enumerate(entries)
    ]

    resp = requests.post(
        MISTRAL_URL,
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MISTRAL_MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": TRACKER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
            ],
        },
        timeout=180,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(raw)

    results = [None] * len(entries)
    for item in parsed.get("items", []):
        idx = item.get("index")
        if not isinstance(idx, int) or not (0 <= idx < len(entries)):
            continue
        theme = item.get("excel_theme") or "DIVERS"
        if theme not in TRACKER_THEME_OPTIONS:
            theme = "DIVERS"
        results[idx] = {
            "excel_theme": theme,
            "acteur": _clean_text(item.get("acteur")) if item.get("acteur") else None,
            "sujet_divers": _clean_text(item.get("sujet_divers")) if item.get("sujet_divers") else None,
        }

    # Filet de sécurité : une entrée non renvoyée par Mistral part quand même
    # dans le classeur plutôt que d'être perdue, juste sans classification fine.
    for i, r in enumerate(results):
        if r is None:
            results[i] = {"excel_theme": "DIVERS", "acteur": None, "sujet_divers": None}

    return results


def _clean_text(text: str) -> str:
    """Filet de sécurité : retire toute syntaxe Markdown résiduelle et \
décode les entités HTML échappées, même si le modèle respecte mal la consigne."""
    text = re.sub(r"\[([^\]]*)\]\((https?://[^\s)]+)\)", r"\2", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\w)([*_])(?!\s)(.*?)(?<!\s)\1(?!\w)", r"\2", text, flags=re.DOTALL)
    text = text.replace("**", "").replace("__", "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()
