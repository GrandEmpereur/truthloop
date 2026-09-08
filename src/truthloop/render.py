"""Rich rendering for the terminal (spec §8.2)."""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from truthloop.contracts.verdict import Verdict, finding_target
from truthloop.runs import TraceRow


def render_verdict(verdict: Verdict, console: Console) -> None:
    console.print(
        f"[bold]{escape(verdict.question_id)}[/bold] itération {verdict.iteration} : "
        f"score [bold]{verdict.score:.1f}[/bold] / seuil {verdict.threshold:.0f} "
        f"→ [bold]{verdict.decision}[/bold]"
    )
    components = Table(title="Composantes")
    components.add_column("composante")
    components.add_column("valeur", justify="right")
    components.add_column("poids", justify="right")
    components.add_column("applicable")
    for name, component in verdict.components.items():
        value = "n/a" if component.value is None else f"{component.value:.2f}"
        components.add_row(
            name, value, f"{component.weight:.2f}", "oui" if component.applicable else "non"
        )
    console.print(components)
    if verdict.caps_applied:
        console.print(
            "Plafonds : " + ", ".join(f"{c.name} ({c.value})" for c in verdict.caps_applied)
        )
    if verdict.findings:
        findings = Table(title="Findings")
        findings.add_column("code")
        findings.add_column("sévérité")
        findings.add_column("cible")
        findings.add_column("détail")
        for finding in verdict.findings:
            target = finding_target(finding)
            findings.add_row(finding.code, finding.severity, escape(target), escape(finding.detail))
        console.print(findings)
    if verdict.repair_plan.actions:
        actions = Table(title="Plan de réparation")
        actions.add_column("#", justify="right")
        actions.add_column("action")
        actions.add_column("gain", justify="right")
        actions.add_column("instruction")
        for action in verdict.repair_plan.actions:
            actions.add_row(
                str(action.priority),
                action.kind,
                f"{action.expected_gain:.1f}",
                escape(action.instruction),
            )
        console.print(actions)
        console.print(f"[italic]{escape(verdict.repair_plan.summary_for_agent)}[/italic]")


def render_trace(rows: Sequence[TraceRow], console: Console) -> None:
    table = Table(title="Trace")
    table.add_column("itération", justify="right")
    table.add_column("score", justify="right")
    table.add_column("décision")
    table.add_column("findings ouverts", justify="right")
    table.add_column("résolus", justify="right")
    for row in rows:
        table.add_row(
            str(row.iteration),
            "n/a" if row.score is None else f"{row.score:.1f}",
            row.decision if row.decision is not None else "non évaluée",
            str(row.open_findings),
            str(row.resolved_findings),
        )
    console.print(table)
