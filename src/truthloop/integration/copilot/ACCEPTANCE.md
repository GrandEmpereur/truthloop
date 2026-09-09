# truthloop — checklist d'acceptation de l'intégration Copilot

À dérouler à la main dans ce dépôt, après `/truthloop-install`. Le harness s'exécute avec
`uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop …` ; `uv` doit être sur le PATH du
terminal intégré (installation : https://docs.astral.sh/uv/).

- [ ] `/truthloop-install` a listé les retrievers, remplacé le placeholder de l'orchestrateur,
      et le test de fumée (graphe de fumée) a rendu `repair` avec deux actions
      `retrieve_entities`.
- [ ] Avec l'agent `truthloop-orchestrator`, une question d'impact sur un programme connu
      produit `runs/<id>/question.json`, `iter-01/{answer,evidence,judge,verdict}.json` et
      `trace.jsonl`.
- [ ] La boucle atteint `release` en au plus {{MAX_ITERATIONS}} itérations et la réponse
      affiche « Score truthloop : … ».
- [ ] Une question sur un programme inexistant donne un verdict avec `UNKNOWN_PIVOT` et une
      action `fix_question` ; l'orchestrateur propose le handoff dès la première itération.
- [ ] Après suppression de `iter-01/judge.json` et `truthloop verify --run runs/<id>
      --iteration 1` à la main : finding `JUDGE_MISSING`, plafond 85, action `run_judge`.
- [ ] Deux `truthloop verify` successifs sur la même itération donnent un `verdict.json`
      identique hors `provenance.generated_at`.
- [ ] `truthloop trace --run runs/<id>` liste toutes les itérations avec score et décision.
