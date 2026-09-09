# truthloop — Spécification de design

Date : 2026-09-08
Statut : approuvé après trois relectures (v3), en attente de relecture utilisateur
Auteur : Patrick Bartosik (avec Claude)

## 1. Contexte et objectif

Un workflow GitHub Copilot pour VS Code (agents custom, RAG et Graph RAG) permet de
rétro-ingénierer un back-end Magic XPA, sa documentation et ses release notes : questions
d'architecture, diagrammes, analyse d'impact (programmes appelants / appelés, tables
touchées), questions sur les nouvelles fonctionnalités.

Problème : rien ne mesure si une réponse est complète. Un agent peut oublier des programmes
impactés, citer un programme qui n'existe pas, ou affirmer une relation d'appel fausse.

Objectif : un système d'évaluation **semi-agentique** qui, pendant le workflow, note la
sortie des agents avec un **score de confiance 0-100**, produit un **plan de réparation**
quand le score est sous le seuil, et n'autorise la publication de la réponse qu'au-dessus du
seuil (90 par défaut, calibré sur données).

Le projet s'appelle `truthloop` (paquet Python géré par uv, déjà initialisé).

## 2. Contraintes

| Contrainte | Conséquence de design |
|---|---|
| Aucun accès LLM côté Python (Copilot Chat est le seul LLM) | Le harness Python est 100 % déterministe. Le jugement sémantique est délégué à un agent Copilot qui remplit une rubrique structurée. |
| Pas de MCP externe, pas de hooks, pas de GitHub CLI | Le seul pont Copilot ↔ Python est le terminal intégré (`runCommands`) et le système de fichiers. |
| Revue sécurité des dépendances | Dépendances runtime minimales : `pydantic`, `pyyaml`, `rich`. CLI en `argparse`. Pas de Ragas (92 paquets transitifs, métriques phares dépendantes d'un LLM). |
| Base de connaissances = fichiers versionnés (JSON / CSV) **et** SQLite local | Deux adaptateurs derrière un même protocole `KnowledgeSource`. Pas de Neo4j. |
| Agents custom `.github/agents` avec terminal autorisé | Boucle in-loop possible : orchestrateur → retrievers → juge → `truthloop verify` → repair → … |
| Pas de Docker en phase 1 | uv garantit la reproductibilité (`uv.lock`, `.python-version`). Un `Dockerfile` CI est une option de phase ultérieure. |

## 3. Architecture

Deux mondes qui communiquent uniquement par fichiers et terminal :

```
.github/agents/                              truthloop (uv, Python ≥ 3.11)
┌────────────────────────┐  answer.json      ┌────────────────────────────┐
│ truthloop-orchestrator │  evidence.json    │ truthloop verify --run DIR │
│  dispatch retrievers   │ ───────────────▶  │  ├ contracts (pydantic)    │
│  applique repair_plan  │                   │  ├ knowledge (sqlite/file) │
│          │ subagent    │  judge.json       │  ├ graders déterministes   │
│          ▼            │ ───────────────▶  │  ├ scoring + gates         │
│ truthloop-judge        │ ◀───────────────  │  └ repair planner          │
│  rubrique sémantique   │  verdict.json     └────────────────────────────┘
│  lance le terminal     │  (+ repair_plan)
└────────────────────────┘
```

Répartition des responsabilités :

- **Copilot** : comprendre la question, chercher (RAG / Graph RAG), rédiger, juger la fidélité
  sémantique d'une claim par rapport à une évidence.
- **Python** : tout ce qui doit être exact et rejouable. Existence des entités citées, rappel
  de couverture sur le graphe, tables oubliées, cohérence claim ↔ graphe, agrégation du score,
  décision, plan de réparation, trace d'audit.

Pattern de référence : *evaluator-optimizer* (Anthropic, « Building effective agents »)
combiné à la boucle corrective de CRAG (Corrective RAG) et au déclenchement de retrieval
ciblé de FLARE. Le vocabulaire des métriques reprend les définitions Ragas
(`faithfulness`, `context_recall`, `context_precision`) pour rester comparable.

Modules Python (un par responsabilité, testables isolément) :

| Module | Rôle | Dépend de |
|---|---|---|
| `truthloop.contracts` | Modèles pydantic des six contrats (§4) et normalisation des ids. | pydantic |
| `truthloop.knowledge` | Protocole `KnowledgeSource`, `SqliteGraphSource`, `FileGraphSource`. | contracts, sqlite3 |
| `truthloop.graders` | Six graders purs (§6). | contracts, knowledge |
| `truthloop.scoring` | Agrégation, plafonds, décision (§6.1, §6.2). | contracts |
| `truthloop.repair` | Génération du `repair_plan` depuis les findings (§7). | contracts |
| `truthloop.runs` | Layout du dossier de run, lecture / écriture, trace, provenance (§8.1). | contracts |
| `truthloop.config` | Chargement et validation de `truthloop.yaml` (§8.3). | pydantic, pyyaml |
| `truthloop.cli` | Sous-commandes argparse, rendu Rich ou JSON (§8.2). | tous |
| `truthloop.golden` | Contrat golden, synthèse, `eval`, `calibrate` (§6.3, §8.4). Phase 3. | knowledge, scoring |

## 4. Contrat de données

Modèles pydantic v2 (`ConfigDict(extra="forbid", strict=True)`), schémas JSON exportables par
`truthloop schema export` pour être collés dans les prompts des agents. Tous les fichiers
portent `schema_version` (entier, démarre à 1).

### 4.0 Règles transversales

- **Normalisation des ids** : `normalize(raw) = raw.strip().casefold()` puis remplacement de
  toute séquence de `-`, `_`, espaces par un unique `_`. Une seule fonction, partagée par les
  contrats, les sources et les graders. Les ids sont stockés normalisés dans les modèles.
- **Référence typée** : une entité est toujours un couple `(type, id)`. Dans `answer.json`,
  `claims[].entities`, `relation.subject`, `relation.object` et `abstentions[].entities` sont
  des ids qui **doivent figurer dans `answer.entities`** ; le type y est retrouvé. Pour une
  `relation`, le type attendu est déduit du prédicat (`calls` / `called_by` : programme →
  programme ; `reads` / `writes` : programme → table) et l'id doit figurer dans
  `answer.entities` avec ce type. Un id absent de `answer.entities` invalide le contrat.
- **Doublons** : `answer.entities` est dédoublonné sur `(type, id)` normalisé après
  validation (toléré, pas rejeté). Un même id cité en `program` et en `table` donne deux
  entités distinctes, résolues indépendamment.
- **Cohérence croisée** : `question_id` et `iteration` doivent être identiques dans
  `answer.json`, `evidence.json` et `judge.json`, et `question_id` doit égaler `question.id` ;
  sinon contrat invalide.

### 4.1 `question.json`

```json
{
  "schema_version": 1,
  "id": "q-2026-09-08-001",
  "text": "Quels programmes et tables sont impactés si je modifie PRG_ORD_VALID ?",
  "intent": "impact_analysis",
  "pivot_entities": [{"type": "program", "id": "PRG_ORD_VALID"}],
  "direction": "both",
  "depth": 2
}
```

- `intent` ∈ `impact_analysis` | `architecture` | `feature` | `diagram`. L'intent ne change
  pas le calcul des graders ; il sert au reporting et au seuil (§6.2) et détermine si une
  liste de claims vide est acceptable (§6, EvidenceSupport).
- `pivot_entities` : programmes et / ou tables (`type` ∈ `program` | `table`, restriction portée par le
  schéma JSON lui-même). Peut être vide (question ouverte).
- `direction` ∈ `callers` | `callees` | `both` (défaut `both`). Toujours utilisé dès qu'un
  pivot existe.
- `depth` : profondeur de fermeture transitive attendue (défaut 1, min 1, max 5).

### 4.2 `answer.json`

```json
{
  "schema_version": 1,
  "question_id": "q-2026-09-08-001",
  "iteration": 1,
  "producer": "graph-retriever",
  "entities": [
    {"type": "program", "id": "PRG_ORD_VALID"},
    {"type": "program", "id": "PRG_ORD_SAVE"},
    {"type": "table", "id": "T_ORDERS"}
  ],
  "claims": [
    {
      "id": "c1",
      "text": "PRG_ORD_SAVE appelle PRG_ORD_VALID après validation du panier.",
      "entities": ["PRG_ORD_SAVE", "PRG_ORD_VALID"],
      "citations": ["ev-12", "ev-30"],
      "relation": {"subject": "PRG_ORD_SAVE", "predicate": "calls", "object": "PRG_ORD_VALID"},
      "confidence_self": 0.8
    }
  ],
  "abstentions": [
    {"text": "Appelants de PRG_ORD_VALID au-delà de la profondeur 1 non explorés.", "entities": ["PRG_ORD_VALID"]}
  ],
  "final_text": "…réponse rédigée destinée à l'utilisateur…"
}
```

- `entities[].type` ∈ `program` | `table` | `doc` | `release`.
- `claims[].id` uniques dans le fichier. `claims[].relation` est optionnel ; `predicate` ∈
  `calls` | `called_by` | `reads` | `writes`.
- `abstentions` : zones d'ombre déclarées. Elles sont **reportées** dans le verdict comme
  `declared_gaps` et **n'altèrent aucun score** : une abstention n'est ni une hallucination
  ni une excuse pour un rappel incomplet. Elles servent au lecteur humain et à l'escalade.

### 4.3 `evidence.json`

```json
{
  "schema_version": 1,
  "question_id": "q-2026-09-08-001",
  "iteration": 1,
  "chunks": [
    {"id": "ev-12", "source": "graph:calls", "text": "PRG_ORD_SAVE -> PRG_ORD_VALID (call, task 3)", "score": 0.91},
    {"id": "ev-30", "source": "docs/orders.md#L40", "text": "…", "score": 0.77}
  ]
}
```

`chunks[].id` uniques. `score` optionnel (∈ [0, 1] s'il est présent).

### 4.4 `judge.json` (rempli par l'agent juge Copilot)

```json
{
  "schema_version": 1,
  "question_id": "q-2026-09-08-001",
  "iteration": 1,
  "judge_model": "…",
  "claims": [
    {"id": "c1", "verdict": "supported", "rationale": "ev-12 montre l'appel explicite."}
  ],
  "relevance": 0.9,
  "completeness": 0.7,
  "notes": "Le juge n'a pas trouvé d'évidence pour les tables écrites."
}
```

- `verdict` ∈ `supported` | `partially` | `unsupported` | `contradicted`.
- `relevance`, `completeness` ∈ [0, 1].
- Chaque `claims[].id` doit exister dans `answer.json` ; sinon le contrat est invalide.
- Une claim de `answer.json` **absente** de `judge.json` est comptée `unsupported`
  (fail-closed) et génère un finding `JUDGE_INCOMPLETE` (major).

### 4.5 `verdict.json` (produit par `truthloop verify`)

Exemple cohérent avec §6 : E contient 5 programmes attendus dont 3 cités (`context_recall`
0.6), T contient 2 tables dont 1 citée (`table_recall` 0.5).

```json
{
  "schema_version": 1,
  "question_id": "q-2026-09-08-001",
  "iteration": 1,
  "score": 76.5,
  "decision": "repair",
  "threshold": 90,
  "components": {
    "context_recall": {"value": 0.6, "weight": 0.35, "applicable": true},
    "table_recall": {"value": 0.5, "weight": 0.15, "applicable": true},
    "evidence_support": {"value": 1.0, "weight": 0.15, "applicable": true},
    "faithfulness": {"value": 1.0, "weight": 0.25, "applicable": true},
    "relevance_completeness": {"value": 0.8, "weight": 0.10, "applicable": true}
  },
  "caps_applied": [],
  "findings": [
    {"code": "MISSING_ENTITY", "severity": "major", "entity": {"type": "program", "id": "prg_ord_notify"}, "detail": "Appelant direct de prg_ord_valid non cité."},
    {"code": "MISSING_ENTITY", "severity": "major", "entity": {"type": "program", "id": "prg_ord_archive"}, "detail": "Appelé de prg_ord_save (profondeur 2) non cité."},
    {"code": "MISSING_TABLE", "severity": "major", "entity": {"type": "table", "id": "t_order_lines"}, "detail": "Écrite par prg_ord_save."}
  ],
  "declared_gaps": ["Appelants de PRG_ORD_VALID au-delà de la profondeur 1 non explorés."],
  "repair_plan": { "…schéma en §7…" },
  "provenance": {
    "harness_version": "0.1.0",
    "inputs_sha256": "…",
    "config_sha256": "…",
    "knowledge_source": "sqlite:knowledge/magic.db",
    "knowledge_fingerprint": "…",
    "generated_at": "2026-09-08T19:40:12+02:00"
  }
}
```

- Vérification : `raw = 100 · (0.6·0.35 + 0.5·0.15 + 1.0·0.15 + 1.0·0.25 + 0.8·0.10) / 1.0 = 76.5`.
- `decision` ∈ `release` | `repair` | `escalate` | `invalid`.
- `findings[].severity` ∈ `critical` | `major` | `info`. `entity`, `claim_id`, `depth` et `via`
  sont optionnels selon le code (`depth` / `via` portés par `MISSING_ENTITY` et `MISSING_TABLE`,
  repris tels quels dans `repair_plan.actions[].entities`).
- `caps_applied` : liste de `{"name": "contradiction", "value": 70}` (nom de la clé dans
  `scoring.caps`, valeur appliquée). `name`, comme `repair_plan.actions[].component`, est une
  énumération fermée dans le schéma JSON (noms de plafonds, noms de composantes).
- Tous les champs des contrats portent une `description` dans le schéma JSON exporté, pour qu'un
  agent puisse les consommer sans lire le code.
- `inputs_sha256` : SHA-256 de la concaténation, pour `question`, `answer`, `evidence`, `judge` dans
  cet ordre, d'une ligne `<position>:<JSON canonique>\n` par fichier (clés triées, séparateurs
  compacts, UTF-8 ; position de 0 à 3 ; fichier absent → JSON vide). Le préfixe de position évite
  qu'un fichier absent déplace le contenu d'un autre sans changer le hash. `config_sha256` : même canonisation de la config
  effective. `knowledge_fingerprint` : §5.
- Le même triplet (entrées, config, version) produit toujours le même verdict, `generated_at`
  exclu.

## 5. Sources de connaissance

Protocole `KnowledgeSource` (module `truthloop.knowledge`) :

```python
class KnowledgeSource(Protocol):
    def resolve(self, raw_id: str, entity_type: EntityType) -> EntityRef | None: ...
    def neighbors(self, program: EntityRef, direction: Direction, depth: int) -> set[EntityRef]: ...
    def programs_of(self, tables: Iterable[EntityRef]) -> set[EntityRef]: ...
    def tables_of(self, programs: Iterable[EntityRef]) -> set[EntityRef]: ...
    def has_edge(self, subject: EntityRef, predicate: Predicate, obj: EntityRef) -> bool: ...
    def fingerprint(self) -> str: ...
```

Sémantique :

- `resolve` compare sur l'id normalisé (§4.0) ; retourne `None` si aucune correspondance
  exacte après normalisation. Pas de correspondance floue.
- `neighbors` **exclut** le programme de départ du résultat ; `depth = 0` renvoie l'ensemble
  vide. `callers` suit les arêtes
  `calls` en sens inverse, `callees` en sens direct, `both` l'union, jusqu'à `depth` sauts
  (parcours en largeur, ensemble de visités).
- `programs_of` : programmes ayant une ligne `program_tables` vers l'une des tables.
- `tables_of` : tables ayant une ligne `program_tables` depuis l'un des programmes, tout
  `access` confondu.
- `has_edge(a, calls, b)` : arête `calls(a, b)` présente. `called_by(a, b)` ≡ `calls(b, a)`.
  `reads(p, t)` : ligne `program_tables(p, t)` avec `access ∈ {read, both}`. `writes(p, t)` :
  `access ∈ {write, both}`.
- `fingerprint` : SHA-256 du contenu pour les fichiers ; pour SQLite, SHA-256 de
  `"{taille}:{mtime_ns}"` du fichier `.db`.

Schéma logique commun (indépendant du stockage) :

| Relation | Colonnes |
|---|---|
| `programs` | `id`, `name`, `kind` (optionnel), `folder` (optionnel) |
| `tables` | `id`, `name` |
| `calls` | `caller_id`, `callee_id`, `call_type` (optionnel) |
| `program_tables` | `program_id`, `table_id`, `access` ∈ `read` / `write` / `both` |
| `docs` | `id`, `title`, `source`, `version` (optionnel) — optionnelle |

### 5.1 `SqliteGraphSource`

Ouvre la base en lecture seule (`file:…?mode=ro`, stdlib `sqlite3`). Les requêtes SQL sont
**surchargeables dans `truthloop.yaml`** afin de s'adapter au schéma réel de la base sans
modifier le code. Chaque requête doit renvoyer les colonnes du schéma logique (alias SQL) :

```yaml
knowledge:
  kind: sqlite
  path: knowledge/magic.db
  queries:
    programs: "SELECT prog_id AS id, prog_name AS name FROM xpa_programs"
    calls: "SELECT src AS caller_id, dst AS callee_id FROM xpa_calls"
    tables: "SELECT tbl_id AS id, tbl_name AS name FROM xpa_tables"
    program_tables: "SELECT prog_id AS program_id, tbl_id AS table_id, mode AS access FROM xpa_prog_tables"
```

Requêtes par défaut (si `queries` est vide) : `SELECT id, name FROM programs`, `SELECT id,
name FROM tables`, `SELECT caller_id, callee_id FROM calls`, `SELECT program_id, table_id,
access FROM program_tables`, `SELECT id, title, source FROM docs` (ignorée si la table
n'existe pas).

Au chargement, la source exécute les quatre requêtes obligatoires (`docs` optionnelle) et
construit en mémoire des index normalisés (dictionnaires d'adjacence). Le graphe Magic tient
en mémoire ; cela rend `neighbors` indépendant des CTE récursives et borné par `depth`.

### 5.2 `FileGraphSource`

Lit le même schéma logique depuis un dossier : soit un `graph.json` unique (clés
`programs`, `tables`, `calls`, `program_tables`, `docs` optionnelle), soit un CSV par
relation (`programs.csv`, `calls.csv`, …, en-têtes = colonnes du schéma logique). Le support
des fiches Markdown avec frontmatter est prévu en phase 3.

## 6. Graders et modèle de score

Chaque grader est une fonction pure
`grade(question, answer, evidence, judge | None, knowledge) -> GraderResult` avec
`value: float | None` (∈ [0, 1], `None` si non applicable), `findings: list[Finding]`,
`cap: int | None`.

Trois graders sont **gate-only** : ils n'ont pas de composante dans `components`, seulement
des findings et un plafond éventuel. Quatre graders produisent cinq composantes.

Notations : P = pivots programmes de la question ; P_t = pivots tables ;
E = programmes attendus ; C = programmes cités (`answer.entities`, type `program`) **moins P** ;
T = tables attendues ; C_t = tables citées **moins P_t**. Tous des ensembles d'ids normalisés.

| Grader | Calcul | Effet |
|---|---|---|
| **CitationValidity** (gate-only) | Pour chaque entité de `answer.entities` de type `program` / `table` : `resolve`. Les types `doc` / `release` sont résolus sur `docs.id` seulement si la relation `docs` est fournie, ignorés sinon. Un pivot inconnu qui figure aussi dans `answer.entities` ne produit que `UNKNOWN_PIVOT` (pas de doublon `UNKNOWN_ENTITY`). | Entité introuvable → finding `UNKNOWN_ENTITY` (critical), **plafond `unknown_entity`** (50). Pivot introuvable → `UNKNOWN_PIVOT` (critical), même plafond, et Coverage / TableCoverage non applicables. |
| **Coverage** (`context_recall`) | `Q = programs_of(P_t)` ; `E = ⋃_{p∈P} neighbors(p, direction, depth)` ∪ `Q` ∪ `⋃_{q∈Q} neighbors(q, direction, depth−1)`, moins P (les programmes qui utilisent une table pivot comptent comme premier saut ; à `depth = 1`, ils forment E à eux seuls). `recall = |E ∩ C| / |E|`. Non applicable si P ∪ P_t est vide, si un pivot est inconnu, ou si E est vide. | Poids 0.35. `E \ C` → un finding `MISSING_ENTITY` (major) par programme, avec la profondeur à laquelle il a été atteint. `C \ E` existant dans le graphe → `EXTRA_ENTITY` (info, sans pénalité). |
| **TableCoverage** (`table_recall`) | `T = tables_of(E ∪ P)` moins P_t ; `recall = |T ∩ C_t| / |T|`. Non applicable si Coverage non applicable ou si T est vide. | Poids 0.15. `T \ C_t` → `MISSING_TABLE` (major) avec le programme qui la référence. |
| **EvidenceSupport** | Une claim est supportée si au moins une de ses citations existe dans `evidence.json` **et** que le texte du chunk **contient** l'id normalisé d'au moins une entité de la claim. Règle de contenance : le texte **et** l'id sont découpés de la même façon en « parties » (séparation sur `[^\w-]+`, normalisation §4.0, puis séparation sur `_`, parties vides ignorées) ; l'id est contenu si la séquence de ses parties apparaît telle quelle, contiguë, dans les parties du texte. Ainsi `PRG-ORD-VALID`, `prg_ord_valid`, `PRG ORD VALID`, `PRG- ORD- VALID` matchent `prg_ord_valid`, `REL-2026.1` matche `rel_2026.1`, et `t_orders` ne matche pas `t_order_lines`. Un id qui est un préfixe d'un id plus long est en revanche reconnu (`prg_ord_valid` dans `PRG_ORD_VALID_X`) : comportement assumé pour les identifiants hiérarchiques Magic, à resserrer en phase 3 si la calibration montre de faux supports ; une claim sans entité est supportée si au moins une citation existe. `score = supportées / total`. Non applicable si `claims` est vide. | Poids 0.15. Claim non supportée → `UNSUPPORTED_CLAIM` (major). Citation vers un chunk inexistant → `DANGLING_CITATION` (major). `claims` vide et `intent ≠ diagram` → `NO_CLAIMS` (major) et **plafond `missing_claims`** (85). |
| **Consistency** (gate-only) | Pour chaque claim avec `relation` dont sujet et objet sont résolus : `has_edge`. Les relations dont une entité est inconnue sont ignorées ici (déjà traitées par CitationValidity). | Absence d'arête → `CONTRADICTED_BY_GRAPH` (critical), **plafond `contradiction`** (70). |
| **Encoding** (gate-only, ajouté le 2026-09-09) | Sur `final_text`, le texte de chaque claim et de chaque abstention : présence de la signature d'un double encodage UTF-8 → Windows-1252 (`Ã` ou `Â` suivi d'un caractère U+0080–U+00BF, `â€`, ou un U+FEFF dans la chaîne). Heuristique textuelle pure, sans source de connaissance ; ces séquences n'apparaissent pas en prose française, anglaise ou polonaise. | Signature trouvée → `MOJIBAKE` (critical), un finding par claim touchée plus un pour `final_text` / `abstentions`. **Pas de plafond** : le score reste intact, la décision ne peut être `release` (§6.2), et le planner émet une action `improve_answer` critique « réécrire answer.json avec l'outil d'édition ». Motivation : PowerShell réencode le texte des commandes Copilot ; sans ce garde-fou, une réponse à 100 serait publiée avec `publiÃ©e`. |
| **Rubric** (adaptateur `judge.json`) | `faithfulness = (supported + 0.5 · partially) / total_claims`, dénominateur = claims de `answer.json` ; non applicable si `claims` vide. `relevance_completeness = (relevance + completeness) / 2`. | Poids 0.25 et 0.10. Claim absente du juge → `JUDGE_INCOMPLETE` (major, sans `JUDGE_UNSUPPORTED` en plus) ; `unsupported` → `JUDGE_UNSUPPORTED` (major) ; `partially` → `JUDGE_PARTIAL` (info) ; `contradicted` → `CONTRADICTED_BY_EVIDENCE` (critical), **plafond `contradiction`** (70). `judge.json` absent → les deux composantes non applicables, `JUDGE_MISSING` (major), **plafond `missing_judge`** (85). |

Note : avec `missing_judge = 85 < release_threshold = 90`, `judge.json` est de fait
obligatoire pour publier. C'est voulu : aucune publication sans revue sémantique.

### 6.1 Agrégation

```
raw   = 100 · Σ_i w_i · s_i / Σ_i w_i          (somme sur les composantes applicables)
score = min(raw, cap_1, cap_2, …)              (plafonds des gates déclenchées)
```

Si aucune composante n'est applicable, `raw = 0`. Contrat invalide (schéma pydantic,
référence croisée cassée) → `score = 0`, `decision = invalid`, aucune composante.

### 6.2 Décision

```
threshold = release_threshold                 (90 par défaut)
          | release_threshold_no_reference    (95 par défaut, si Coverage non applicable)

release  si score ≥ threshold et aucun finding critical
repair   sinon, si iteration < max_iterations (3 par défaut)
escalate sinon
```

La comparaison au seuil se fait sur le flottant non arrondi ; l'arrondi à une décimale ne
concerne que l'affichage et `verdict.json`. Jamais de `release` sous le seuil, y compris à la
dernière itération.

### 6.3 Calibration (phase 3)

Le seuil n'est pas décrété, il est mesuré. `truthloop calibrate` lit un rapport `eval`
(§8.4) dont les runs portent une annotation humaine `human_verdict.json` et calcule, pour
chaque seuil candidat (pas de 1 entre 50 et 100) : précision des réponses qui seraient
publiées, taux de publication, ECE (10 bins de largeur égale) et score de Brier du score
normalisé. Il recommande le plus petit seuil dont la précision ≥ `target_precision` (0.95 par
défaut). Le rapport indique aussi la calibration de `confidence_self` déclaré par les agents
(moyenne de `confidence_self` sur les claims `supported` vs `unsupported`), pour détecter un
agent sur-confiant.

## 7. Boucle de réparation

`repair_plan` est un contrat à part entière (modèle pydantic, schéma exporté) :

```json
{
  "schema_version": 1,
  "actions": [
    {
      "id": "a1",
      "kind": "retrieve_entities",
      "priority": 1,
      "expected_gain": 14.0,
      "entities": [
        {"type": "program", "id": "prg_ord_notify", "depth": 1, "via": "prg_ord_valid"},
        {"type": "program", "id": "prg_ord_archive", "depth": 2, "via": "prg_ord_save"}
      ],
      "queries": {
        "graph": "Lister les appelants et appelés de prg_ord_valid jusqu'à la profondeur 2, inclure prg_ord_notify et prg_ord_archive.",
        "rag": "prg_ord_notify prg_ord_archive"
      },
      "instruction": "Citer chaque programme trouvé dans answer.entities et appuyer chaque claim par un chunk."
    },
    {"id": "a2", "kind": "retrieve_entities", "priority": 2, "expected_gain": 7.5, "entities": [{"type": "table", "id": "t_order_lines", "via": "prg_ord_save"}], "queries": {"graph": "…", "rag": "…"}, "instruction": "…"},
    {"id": "a3", "kind": "verify_claim", "priority": 3, "expected_gain": 6.7, "claim_ids": ["c4"], "instruction": "Trouver une évidence pour c4 ou retirer la claim."}
  ],
  "summary_for_agent": "Rappel 0.6 : 2 programmes manquants (prg_ord_notify, prg_ord_archive). 1 table manquante (t_order_lines). 1 claim sans évidence (c4)."
}
```

- `kind` ∈ `retrieve_entities` | `verify_claim` | `write_claims` | `improve_answer` |
  `fix_question` | `run_judge` | `fix_contract`.
- Champs communs : `id`, `kind`, `priority` (1 = premier), `expected_gain` (points de score,
  déterministe), `instruction`. Champs spécifiques : `entities` + `queries`
  (`retrieve_entities`), `claim_ids` et `entities` optionnel (`verify_claim`), `entities`
  (`fix_question`, le pivot fautif), `component` (`improve_answer`, nom de la composante la plus
  basse), `errors` (`fix_contract`, liste de `{"loc": "…", "msg": "…"}` issus de pydantic).

Génération (uniquement si `decision ≠ release` ; pour `release`, le planner n'est pas
appelé et `actions = []`), dans l'ordre :

| Findings | Action | `expected_gain` |
|---|---|---|
| Contrat invalide | `fix_contract` (unique) | 100 |
| `UNKNOWN_PIVOT` | `fix_question` : corriger l'id du pivot | 100 − score |
| `JUDGE_MISSING` | `run_judge` | `100 · (w_faith + w_rel) / Σ w` (Σ w = somme de **tous** les poids configurés, ici et dans les lignes suivantes) |
| `MISSING_ENTITY` (tous, regroupés en une action) | `retrieve_entities` type `program` | `100 · w_recall · |manquants| / |E| / Σ w` |
| `MISSING_TABLE` (regroupés) | `retrieve_entities` type `table` | `100 · w_table · |manquantes| / |T| / Σ w` |
| `NO_CLAIMS` | `write_claims` : rédiger des claims citées pour les entités présentes | `100 − score` |
| `UNSUPPORTED_CLAIM`, `DANGLING_CITATION`, `CONTRADICTED_*`, `JUDGE_INCOMPLETE`, `JUDGE_UNSUPPORTED`, `JUDGE_PARTIAL` (regroupés par claim) | `verify_claim` | `100 · (w_evid + w_faith) / total_claims / Σ w` par claim (`total_claims ≥ 1` par construction, ces findings n'existant que s'il y a des claims), plus `max(0, min(raw, autres plafonds) − plafond)` si le finding est le dernier de sa gate |
| `UNKNOWN_ENTITY` référencée par au moins une claim | `verify_claim` de cette claim (`entities` renseigné) | idem ci-dessus |
| `UNKNOWN_ENTITY` référencée par aucune claim (regroupées) | `verify_claim` avec `claim_ids: []` et `entities` : corriger l'id ou retirer de `answer.entities` | `max(0, min(raw, autres plafonds) − plafond)` |
| Aucune action générée alors que `decision ≠ release` (ex. `relevance_completeness` bas, ou rappel < 1 par arrondi) | `improve_answer` : `component` = composante applicable la plus basse, `instruction` = `judge.notes` s'il existe, sinon gabarit par composante | `100 − score` |

`priority` = tri par sévérité maximale décroissante, puis `expected_gain` décroissant, puis
`kind` alphabétique, puis id. `summary_for_agent` : au plus trois phrases générées par
gabarit (une par famille d'actions présente), en français.

Le plan est vide (`actions: []`) si et seulement si la décision est `release` : le
court-circuit ci-dessus garantit le sens direct, la règle `improve_answer` garantit au moins
une action pour toute décision `repair`, `escalate` ou `invalid`. « Dernier finding de sa
gate » s'évalue dans l'ordre d'émission des findings (graders exécutés dans l'ordre fixe
CitationValidity, Coverage, EvidenceSupport, Consistency, Rubric ; chacun parcourt les claims et
les entités dans l'ordre de `answer.json`), ce qui rend `expected_gain` déterministe. Le bonus
ne s'applique qu'aux actions `verify_claim`.

L'exemple JSON ci-dessus est indépendant de celui du §4.5 (l'action `a3` suppose une claim
`c4` sans évidence).

## 8. Dossier de run, CLI, configuration, golden

### 8.1 Layout

```
runs/<question-id>/
  question.json
  human_verdict.json                       # optionnel, annotation humaine (§8.4)
  iter-01/answer.json  evidence.json  judge.json  verdict.json
  iter-02/…
  trace.jsonl            # une ligne par événement : {"ts", "iteration", "event", "score", "decision"}
```

### 8.2 Commandes (argparse, sortie Rich en TTY, JSON avec `--json`)

| Commande | Rôle | Code retour |
|---|---|---|
| `truthloop init [--config truthloop.yaml]` | Crée `truthloop.yaml`, `runs/`, `golden/`, `reports/`, exporte les schémas dans `schemas/`. | 0 |
| `truthloop verify --run runs/<id> [--iteration N]` | Évalue la dernière itération (ou N), écrit `verdict.json`, ajoute une ligne à `trace.jsonl`, imprime le résumé. Un `iteration` dans les fichiers différent du numéro du dossier `iter-NN` invalide le contrat. | 0 release, 2 repair, 3 escalate, 4 invalid, 1 erreur |
| `truthloop schema export [--out schemas/]` | Écrit les JSON Schema des six contrats (question, answer, evidence, judge, verdict, repair_plan) et du golden. | 0 |
| `truthloop trace --run runs/<id>` | Historique des itérations : score, décision, findings ouverts / résolus entre itérations. | 0 |
| `truthloop golden synth --program P [--direction both] [--depth N] [--out golden/cases.jsonl]` | Ajoute un cas golden (entités et tables attendues) dérivé du graphe. | 0 |
| `truthloop eval --golden golden/cases.jsonl --runs runs/ [--baseline reports/main.json] [--out reports/x.json] [--markdown]` | Régression : métriques par cas et agrégées, diff contre une baseline, liste des régressions. | 0, 5 si régression détectée |
| `truthloop calibrate --report reports/x.json [--target-precision 0.95]` | Courbes précision / taux de publication, ECE, Brier, seuil recommandé. | 0 |

Erreurs communes (code 1, aucun `verdict.json` écrit) : dossier de run ou `question.json`
introuvable, config invalide, source de connaissance inaccessible ou requête SQL en erreur.

### 8.3 `truthloop.yaml`

```yaml
schema_version: 1
knowledge: { kind: sqlite, path: knowledge/magic.db, queries: {} }   # ou kind: files, path: knowledge/
scoring:
  weights: { context_recall: 0.35, table_recall: 0.15, evidence_support: 0.15, faithfulness: 0.25, relevance_completeness: 0.10 }
  caps: { unknown_entity: 50, contradiction: 70, missing_judge: 85, missing_claims: 85 }
  release_threshold: 90
  release_threshold_no_reference: 95
loop: { max_iterations: 3 }
paths: { runs: runs, golden: golden, reports: reports }
```

Validation au chargement : poids ≥ 0 et somme > 0, plafonds et seuils ∈ [0, 100],
`max_iterations` ≥ 1, `kind` ∈ `sqlite` / `files`.

### 8.4 Contrat golden et rapport (phase 3)

`golden/cases.jsonl`, une ligne par cas :

```json
{"schema_version": 1, "id": "g-001", "question": {"…champs de question.json sans id…"}, "expected": {"programs": ["prg_ord_notify"], "tables": ["t_order_lines"]}, "tags": ["orders"], "notes": "…"}
```

- `expected` optionnel : s'il est absent, `eval` le dérive du graphe (même calcul que
  Coverage / TableCoverage). S'il est présent, il **remplace** le calcul graphe pour ce cas
  (utile pour figer une vérité terrain validée par un humain).
- `golden synth` écrit un cas avec `expected` renseigné depuis le graphe.
- Appariement golden ↔ run : `eval` cherche `runs/<golden.id>/` et évalue sa dernière
  itération ; un cas sans run est reporté `missing_run` et exclu des agrégats.

`runs/<id>/human_verdict.json` : `{"schema_version": 1, "verdict": "correct" | "incorrect",
"reviewer": "…", "notes": "…"}`.

Rapport `eval` (`reports/x.json`) : `{"schema_version": 1, "generated_at", "config_sha256",
"cases": [{"golden_id", "run_id", "iteration", "score", "decision", "components": {…},
"human_verdict": "…" | null}], "aggregate": {"mean_score", "release_rate", "mean_context_recall",
"mean_table_recall", "mean_faithfulness"}, "regressions": [{"golden_id", "metric", "baseline",
"current"}]}`. Une régression est une baisse de `score` > 1 point ou un passage
`release → non-release` par rapport à la baseline. `--markdown` écrit le même contenu en
tableau Markdown à côté du JSON.

## 9. Intégration Copilot

Fichiers livrés dans `.github/` (les agents retrievers existants ne sont pas modifiés ; ils
reçoivent le contrat via un fichier d'instructions) :

- `.github/agents/truthloop-orchestrator.agent.md` — `user-invocable: true`, `tools:
  ['agent', 'runCommands', 'read', 'edit', 'search']`, `agents: ['truthloop-judge', <retrievers
  existants>]`, `handoffs` : « Publier la réponse » et « Escalader à un humain ». Instructions :
  créer `runs/<id>/question.json`, dispatcher les retrievers, assembler `answer.json` et
  `evidence.json`, invoquer le juge, lire `verdict.json`, appliquer `repair_plan` dans l'ordre
  des `priority`, boucler tant que la décision est `repair`.
- `.github/agents/truthloop-judge.agent.md` — `user-invocable: false`, `tools:
  ['runCommands', 'read', 'edit']`. Instructions : lire `answer.json` / `evidence.json`,
  remplir `judge.json` claim par claim selon la rubrique, exécuter `uv run truthloop verify
  --run … --json`, renvoyer à l'orchestrateur le score, la décision et `summary_for_agent`.
- `.github/instructions/truthloop-contract.instructions.md` — le contrat `answer.json` /
  `evidence.json` avec les schémas exportés et les règles (ids normalisés, entités des claims
  déclarées dans `entities`, abstentions explicites, citations obligatoires).

Format vérifié dans la documentation VS Code du 2026-09-08 (frontmatter `name`,
`description`, `tools`, `agents`, `handoffs`, `user-invocable`, `disable-model-invocation`).

## 10. Gestion des erreurs

Philosophie **fail-closed** : aucune erreur ne mène à `release`.

| Situation | Comportement |
|---|---|
| `question.json` introuvable ou invalide, dossier de run absent | Code retour 1, message explicite, aucun `verdict.json` (le run n'est pas identifiable). |
| `answer.json` ou `evidence.json` manquant ou invalide, référence croisée cassée (§4.0, §4.4) | `decision = invalid`, `score = 0`, `fix_contract` avec les erreurs pydantic (`loc`, `msg`). `verdict.json` est écrit. |
| `judge.json` absent | Composantes rubrique non applicables, plafond `missing_judge`, finding `JUDGE_MISSING`, action `run_judge`. |
| `judge.json` présent mais invalide | Traité comme contrat invalide (ligne 2). |
| Source de connaissance introuvable ou requête SQL en erreur | Code retour 1, message explicite, aucun `verdict.json` écrit. |
| Pivot inconnu du graphe | `UNKNOWN_PIVOT` (critical), plafond `unknown_entity`, Coverage et TableCoverage non applicables, action `fix_question`. |
| Dépassement de `max_iterations` | `escalate`, handoff humain, `summary_for_agent` liste les findings ouverts. |
| Config invalide | Code retour 1 au chargement, avant toute évaluation. |

## 11. Tests

- **Fixture** : mini-graphe Magic fictif (8 programmes, 4 tables, appels sur 3 niveaux)
  disponible en `graph.json` et chargé dans une SQLite temporaire, pour tester les deux sources
  avec les mêmes attentes.
- **Unitaires par grader** : cas nominal, non applicable, `claims` vide, pivot table, pivot
  inconnu, doublons, id cité dans deux types, findings attendus, plafond.
- **Propriétés** : `decision = release ⇒ actions == []` et `decision ≠ release ⇒ len(actions) ≥ 1` ;
  ajouter une entité attendue ne fait jamais baisser `context_recall` ;
  un plafond déclenché borne toujours le score ; le verdict est identique sur deux exécutions
  (snapshot JSON, `generated_at` exclu).
- **Contrat** : les schémas exportés valident les exemples de ce document (l'exemple §4.5 doit
  donner exactement 76.5) ; un `claims[].id` inconnu dans `judge.json` invalide le contrat ;
  `question_id` divergents invalident le contrat.
- **CLI** : chaque commande sur un run de fixture, codes retour vérifiés.
- **Régression** : `truthloop eval` sur le golden de fixture en CI, échec si régression.
- Couverture ≥ 85 % (`--cov-fail-under=85` dans `pyproject.toml`), `ruff` et `mypy --strict`
  sans erreur.

## 12. Phases de livraison

1. **Cœur** : contrats (six + golden), normalisation, `KnowledgeSource` (SQLite + fichiers
   JSON / CSV), six graders, scoring, `verify`, `schema export`, `init`, `trace`, tests.
2. **Boucle** : repair planner, agents Copilot, fichier d'instructions.
3. **Mesure** : `golden synth`, `eval` avec baseline et rapport Markdown, `calibrate`,
   `human_verdict.json`, fiches Markdown pour `FileGraphSource`.

## 13. Hors périmètre

- Appels LLM depuis Python, MCP, hooks, GitHub CLI.
- Neo4j, LanceDB, Docker en phase 1.
- Correspondance floue des ids (seule la normalisation §4.0 est appliquée).
- Évaluation de la qualité visuelle des diagrammes : un diagramme est évalué via la liste
  d'entités qu'il contient (même contrat `answer.json`, intent `diagram`, `claims` vide toléré).
- Modification des agents retrievers existants.

## 14. Décisions et alternatives écartées

| Décision | Alternative écartée | Raison |
|---|---|---|
| Scorers custom alignés sur le vocabulaire Ragas | Ragas 0.4.3 | 92 paquets transitifs (langchain, openai, datasets…) ; métriques phares dépendantes d'un LLM ; aucune métrique de couverture d'entités sur graphe. |
| Boucle in-loop hybride | Harness hors-ligne seul | Ne bloque pas une réponse incomplète pendant le workflow. |
| Boucle in-loop hybride | Auto-critique par prompt seul | Score non calibré, non reproductible, non testable. |
| uv seul | Docker | Reproductibilité déjà assurée par `uv.lock` ; conteneur plus lent dans une boucle appelée jusqu'à 3 fois par question ; licence et revue sécurité supplémentaires. |
| SQL surchargeable dans `truthloop.yaml` | Schéma SQLite imposé | Le schéma réel de la base n'est pas figé ; l'adaptation ne doit pas demander de code. |
| Graphe chargé en mémoire | Requêtes SQL récursives à la volée | Un graphe Magic tient en mémoire ; le parcours Python est identique pour SQLite et fichiers, donc testable une seule fois. |
| Seuil calibré sur golden set | Seuil fixe 90 | Un seuil non mesuré n'a pas de signification opérationnelle. |
| Abstentions sans effet sur le score | Abstention qui réduit le dénominateur du rappel | Un agent pourrait « abstenir » tout ce qu'il n'a pas trouvé et publier une réponse incomplète. |
