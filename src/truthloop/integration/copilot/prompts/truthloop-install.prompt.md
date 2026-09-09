---
name: truthloop-install
description: "Câble les agents truthloop sur les retrievers existants de ce dépôt et lance le test de fumée."
tools: ['read', 'edit', 'search', 'runCommands']
---
Tu installes truthloop dans ce dépôt. Le kit a déjà été copié par
`truthloop install-copilot` ; il te reste le câblage et le test de fumée. Procède dans l'ordre
et demande confirmation avant l'étape 2.

1. **Inventaire.** Liste `.github/agents/*.agent.md`. Pour chaque agent, lis son frontmatter
   et son corps, et classe-le dans une de quatre catégories :
   - *retriever graphe* : il accède au graphe des programmes (export `program-graph/`, base
     SQLite, `graph.json`) ;
   - *retriever documentation* : il accède à la documentation, aux release notes, aux cartes de
     sources (`kg/`, `docs/`, `source_map.json` ou équivalents) ;
   - *expert de domaine* : il interprète et explique, mais ne va pas chercher de faits dans un
     dossier de connaissance ;
   - *autre*.
   Vérifie pour chacun les outils réels (`read`, `search`, `runCommands`) et les chemins qu'il
   lit effectivement, pas seulement ce que son nom suggère. Seuls les retrievers (graphe ou
   documentation) capables de renvoyer le fragment JSON du contrat sont câblés ; un expert de
   domaine n'est ajouté que s'il sait produire des chunks avec une source citée. Présente un
   tableau nom / catégorie / outils / chemins et demande confirmation de la liste à câbler.
2. **Câblage de l'orchestrateur.** Dans `.github/agents/truthloop-orchestrator.agent.md`,
   remplace le token `'{{RETRIEVER_AGENTS}}'` (avec ses quotes) par les noms confirmés,
   chacun entre quotes simples et séparés par une virgule et une espace, par exemple
   `'rag-agent', 'graph-agent'`. Noms exacts, sensibles à la casse. Ne touche à rien d'autre
   dans ce fichier. Si le token est absent (installation déjà câblée), compare la liste
   `agents:` existante aux noms confirmés : si elle est identique, ne touche pas au fichier ;
   sinon remplace uniquement les noms qui suivent `'truthloop-judge'`, sans changer le reste de
   la ligne.
3. **Renvoi au contrat.** À la fin du corps de chaque retriever confirmé, ajoute la ligne :
   « Quand la consigne mentionne truthloop, respecte le format de fragment de
   `.github/instructions/truthloop-contract.instructions.md`. » Ne modifie rien d'autre.
   Si la ligne y figure déjà, ne l'ajoute pas une seconde fois.
4. **Test de fumée.** Depuis la racine du dépôt, exécute :
   `uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop --version`
   puis
   `uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop verify --run "runs/smoke" --config ".github/truthloop/smoke/truthloop.yaml" --json`.
   Attendu : code de retour 2, `"decision": "repair"`, deux actions `retrieve_entities`.
   Ce test utilise le graphe de fumée, pas la base de connaissance du dépôt. Rapporte le
   résultat exact ; si `uv` est introuvable, indique-le.
5. **Première question.** Explique que la boucle réelle ne se lance qu'en **sélectionnant
   l'agent `truthloop-orchestrator` dans la liste des agents** de Copilot Chat, puis en posant la
   question. Ne construis jamais toi-même `answer.json` / `judge.json` à partir de la base : le
   score obtenu ainsi copierait l'oracle et ne mesurerait rien.
6. **Suite.** Rappelle la checklist `.github/truthloop/ACCEPTANCE.md` et propose de commencer
   par son premier point.
