# truthloop

Harness d'évaluation déterministe pour les réponses produites par un workflow GitHub
Copilot (agents custom, RAG et Graph RAG) sur un back-end Magic XPA. Il note chaque
réponse avec un score de confiance 0-100 calculé à partir du graphe de programmes et de
tables (existence des entités citées, rappel de couverture, cohérence des relations), et
produit un plan de réparation quand le score reste sous le seuil de publication. Aucun
appel LLM ni réseau côté Python : mêmes entrées, même verdict, à chaque exécution.

Spécification complète : `docs/superpowers/specs/2026-09-08-truthloop-design.md`.

## Installation

```bash
uv sync
```

Python ≥ 3.11 (3.12, 3.13 et 3.14 conviennent), géré par `uv` (voir `uv.lock`). Aucun
`.python-version` n'est versionné : `uv` utilise l'interpréteur compatible déjà installé.
Dépendances runtime minimales : `pydantic`, `pyyaml`, `rich`.

## Commandes

Quatre commandes sont disponibles en phase 1 (`truthloop <commande> --help` pour le
détail des options) :

| Commande | Rôle | Code retour |
|---|---|---|
| `truthloop init [--config truthloop.yaml]` | Crée `truthloop.yaml`, `runs/`, `golden/`, `reports/`, exporte les schémas JSON dans `schemas/`. | `0` |
| `truthloop verify --run runs/<id> [--iteration N] [--json]` | Évalue la dernière itération (ou `N`), écrit `verdict.json`, ajoute une ligne à `trace.jsonl`, imprime le résumé (tableau Rich ou JSON). | `0` release · `2` repair · `3` escalate · `4` invalid · `1` erreur |
| `truthloop schema export [--out schemas/]` | Écrit les JSON Schema des six contrats (question, answer, evidence, judge, verdict, repair_plan). | `0` |
| `truthloop trace --run runs/<id> [--json]` | Historique des itérations d'un run : score, décision, findings ouverts / résolus entre deux itérations. | `0` |

Le code `1` (erreur, aucun `verdict.json` écrit) couvre les cas communs : dossier de run
ou `question.json` introuvable, `truthloop.yaml` invalide, source de connaissance
inaccessible ou requête SQL en erreur.

**Note :** `verify` ouvre la source de connaissance (`knowledge.kind`) avant de lire le
dossier de run. Une base SQLite ou un `graph.json` absent ou invalide est donc signalé
en premier, avant toute erreur liée au run lui-même.

## Layout d'un run

```
runs/<question-id>/
  question.json
  human_verdict.json                       # optionnel, annotation humaine (phase 3)
  iter-01/answer.json  evidence.json  judge.json  verdict.json
  iter-02/…
  trace.jsonl            # une ligne par itération : {"ts", "iteration", "event", "score", "decision"}
```

Le nom du dossier sous `runs/` (ici `<question-id>`) n'a pas besoin de correspondre à
`question.id` : aucune vérification n'est faite sur ce point, c'est volontaire.

## Configuration (`truthloop.yaml`)

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

Deux backends de connaissance sont supportés derrière le même protocole
`KnowledgeSource` : `sqlite` (base locale, requêtes surchargeables) et `files`
(`graph.json` ou CSV versionnés). Voir §5 et §8.3 de la spécification.

## Développement

```bash
uv run pytest -q                                    # suite complète + couverture (seuil 85 %)
uv run ruff format src tests && uv run ruff check --fix src tests
uv run mypy
```

## Exemple de mapping SQL

Le schéma de la base SQLite n'est jamais imposé : quatre requêtes dans `truthloop.yaml`
l'adaptent au schéma logique (`programs`, `tables`, `calls`, `program_tables`). Exemple réel,
anonymisé, pour un export de graphe Magic XPA dont les arêtes portent un type et un statut de
résolution, et dont les accès aux tables sont codés par des actions :

```yaml
knowledge:
  kind: sqlite
  path: generated/program-graph/graph.sqlite
  queries:
    programs: "SELECT DISTINCT TRIM(id) AS id, COALESCE(name, '') AS name FROM programs WHERE id IS NOT NULL AND TRIM(id) <> ''"
    tables: "SELECT LOWER(TRIM(table_name)) AS id, MIN(TRIM(table_name)) AS name FROM tables WHERE table_name IS NOT NULL AND TRIM(table_name) <> '' GROUP BY LOWER(TRIM(table_name))"
    calls: "SELECT DISTINCT TRIM(e.source) AS caller_id, TRIM(e.target) AS callee_id FROM edges e JOIN programs p1 ON TRIM(p1.id) = TRIM(e.source) JOIN programs p2 ON TRIM(p2.id) = TRIM(e.target) WHERE e.type = 'CALL' AND COALESCE(e.unresolved, 0) = 0"
    program_tables: "SELECT DISTINCT TRIM(program) AS program_id, LOWER(TRIM(table_name)) AS table_id, CASE WHEN actions LIKE '%LINK_WRITE%' OR actions LIKE '%LINK_CREATE%' THEN 'write' ELSE 'read' END AS access FROM tables WHERE program IS NOT NULL AND TRIM(program) <> '' AND table_name IS NOT NULL AND TRIM(table_name) <> ''"
```

Règles qui rendent ce mapping robuste : `GROUP BY LOWER(TRIM(…))` fusionne les collisions de
casse (`DUAL` / `dual`) que truthloop refuserait ; les jointures excluent les arêtes vers des
programmes inconnus ; `DISTINCT` retire les doublons ; les accès en double avec des valeurs
différentes sont fusionnés en `both` par truthloop. Les actions non classées (par exemple un
accès SQL direct) tombent en `read` : approximation à affiner si la base porte le sens de
l'accès. La base est toujours ouverte en lecture seule.

## truthloop vendu dans un autre dépôt

Si truthloop est cloné dans un sous-dossier du dépôt hôte (par exemple `<hôte>/truthloop/`),
exclure ce dossier de la collecte pytest du dépôt hôte, sinon ses tests sont ramassés dans un
environnement qui n'a pas ses dépendances :

```toml
[tool.pytest.ini_options]
norecursedirs = ["truthloop"]
```

Les tests de truthloop se lancent depuis son propre dossier avec `uv run pytest -q`.

## Phase 3 : ce que la calibration devra mesurer

Le seuil 90 est une valeur par défaut. Les cas à constituer pour le golden set, d'après le
premier branchement réel : programme très appelé, programme sans appel, appels conditionnels,
références de composant résolues (`14:*`), accès `read` / `write` / `both`, pivot inconnu,
collisions de casse, réponses incomplètes, entités inventées. Un score de 100 obtenu en
construisant la réponse à partir de la base elle-même ne mesure rien : la boucle doit être
lancée avec l'agent `truthloop-orchestrator`, jamais en écrivant `answer.json` depuis l'oracle.

## Dépannage

Sur macOS, il arrive que les fichiers créés par `uv` dans `.venv` portent le flag `hidden` ;
Python ignore alors le `.pth` de l'installation éditable et `import truthloop` échoue avec
`ModuleNotFoundError`. Remède :

```bash
chflags -R nohidden .venv
```

Sous Windows derrière un proxy d'entreprise, `uv` peut refuser le certificat interposé
(`invalid peer certificate: UnknownIssuer`) et tenter de télécharger un Python. Régler une fois
pour toutes, puis redémarrer VS Code pour que le terminal intégré hérite des variables :

```powershell
[Environment]::SetEnvironmentVariable("UV_SYSTEM_CERTS", "true", "User")   # UV_NATIVE_TLS est obsolète
[Environment]::SetEnvironmentVariable("UV_PYTHON", "C:\Users\<user>\AppData\Local\Programs\Python\Python314\python.exe", "User")
```

## Phase 2 : intégration Copilot

La phase 2 livre le kit Copilot (agents orchestrateur et juge, contrat des retrievers,
prompt d'installation, graphe de fumée, checklist) et la commande `truthloop
install-copilot`, qui l'installe dans un dépôt cible (par exemple un dépôt Magic ouvert
dans VS Code).

```bash
uv run truthloop install-copilot --target <dépôt> --knowledge sqlite:<chemin>|files:<chemin> \
    [--retrievers nom1,nom2] [--force]
```

- `--target` : dossier du dépôt cible (doit déjà exister).
- `--knowledge` : source de connaissance à écrire dans le `truthloop.yaml` du dépôt cible,
  au format `kind:chemin` (`sqlite:knowledge/magic.db` ou `files:knowledge/`). Optionnel
  seulement si `<target>/truthloop.yaml` existe déjà (il est alors relu).
- `--retrievers nom1,nom2` : remplace tout de suite le placeholder `agents:` de
  l'orchestrateur par ces noms de subagents Copilot ; sans cette option, le placeholder
  est laissé pour que le prompt `/truthloop-install` le renseigne.
- `--force` : remplace les fichiers déjà installés (agents, instructions, prompt, schémas,
  fumée) ; `truthloop.yaml` n'est en revanche jamais écrasé.

La commande écrit dans le dépôt cible : `.github/agents/truthloop-orchestrator.agent.md`,
`.github/agents/truthloop-judge.agent.md`,
`.github/instructions/truthloop-contract.instructions.md`,
`.github/prompts/truthloop-install.prompt.md`, `.github/truthloop/schemas/*.schema.json`,
`.github/truthloop/smoke/{graph.json, truthloop.yaml}`, `.github/truthloop/ACCEPTANCE.md`,
ainsi que `truthloop.yaml` et `runs/smoke/` à la racine. Elle imprime une ligne par fichier
(`créé` / `conservé` / `remplacé`) et est idempotente : relancée sans `--force`, elle laisse
l'arbre identique. Une installation interrompue en cours de route (erreur, Ctrl-C) peut
laisser des fichiers partiellement écrits ; relancer simplement la commande (avec
`--force` si l'on veut aussi remplacer les fichiers déjà en place) répare l'arbre, car
chaque fichier est traité indépendamment et signalé `créé` / `conservé` / `remplacé`.

Dans le dépôt cible, le prompt `/truthloop-install` termine le câblage : il inventorie les
agents `.github/agents/*.agent.md`, identifie les retrievers (accès au dossier de
connaissance ou au graphe), remplit le placeholder de l'orchestrateur avec les noms
confirmés, ajoute le renvoi vers le contrat dans chaque retriever, puis lance le test de
fumée (`truthloop --version` puis `truthloop verify` sur le graphe de fumée).

Principe d'exécution une fois câblé : l'orchestrateur délègue la recherche à chaque
retriever puis assemble leurs fragments en `answer.json` / `evidence.json` ; le juge
évalue chaque claim, écrit `judge.json` et invoque `truthloop verify` ; le harness Python
décide (`release` / `repair` / `escalate` / `invalid`) et fournit un `repair_plan` que
l'orchestrateur applique jusqu'à publication ou escalade, dans la limite de
`loop.max_iterations` itérations.

Vérification manuelle : dérouler `.github/truthloop/ACCEPTANCE.md` dans le dépôt cible une
fois le câblage terminé. Détails complets (architecture, gabarits, placeholders,
protocoles des agents, contrat des retrievers) : spécification
`docs/superpowers/specs/2026-09-09-truthloop-phase2-copilot-design.md`.
