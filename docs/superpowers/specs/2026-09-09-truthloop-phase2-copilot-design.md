# truthloop phase 2 — Intégration Copilot : spécification de design

Date : 2026-09-09
Statut : approuvé après deux relectures (v3), en attente de relecture utilisateur
Dépend de : `2026-09-08-truthloop-design.md` (phase 1, livrée sur `feat/truthloop-phase1`)

## 1. Objectif

Brancher le harness `truthloop` (phase 1) sur le workflow GitHub Copilot du dépôt Magic XPA
sans modifier le contenu des agents retrievers existants. À la fin de la phase 2, un
utilisateur ouvre le dépôt Magic dans VS Code, choisit l'agent `truthloop-orchestrator`, pose
une question d'architecture ou d'impact, et obtient soit une réponse publiée avec son score,
soit une escalade explicite, après au plus `max_iterations` boucles `verify → repair`.

## 2. Contraintes reprises de la phase 1

- Copilot Chat est le seul LLM ; le harness Python reste déterministe et hors réseau.
- Pas de MCP, pas de hooks, pas de GitHub CLI. Ponts autorisés : fichiers et terminal intégré.
- Les agents custom vivent dans `.github/agents/` du **dépôt Magic**, pas dans ce dépôt.
- Les retrievers existants (plusieurs agents s'appuyant sur un dossier de connaissance) ne sont
  pas réécrits : ils reçoivent un contrat et une ligne de renvoi vers ce contrat.
- Les noms des retrievers ne sont pas connus à l'avance : le câblage est confié à Copilot via un
  prompt d'installation, ou fourni en option de la commande d'installation.

## 3. Architecture

```
dépôt truthloop (ce dépôt)                       dépôt Magic (workspace VS Code)
src/truthloop/integration/copilot/  ──install──▶  .github/agents/truthloop-orchestrator.agent.md
  agents/*.agent.md (gabarits)                    .github/agents/truthloop-judge.agent.md
  instructions/*.md                               .github/instructions/truthloop-contract.instructions.md
  prompts/truthloop-install.prompt.md             .github/prompts/truthloop-install.prompt.md
  smoke/{graph.json, truthloop.yaml, run/…}       .github/truthloop/schemas/*.schema.json
  ACCEPTANCE.md                                   .github/truthloop/smoke/{graph.json, truthloop.yaml}
                                                  .github/truthloop/ACCEPTANCE.md
                                                  truthloop.yaml          runs/smoke/   runs/.gitkeep
```

Deux temps :

1. **Installation déterministe** : `truthloop install-copilot` copie le kit, substitue les
   placeholders, écrit la configuration et les schémas. Aucun LLM.
2. **Câblage assisté** : dans le dépôt Magic, l'utilisateur lance le prompt file
   `/truthloop-install` ; Copilot inventorie `.github/agents/*.agent.md`, identifie les
   retrievers, remplit `agents:` de l'orchestrateur, ajoute la ligne de renvoi au contrat dans
   chaque retriever, et exécute le test de fumée.

À l'usage, les agents appellent le harness par
`uv run --project "<TRUTHLOOP_PROJECT>" truthloop …` : aucune installation globale, le chemin
est fixé à l'installation. `uv` doit être sur le PATH du terminal intégré. Le chemin est écrit
par l'installateur sous forme absolue, résolue (`Path.resolve()`), avec des `/` (accepté par uv
sous Windows) et sans séparateur final, pour rester valide entre guillemets sous cmd et
PowerShell.

## 4. Kit livré (`src/truthloop/integration/copilot/`)

Le kit est un sous-paquet Python (`truthloop.integration.copilot`, avec `__init__.py`) pour
être localisé par `importlib.resources` quel que soit le mode d'installation.

| Fichier | Rôle |
|---|---|
| `agents/truthloop-orchestrator.agent.md` | Gabarit de l'orchestrateur (§5). |
| `agents/truthloop-judge.agent.md` | Gabarit du juge (§6). |
| `instructions/truthloop-contract.instructions.md` | Contrat `answer.json` / `evidence.json` pour les retrievers (§7). |
| `prompts/truthloop-install.prompt.md` | Prompt de câblage exécuté par Copilot dans le dépôt Magic (§8). |
| `smoke/graph.json`, `smoke/truthloop.yaml`, `smoke/run/…` | Graphe de fixture de la phase 1, configuration `kind: files` pointant sur `graph.json` (chemin relatif au fichier de config), et le run d'exemple (question, answer, evidence, judge des échantillons de phase 1). Le test de fumée s'exécute **contre ce graphe**, pas contre la base Magic. |
| `ACCEPTANCE.md` | Checklist d'acceptation manuelle (§10). |

Placeholders, tous de la forme `{{NOM}}`, substitués par l'installateur :

| Placeholder | Valeur |
|---|---|
| `{{TRUTHLOOP_PROJECT}}` | Chemin absolu de ce dépôt (celui de `pyproject.toml`), résolu par l'installateur. |
| `{{KNOWLEDGE_KIND}}` / `{{KNOWLEDGE_PATH}}` | Depuis `--knowledge kind:path` ; n'apparaissent que dans le `truthloop.yaml` écrit à la racine du dépôt cible (dérivé de `DEFAULT_CONFIG_YAML`, mêmes poids, plafonds et seuils). `smoke/truthloop.yaml` est fixe (`kind: files`, `path: graph.json`, mêmes valeurs par défaut : condition du score 69.3 attendu). |
| `{{RETRIEVER_AGENTS}}` | Dans le gabarit, l'entrée est **entre quotes** : `agents: ['truthloop-judge', '{{RETRIEVER_AGENTS}}']`, YAML valide avant substitution. `--retrievers a,b` remplace le token quoté `'{{RETRIEVER_AGENTS}}'` par `'a', 'b'` (noms tels quels, séparés par `, `, chacun entre quotes simples). Sans `--retrievers`, le token quoté est conservé pour que le prompt d'installation le remplace ; VS Code voit alors un subagent inexistant, ce que l'orchestrateur détecte (§11). |
| `{{MAX_ITERATIONS}}` | `loop.max_iterations` de la configuration effective : celle écrite par l'installateur, ou celle lue depuis le `truthloop.yaml` conservé. |

Un test vérifie qu'après installation avec `--retrievers`, aucun `{{` ne subsiste dans les
fichiers écrits, et qu'avec `--retrievers` absent, seul `{{RETRIEVER_AGENTS}}` subsiste.

## 5. Agent orchestrateur

Frontmatter :

```yaml
---
name: truthloop-orchestrator
description: Répond aux questions d'architecture et d'impact Magic XPA avec un score de confiance vérifié par truthloop.
tools: ['agent', 'runCommands', 'read', 'edit', 'search']
agents: ['truthloop-judge', '{{RETRIEVER_AGENTS}}']
handoffs:
  - label: Escalader à un humain
    agent: agent
    prompt: La réponse n'a pas atteint le seuil de confiance. Voici les zones d'ombre à trancher.
    send: false
---
```

Protocole (corps de l'agent, en français, numéroté) :

1. **Cadrer** : déduire de la question `intent` (`impact_analysis` | `architecture` | `feature` |
   `diagram`), `pivot_entities` (programmes / tables nommés, `id` tel qu'il apparaît dans le
   dossier de connaissance ; le harness normalise casse et séparateurs), `direction` (`callers` |
   `callees` | `both`), `depth` (1 par défaut, 2 si la question parle de « transitif »,
   « en cascade », « indirect »). Créer `runs/<id>/question.json` (schéma
   `.github/truthloop/schemas/question.schema.json`), `<id>` = `q-<AAAAMMJJ>-<3 chiffres>`.
2. **Chercher** : déléguer à chaque retriever, en subagent, une consigne **autosuffisante** :
   la question, le bloc « Consigne à copier » du contrat (§7, règles + format du fragment) et
   les entités déjà connues. Le contrat n'est donc pas lu par le retriever, il est inliné :
   un retriever sans outil `read` fonctionne quand même. Exiger en retour un fragment (§7).
3. **Assembler** : fusionner les fragments dans `runs/<id>/iter-NN/answer.json` (entités
   dédoublonnées sur `(type, id)`, claims renumérotées `c1…` dans l'ordre des retrievers,
   `producer` = `"truthloop-orchestrator"`, `final_text` rédigé par l'orchestrateur à partir
   des claims : le fragment ne le porte pas) et `evidence.json` (chunks renumérotés `ev-1…`
   dans le même ordre, citations réécrites en conséquence). `iteration` et `question_id`
   cohérents. Un retriever qui ne renvoie pas de bloc JSON exploitable est relancé une fois
   avec la même consigne ; au second échec, l'assemblage se fait avec les autres fragments (le
   harness produira `NO_CLAIMS` ou `fix_contract` le cas échéant).
4. **Juger** : invoquer `truthloop-judge` en subagent avec le chemin du run et le numéro
   d'itération. Lire sa réponse : score, décision, `summary_for_agent`, chemin du verdict. Si
   la réponse n'a pas la forme attendue (§6), lire directement `runs/<id>/iter-NN/verdict.json`
   (`score`, `decision`, `repair_plan.summary_for_agent`) ; si ce fichier n'existe pas,
   arrêter avec le message du juge.
5. **Décider** :
   - `release` → rédiger la réponse finale à partir de `final_text`, en tête : « Score
     truthloop : NN / seuil » et le chemin du verdict ; lister les `declared_gaps`.
   - `repair` → lire `repair_plan.actions` dans `verdict.json`. Si la première action est
     `fix_question` (pivot inconnu du graphe), **court-circuiter** : ne pas itérer, proposer le
     handoff « Escalader à un humain » en demandant de reformuler le pivot (une question par
     run, `question.json` n'est jamais modifié). Sinon, pour chaque action dans l'ordre de
     `priority` : `retrieve_entities` → nouvelle consigne au retriever concerné (graphe ou
     documentation selon `queries.graph` / `queries.rag`) ; `verify_claim` → demander une
     évidence ou retirer la claim ; `write_claims` → rédiger des claims citées pour les entités
     présentes ; `improve_answer` → reformuler selon `instruction` ; `run_judge` → réinvoquer
     le juge ; `fix_contract` → corriger les erreurs listées. Créer `iter-NN+1/` et reprendre
     en 3.
   - `escalate` → proposer le handoff avec les findings ouverts et `summary_for_agent`.
6. **Règles dures** : jamais de réponse publiée sans décision `release` ; jamais de
   modification manuelle de `verdict.json` ; au plus `{{MAX_ITERATIONS}}` itérations ; toute
   commande `uv run …` qui sort avec le code 1 arrête la boucle avec le message d'erreur.

## 6. Agent juge

Frontmatter : `name: truthloop-judge`, `user-invocable: false`,
`tools: ['runCommands', 'read', 'edit']`.

Protocole :

1. Lire `runs/<id>/question.json`, `iter-NN/answer.json`, `iter-NN/evidence.json`.
2. Pour chaque claim, dans l'ordre : chercher dans les chunks cités les éléments factuels de
   la claim et attribuer `supported` (tous les éléments sont écrits dans un chunk cité),
   `partially` (une partie seulement), `unsupported` (aucun chunk cité ne l'étaye),
   `contradicted` (un chunk cité affirme le contraire). `rationale` : une phrase citant l'id du
   chunk décisif. Les entités et relations ne sont pas jugées ici : c'est le rôle du graphe.
3. `relevance` (la réponse répond-elle à la question posée : 1 oui, 0.5 partiellement, 0 non)
   et `completeness` (couvre-t-elle tous les aspects demandés : mêmes ancrages). `notes` :
   une phrase sur le manque principal, réutilisée par le harness dans `improve_answer`.
4. Écrire `iter-NN/judge.json` (schéma `judge.schema.json`, `question_id` et `iteration`
   recopiés, `judge_model` = `"copilot-chat"`).
5. Exécuter `uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop verify --run "runs/<id>"
   --iteration NN --json` depuis la racine du dépôt ; ne pas modifier `answer.json`. Lire dans
   le JSON imprimé : `score`, `decision`, `repair_plan.summary_for_agent`.
6. Répondre **uniquement** par le bloc :

   ```
   score: <score>
   decision: <release|repair|escalate|invalid>
   verdict: runs/<id>/iter-NN/verdict.json
   summary: <summary_for_agent>
   ```

   Si la commande sort avec le code 1, répondre `decision: error` suivi du message.

## 7. Contrat pour les retrievers

`truthloop-contract.instructions.md` (frontmatter `description` seulement ; lu explicitement par
chemin, pas par `applyTo`) contient :

- le rôle des quatre fichiers et qui les écrit (retrievers : fragments d'`answer` /
  `evidence` ; orchestrateur : assemblage ; juge : `judge.json` ; harness : `verdict.json`) ;
- les règles : identifiants exacts du dossier de connaissance (le harness normalise casse et
  séparateurs, mais n'invente jamais), chaque entité d'une claim déclarée dans `entities`,
  chaque citation vers un chunk fourni, relation optionnelle (`calls` / `called_by` /
  `reads` / `writes`), abstention explicite pour ce qui n'a pas été trouvé, `confidence_self`
  honnête ;
- le **format du fragment** renvoyé par un retriever : un unique bloc ```json contenant
  `{"entities": [...], "claims": [...], "chunks": [...], "abstentions": [...]}` où `entities`,
  `claims`, `abstentions` suivent le schéma `answer.json` et `chunks` le schéma
  `evidence.json` ; ids locaux (`c1…`, `ev-1…`) : l'orchestrateur renumérote ;
- une section « Consigne à copier » : le bloc de règles + format, prêt à être inliné par
  l'orchestrateur dans chaque délégation (§5 étape 2) ;
- un exemple complet de fragment et l'`answer.json` / `evidence.json` assemblés correspondants
  (valides contre les schémas : testé) ;
- le renvoi aux schémas `.github/truthloop/schemas/`.

## 8. Prompt d'installation (`.github/prompts/truthloop-install.prompt.md`)

Frontmatter `name: truthloop-install`, `tools: ['read', 'edit', 'search', 'runCommands']`.
Étapes demandées à Copilot :

1. Lister `.github/agents/*.agent.md` ; classer chaque agent : retriever (accède au dossier de
   connaissance / graphe / documentation), autre ; noter pour chaque retriever s'il dispose
   des outils `read` et `search` (information, pas bloquant : la consigne est inlinée).
   Présenter la liste et demander confirmation.
2. Remplacer le token `'{{RETRIEVER_AGENTS}}'` dans `truthloop-orchestrator.agent.md` par la
   liste confirmée (`'nom1', 'nom2'`, noms exacts, sensibles à la casse).
3. Dans chaque retriever confirmé, ajouter en fin de corps la ligne : « Quand la consigne
   mentionne truthloop, respecter `.github/instructions/truthloop-contract.instructions.md`. »
   Ne rien modifier d'autre.
4. Test de fumée : `uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop --version`, puis
   `uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop verify --run "runs/smoke" --config
   ".github/truthloop/smoke/truthloop.yaml" --json` (le graphe de fumée, pas la base Magic) :
   attendu code 2, `decision: repair`, deux actions `retrieve_entities`. Rapporter le résultat.
5. Rappeler la checklist `.github/truthloop/ACCEPTANCE.md`.

## 9. Commande `truthloop install-copilot`

```
truthloop install-copilot --target <dépôt Magic> --knowledge sqlite:<chemin>|files:<chemin>
                          [--retrievers nom1,nom2] [--force]
```

- Refuse (code 1) si `--target` n'est pas un dossier ou si `--knowledge` est mal formé
  (`kind` ∉ {`sqlite`, `files`} ou chemin vide) ; `--knowledge` est optionnel seulement si
  `<target>/truthloop.yaml` existe déjà (il est alors lu pour `{{MAX_ITERATIONS}}`).
- Le chemin de `--knowledge` est écrit tel quel dans `truthloop.yaml` : absolu s'il est
  absolu, sinon relatif à `<target>` (cohérent avec `resolve_path`, qui résout par rapport au
  fichier de configuration). Un chemin relatif est conseillé pour un dépôt partagé.
- Écrit les fichiers du §3 ; `truthloop.yaml` n'est jamais écrasé (message « conservé ») ;
  les autres fichiers (agents, instructions, prompt, schémas, smoke, `runs/smoke/`) ne sont
  écrasés qu'avec `--force`, sinon « conservé ».
- Sortie : une ligne par fichier (`créé` / `conservé` / `remplacé`), puis les deux étapes
  suivantes (lancer `/truthloop-install` dans Copilot, dérouler `ACCEPTANCE.md`). Code 0 dans
  tous ces cas, y compris quand tout est « conservé ».
- Idempotente : deux exécutions successives sans `--force` laissent l'arbre identique. Avec
  `--force`, `runs/smoke/` est supprimé puis recréé (les résidus d'un test de fumée,
  `iter-01/verdict.json` et `trace.jsonl`, disparaissent) ; le test d'idempotence compare
  l'arbre après deux installations sans test de fumée entre les deux.

## 10. Checklist d'acceptation (`ACCEPTANCE.md`)

Déroulée à la main dans le dépôt Magic, sans outillage :

1. `/truthloop-install` a listé les retrievers et le test de fumée (graphe de fumée) a rendu `repair` avec deux actions `retrieve_entities`.
2. Question d'impact sur un programme connu avec `truthloop-orchestrator` : `runs/<id>/` contient
   `question.json`, `iter-01/{answer,evidence,judge,verdict}.json`, `trace.jsonl`.
3. La boucle atteint `release` en au plus trois itérations, et la réponse affiche le score.
4. Question sur un programme inexistant : verdict avec `UNKNOWN_PIVOT` et action
   `fix_question`, l'orchestrateur court-circuite dès la première itération et propose le
   handoff en demandant de reformuler le pivot.
5. Suppression de `judge.json` puis `truthloop verify` à la main : `JUDGE_MISSING`, plafond 85.
6. Deux `verify` successifs sur la même itération : `verdict.json` identique hors `generated_at`.

## 11. Erreurs

| Situation | Comportement |
|---|---|
| `uv` absent du PATH du terminal Copilot | L'agent rapporte l'erreur brute et s'arrête ; `ACCEPTANCE.md` documente l'installation d'uv. |
| Retriever qui renvoie du texte libre (pas de bloc JSON) | L'orchestrateur relance une fois la même consigne ; au second échec, il assemble avec les autres fragments et laisse le harness produire `NO_CLAIMS` / `fix_contract`. |
| Le juge ne renvoie pas le bloc attendu | L'orchestrateur lit `verdict.json` directement ; s'il n'existe pas, arrêt avec le message du juge. |
| Placeholder `{{RETRIEVER_AGENTS}}` non remplacé | L'orchestrateur ne trouve pas les subagents : son corps commence par vérifier l'absence de `{{` dans sa propre configuration et renvoie vers `/truthloop-install`. |
| Chemin `{{TRUTHLOOP_PROJECT}}` déplacé | `uv run --project` échoue (code ≠ 0) ; message d'erreur remonté tel quel, relancer `install-copilot --force`. |

## 12. Tests (Python)

- `install-copilot` : arbre attendu créé, placeholders substitués, `{{RETRIEVER_AGENTS}}` conservé
  sans `--retrievers`, `truthloop.yaml` jamais écrasé, `--force` requis pour les autres
  fichiers, idempotence (empreinte de l'arbre identique), codes retour.
- Frontmatters des gabarits : YAML valide (parseur strict) **avant** substitution (sans
  `--retrievers`) et après ; champs `name`, `tools`, `agents` / `user-invocable` présents et
  cohérents avec §5–§6 ; `{{TRUTHLOOP_PROJECT}}` substitué par un chemin absolu en `/` sans
  séparateur final.
- Exemple du contrat : le fragment et l'`answer.json` / `evidence.json` extraits du markdown
  valident contre `Answer` / `Evidence` ; `runs/smoke` installé, évalué avec
  `.github/truthloop/smoke/truthloop.yaml`, donne `repair` avec deux actions
  `retrieve_entities` via `evaluate`.
- Schémas installés identiques à `export_schemas`.
- Couverture globale ≥ 85 % maintenue.

## 13. Hors périmètre

- Phase 3 (golden set, `eval`, `calibrate`, fiches Markdown).
- Réécriture des retrievers, choix des modèles Copilot, agents cloud.
- Évaluation automatique du comportement des agents (impossible sans LLM côté Python) : couverte
  par la checklist d'acceptation.

## 14. Décisions

| Décision | Alternative écartée | Raison |
|---|---|---|
| Kit installé par commande + câblage par prompt | Documentation manuelle | Le déterministe est automatisé, seul le câblage des noms demande de la compréhension. |
| `uv run --project <chemin>` | `uv tool install` | Aucune installation globale à faire valider ; le chemin est fixé à l'installation et vérifiable. |
| Le juge lance `verify` | L'orchestrateur lance `verify` | Le contexte de l'orchestrateur reste court ; le juge renvoie un bloc de cinq lignes. |
| Contrat lu par chemin | Instructions `applyTo` | Les retrievers travaillent sur des fichiers variés ; un glob serait soit trop large, soit inopérant. |
