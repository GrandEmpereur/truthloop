---
description: "Contrat truthloop pour les agents retrievers : format du fragment, règles d'identifiants, citations et abstentions."
---
# Contrat truthloop pour les retrievers

Ce fichier est la référence. L'orchestrateur `truthloop-orchestrator` copie la section
« Consigne à copier » dans chaque délégation : un retriever n'a pas besoin de le lire.

## Qui écrit quoi

| Fichier | Auteur |
|---|---|
| fragment (bloc JSON renvoyé dans la réponse) | chaque retriever |
| `runs/<id>/iter-NN/answer.json`, `evidence.json` | l'orchestrateur, par assemblage des fragments |
| `runs/<id>/iter-NN/judge.json` | `truthloop-judge` |
| `runs/<id>/iter-NN/verdict.json`, `runs/<id>/trace.jsonl` | le harness (`truthloop verify`), jamais un agent |

Schémas JSON : `.github/truthloop/schemas/`.

## Consigne à copier

> Tu travailles pour truthloop. Réponds par un **unique** bloc ```json de la forme
> `{"entities": [...], "claims": [...], "chunks": [...], "abstentions": [...]}` et rien d'autre.
>
> - `entities` : chaque programme, table, document ou release que tu cites, sous la forme
>   `{"type": <program, table, doc ou release>, "id": "<identifiant exact du dossier de connaissance>"}`.
>   N'invente aucun identifiant : si tu n'es pas sûr qu'il existe, ne le cite pas.
> - `chunks` : les extraits qui prouvent ce que tu affirmes,
>   `{"id": "ev-1", "source": "<fichier ou vue du graphe>", "text": "<extrait littéral>", "score": <nombre entre 0 et 1>}`.
>   Le texte doit contenir les identifiants tels qu'ils apparaissent dans la source.
> - `claims` : une affirmation par élément de réponse,
>   `{"id": "c1", "text": "...", "entities": ["<ids cités par la claim>"], "citations": ["ev-1"],
>   "relation": {"subject": "PRG_A", "predicate": <calls, called_by, reads ou writes>, "object": "PRG_B"},
>   "confidence_self": <nombre entre 0 et 1>}`. `relation` est optionnelle. Chaque id de `entities` de la claim
>   doit figurer dans la liste `entities` globale ; chaque citation doit exister dans `chunks`.
> - `abstentions` : ce que tu n'as pas trouvé, `{"text": "...", "entities": ["<ids concernés>"]}`.
>   Une abstention honnête vaut mieux qu'une invention : elle n'est jamais pénalisée.
> - `confidence_self` : ta confiance réelle dans la claim ; un chiffre honnête, pas un
>   chiffre flatteur (le harness la compare au verdict).
> - Numérote localement (`c1`, `ev-1`, …) : l'orchestrateur renumérote.
> - Les identifiants que l'orchestrateur te transmet (issus du plan de réparation) peuvent être
>   en minuscules : cherche sans tenir compte de la casse et renvoie la forme exacte de la
>   source.

## Exemple de fragment

```json
{
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
      "citations": ["ev-1"],
      "relation": {"subject": "PRG_ORD_SAVE", "predicate": "calls", "object": "PRG_ORD_VALID"},
      "confidence_self": 0.9
    },
    {
      "id": "c2",
      "text": "PRG_ORD_SAVE écrit dans T_ORDERS.",
      "entities": ["PRG_ORD_SAVE", "T_ORDERS"],
      "citations": ["ev-2"],
      "relation": {"subject": "PRG_ORD_SAVE", "predicate": "writes", "object": "T_ORDERS"}
    }
  ],
  "chunks": [
    {"id": "ev-1", "source": "graph:calls", "text": "PRG_ORD_SAVE -> PRG_ORD_VALID (call, task 3)", "score": 0.95},
    {"id": "ev-2", "source": "graph:program_tables", "text": "PRG_ORD_SAVE writes T_ORDERS", "score": 0.9}
  ],
  "abstentions": [
    {"text": "Appelants de PRG_ORD_VALID au-delà de la profondeur 1 non explorés.", "entities": ["PRG_ORD_VALID"]}
  ]
}
```

## Assemblage par l'orchestrateur

Le fragment ci-dessus, seul, devient `answer.json` :

```json
{
  "schema_version": 1,
  "question_id": "q-20260909-001",
  "iteration": 1,
  "producer": "truthloop-orchestrator",
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
      "citations": ["ev-1"],
      "relation": {"subject": "PRG_ORD_SAVE", "predicate": "calls", "object": "PRG_ORD_VALID"},
      "confidence_self": 0.9
    },
    {
      "id": "c2",
      "text": "PRG_ORD_SAVE écrit dans T_ORDERS.",
      "entities": ["PRG_ORD_SAVE", "T_ORDERS"],
      "citations": ["ev-2"],
      "relation": {"subject": "PRG_ORD_SAVE", "predicate": "writes", "object": "T_ORDERS"}
    }
  ],
  "abstentions": [
    {"text": "Appelants de PRG_ORD_VALID au-delà de la profondeur 1 non explorés.", "entities": ["PRG_ORD_VALID"]}
  ],
  "final_text": "PRG_ORD_VALID est appelé par PRG_ORD_SAVE, qui écrit dans T_ORDERS."
}
```

et `evidence.json` :

```json
{
  "schema_version": 1,
  "question_id": "q-20260909-001",
  "iteration": 1,
  "chunks": [
    {"id": "ev-1", "source": "graph:calls", "text": "PRG_ORD_SAVE -> PRG_ORD_VALID (call, task 3)", "score": 0.95},
    {"id": "ev-2", "source": "graph:program_tables", "text": "PRG_ORD_SAVE writes T_ORDERS", "score": 0.9}
  ]
}
```

## Ce que le harness vérifie ensuite

Existence des entités dans le graphe, rappel des appelants / appelés et des tables attendus,
présence d'une évidence par claim, cohérence des relations avec le graphe, puis le verdict
sémantique du juge. Le score doit atteindre le seuil (90 par défaut) pour publier.
