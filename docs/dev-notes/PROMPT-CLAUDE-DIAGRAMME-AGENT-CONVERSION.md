# Prompt Claude — Diagramme Agent de conversion (Draw.io / architecture)

Copier **la section A** (prompt principal) dans Claude. Joindre **ce fichier entier** en pièce jointe ou coller la **section B** comme contexte si Claude le demande.

---

## A. PROMPT À COPIER DANS CLAUDE

```
Tu es un architecte logiciel senior et un expert en diagrammes d'architecture pour présentations executives / techniques.

Ta mission : produire une spécification VISUELLE TRÈS DÉTAILLÉE (prête pour Draw.io, Mermaid, ou export image) du pipeline de l'**Agent de conversion COBOL → Java** d'une plateforme de modernisation legacy.

## Objectif du diagramme
- Valoriser une architecture **volontairement sophistiquée** comme un choix de **ingénierie intelligent**, pas comme de la complexité gratuite.
- Montrer clairement : entrées, décisions, boucle, squelette déterministe, appels LLM, splice, post-traitement, sortie, cache.
- Public : consultants, architectes, management technique — ils doivent comprendre POURQUOI chaque mécanisme existe.

## Style visuel
- Professionnel, lisible en projection (police ≥ 11pt sur les libellés).
- Couleurs cohérentes :
  - Entrées : jaune #FFF9C4
  - Agent / décisions : violet #E1BEE7
  - Déterministe (Python, squelette, splice) : vert #C8E6C9 + badge "DET"
  - LLM : bleu #E3F2FD + icône nuage
  - Post-traitement : orange #FFE0B2
  - Sortie : vert foncé #A5D6A7 (document)
  - Cache : cylindre gris #ECEFF1
- Utiliser : swimlanes optionnelles, losanges pour décisions, conteneur en pointillés pour la BOUCLE, flèches étiquetées avec noms d'artefacts.
- Langue des libellés : **français** (termes techniques anglais acceptés : parser_output, splice, placeholder, fast_mode).

## NE PAS faire d'erreurs factuelles (critique)
1. Le losange "génération contrainte ?" est déclenché par :
   - programme COBOL > ~400 lignes non vides, OU
   - programme dans liste mandatory (LOANEVAL, RISKSCOR, RPTMONTH, RECOVRY)
   - **PAS** par le tier "Enterprise" seul.
2. RISKSCOR, RPTMONTH, RECOVRY sont en mode **CONTRAINT**, pas monolithique.
3. Le tier Standard / Complexe / Enterprise sert à **select_model** (gpt-4o-mini vs gpt-4o), pas au losange contrainte/monolithique.
4. L'agrégateur d'ANALYSE (amont) fusionne des chunks JSON d'analyse — il **ne assemble PAS** le Java. Le splice assemble le Java.
5. Cache conversion = **v5** (pas v2). Clé : v5_{PROGRAM}_{hash COBOL}.
6. Post-traitement diffère : léger (contrainte) vs complet (monolithique) ; compile_and_repair souvent skip pour batch ACME.
7. Cas AUTOPREM (option encadré latéral) : référence Java COBOL-faithful, skip repairs destructifs — hors chemin contraint classique si petit programme.

## Structure obligatoire du diagramme (top → bottom)

### 1. Titre
"Agent de conversion — COBOL vers Java (architecture intelligente)"

### 2. Trois entrées (parallélogrammes, flèches vers agent)
- Code source COBOL (vérité syntaxique)
- parser_output.json (paragraphes, symboles PIC, control_flow, operations)
- analysis_output.json (rôles, business_rules, complexity_tier, conversion_guidance) — produit amont par segmenter → chunker LLM → agrégateur

### 3. Bloc Agent de conversion (violet)
Inclure :
- clean_analysis_for_prompt()
- get_chunk_rules() — règles filtrées par section
- select_model(complexity_tier) : Standard → gpt-4o-mini | Complexe/Enterprise → gpt-4o
- Cylindre cache v5 en pointillé : "hit → skip LLM"

Note latérale : "Le tier choisit le MODÈLE, pas le mode contrainte/monolithique."

### 4. Losange : "Génération contrainte (F45) ?"
Critères écrits dans le losange.

### 5a. Branche OUI (colonne gauche, fond orange clair)

**5a.1 Squelette Java — 100% déterministe (DET, aucun LLM)**
Expliquer en 4 bullets :
- structured_rep = plan en mémoire Python (pas un fichier visible)
- build_java_scaffolding() → UNE string Java
- Contenu : package, imports, champs (SymbolTable), signatures void method() par paragraphe COBOL
- Chaque méthode contient : // PLACEHOLDER_FOR_PARAGRAPH_<id>

Mini-exemple code dans encadré (3-5 lignes) montrant placeholder.

**5a.2 java_source = squelette** (petite boîte — "même texte, variable de travail")

**5a.3 CONTENEUR BOUCLE (pointillés, titre "↻ POUR CHAQUE paragraphe (N itérations)")**
À l'intérieur, séquence :
1. Losange interne : "CALL sous-programme ?" → OUI : codegen Python (DET) | NON : suite
2. Boîte LLM : "1 appel — corps de méthode uniquement" + prompt (COBOL paragraphe + symboles + règles section)
3. Boîte DET : sanitize / fast_mode (compliance retry off par défaut)
4. Boîte DET : splice_method_body() — remplace UN placeholder dans java_source
5. Losange : "structure Java OK ?" → retry LLM ou stub TODO
Flèche de boucle vers "paragraphe suivant".

Montrer état progressif (encadré) : [□□□] → [■□□] → [■■□] → [■■■]

**5a.4 Après boucle (DET)**
- inject_main_if_missing()
- Sortie : classe Java assemblée

Encadré "Pourquoi ?" : programme trop volumineux ; structure fixe + logique par morceau ; précision.

### 5b. Branche NON (colonne droite, fond bleu)

**5b.1 Un seul appel LLM**
Prompt : COBOL + parser JSON + analysis nettoyé + règles (~dizaines)
→ classe Java complète en une passe

**5b.2 Pourquoi ?**
Programme compact, moins d'appels API, plus rapide.
Exemples : petits batch < 400 lignes — NE PAS lister RISKSCOR/RPTMONTH/RECOVRY ici.

### 6. Fusion (barre horizontale)
Les deux branches rejoignent.

### 7. Post-traitement (orange)
Deux sous-branches ou tableau :
- Léger (contrainte) : sanitize, profil
- Complet (monolithique) : sanitize, CALL/SORT repair, reconcile, compile_and_repair (javac)
Note : skip compile repair batch ACME

Encadré latéral AUTOPREM : référence Java + skip dangling chains

### 8. Sortie (document vert)
java_source.java + quality_score → Testing Agent (behavioral diff)

### 9. Légende (coin bas)
Formes, couleurs, symboles DET / LLM / cache

## Livrables attendus de ta part
1. **Description narrative** slide-par-slide (ce que le présentateur dit à chaque zone).
2. **Diagramme Mermaid flowchart TB** complet (syntaxe valide).
3. **Liste des formes Draw.io** : type, texte exact, couleur, connexions (tableau).
4. **Script oral 2 minutes** pour expliquer la boucle squelette → LLM → splice sans perdre l'audience.
5. **Une phrase de valorisation** : pourquoi cette complexité est un avantage compétitif vs "un seul prompt ChatGPT sur le COBOL".

Sois exhaustif, précis, et pédagogique. Pas de simplifications fausses.
```

---

## B. CONTEXTE TECHNIQUE (référence pour Claude / présentateur)

### B.1 Position dans le pipeline global

```
COBOL → Parser (DET) → Analysis (LLM chunks + agrégateur) → CONVERSION (ce diagramme) → Testing / Score
```

L'analyse amont :
- **Segmenter** (`pipeline_segmenter`) : graphe d'appels, segments, complexité segment
- **Chunker** : découpe pour appels LLM d'analyse (limites tokens)
- **Agrégateur** (`AnalysisAgent._aggregate`) : fusionne JSON → `analysis_output` unique

La conversion **consomme** `analysis_output` déjà fusionné ; elle ne refait pas le chunking d'analyse.

### B.2 Outputs de l'agent de conversion

| Sortie | Description |
|--------|-------------|
| **java_source** | Texte d'une ou plusieurs classes Java |
| **notes / repair_notes** | Stratégie, cache, échecs partiels |
| **quality_score** | 20 parse + 20 analyze + 20 convert + 40 semantic (déterministe) |

### B.3 Génération contrainte — détail technique

**Fonctions clés** (`constrained_generation.py`) :
- `should_use_constrained_generation(cobol, parser)` — seuil 400 lignes + mandatory programs
- `build_structured_representation()` — plan Python en mémoire
- `build_java_scaffolding()` — string Java + placeholders `// PLACEHOLDER_FOR_PARAGRAPH_<id>`
- Boucle `for method in rep.methods`
- `build_method_body_prompt()` → `_call_llm_with_retries()` → `splice_method_body()`
- `inject_main_if_missing()` après boucle

**Splice** = `scaffolding.replace("// PLACEHOLDER_FOR_PARAGRAPH_XXX", corps_indenté)`

**Variable java_source** : même string Java, enrichie à chaque itération (pas 36 fichiers).

**Nombre d'appels LLM** ≈ nombre de paragraphes avec logique (ex. LOANEVAL ~36), sauf paragraphes CALL (codegen Python sans LLM).

**Règles injectées** : par section/paragraphe (~ordre de grandeur 80 règles uniques programme, pas 80×N dans chaque prompt).

### B.4 Génération monolithique

- `_convert_raw()` : un prompt, une réponse = classe entière
- Post-process souvent plus lourd (reconcile, compile_and_repair)

### B.5 Post-traitement (`_postprocess_conversion`)

Ordre typique mode complet : sanitize → repairs métier → reconcile → compile_and_repair → enrich

Mode léger (constrained + flag) : sanitize + profil Java principalement

### B.6 Performance (mention optionnelle slide)

- Conversion projet : parallèle frontend (wall-clock = max programme lent)
- CONVERSION_SKIP_COMPLIANCE_RETRY default true (1 LLM/para vs 3)
- CONVERSION_LIGHTWEIGHT_POSTPROCESS default true
- ACME batch : skip compile_and_repair à la conversion
- conversion_cache v5, analysis_cache v4

### B.7 Messages clés valorisation

1. **Séparation des responsabilités** : structure déterministe, logique LLM ciblée.
2. **Scalabilité** : petits programmes rapides (monolithique + mini), gros programmes précis (contrainte + gpt-4o).
3. **Traçabilité** : 1 paragraphe COBOL ↔ 1 méthode ↔ 1 placeholder ↔ 1 splice.
4. **Qualité industrialisée** : post-process, tests comportementaux, reliability score — pas du vibe-coding.

### B.8 Erreurs à éviter dans le dessin

| Faux | Vrai |
|------|------|
| Enterprise → contrainte | Taille / mandatory → contrainte |
| Agrégateur colle le Java | Agrégateur = JSON analyse ; splice = Java |
| 2 squelettes Python + Java | structured_rep = RAM ; 1 squelette = string Java |
| java_source ≠ squelette | java_source commence comme squelette puis évolue |
| RISKSCOR monolithique | RISKSCOR contraint |
| cache v2 | cache v5 |

### B.9 Exemple mini squelette + boucle (pour encadré diagramme)

**Avant boucle :**
```java
private void validateQuote() {
    // PLACEHOLDER_FOR_PARAGRAPH_2100_VALIDATE_QUOTE
}
```

**LLM renvoie :**
```java
if (qtDriverAge < wsMinDriverAge) {
    prDecision = "REFUSE";
}
```

**Après splice :** placeholder remplacé ; autres méthodes encore en placeholder.

### B.10 Script oral boucle (30 s)

« On génère d'abord une classe Java avec des méthodes vides marquées par des commentaires-placeholder, entièrement en Python à partir du parser. Ensuite, pour chaque paragraphe COBOL, un appel LLM ne produit que les instructions à l'intérieur de la méthode ; on remplace le marqueur correspondant dans le même fichier — c'est le splice. Après N tours, la classe est complète, on ajoute le main si besoin, puis le post-traitement et les tests comportementaux. »

---

## C. Variante prompt court (si limite de tokens)

```
Génère un diagramme d'architecture détaillé (Mermaid + spec Draw.io + script oral 2 min) pour l'Agent de conversion COBOL→Java décrit dans le document joint. Respecte strictement les faits section B.8. Montre : 3 entrées, select_model vs losange contrainte, squelette DET + placeholders, boucle LLM+splice avec états [□→■], branches monolithique/contrainte, post-process dual, cache v5, sortie java_source. Français. Valorise la complexité comme ingénierie maîtrisée.
```

---

*Document préparé pour présentation COBOL Modernizer — juin 2026.*
