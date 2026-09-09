"""Command-line entry point (spec §8.2): init, verify, schema export, trace."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

from rich.console import Console

from truthloop import __version__
from truthloop.config import DEFAULT_CONFIG_YAML, ConfigError, load_config, resolve_path
from truthloop.contracts.schemas import export_schemas
from truthloop.engine import EXIT_CODES, evaluate
from truthloop.integration.installer import InstallError, install_copilot, parse_knowledge
from truthloop.knowledge import KnowledgeError
from truthloop.knowledge.factory import open_knowledge
from truthloop.render import render_trace, render_verdict
from truthloop.runs import RunDir, RunError

Handler = Callable[[argparse.Namespace, Console], int]


class _Parser(argparse.ArgumentParser):
    """Exit 1 (not argparse's default 2) so CLI errors match runtime errors."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        sys.stderr.write(f"erreur : {message}\n")
        sys.exit(1)


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("doit être un entier ≥ 1") from None
    if number < 1:
        raise argparse.ArgumentTypeError("doit être un entier ≥ 1")
    return number


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler = args.handler
    console = Console(soft_wrap=True, emoji=False, highlight=False)
    try:
        return handler(args, console)
    except (RunError, ConfigError, KnowledgeError, InstallError, OSError, ValueError) as exc:
        Console(stderr=True, soft_wrap=True, emoji=False, highlight=False).print(
            f"erreur : {exc}", markup=False, style="red"
        )
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="truthloop", description="Harness d'évaluation déterministe.")
    parser.add_argument("--version", action="version", version=f"truthloop {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    init = subparsers.add_parser(
        "init", help="crée truthloop.yaml, runs/, golden/, reports/ et schemas/"
    )
    init.add_argument("--config", type=Path, default=Path("truthloop.yaml"))
    init.set_defaults(handler=cmd_init)

    verify = subparsers.add_parser("verify", help="évalue une itération et écrit verdict.json")
    verify.add_argument("--run", type=Path, required=True)
    verify.add_argument("--iteration", type=_positive_int, default=None)
    verify.add_argument("--config", type=Path, default=Path("truthloop.yaml"))
    verify.add_argument("--json", action="store_true", dest="as_json")
    verify.set_defaults(handler=cmd_verify)

    schema = subparsers.add_parser("schema", help="outils sur les schémas JSON")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True, parser_class=_Parser)
    export = schema_sub.add_parser("export", help="écrit les JSON Schema des contrats")
    export.add_argument("--out", type=Path, default=Path("schemas"))
    export.set_defaults(handler=cmd_schema_export)

    trace = subparsers.add_parser("trace", help="historique des itérations d'un run")
    trace.add_argument("--run", type=Path, required=True)
    trace.add_argument("--json", action="store_true", dest="as_json")
    trace.set_defaults(handler=cmd_trace)

    install = subparsers.add_parser(
        "install-copilot", help="installe le kit Copilot dans un dépôt cible"
    )
    install.add_argument("--target", type=Path, required=True, help="dossier du dépôt cible")
    install.add_argument(
        "--knowledge", default=None, help="kind:chemin, ex. sqlite:knowledge/magic.db"
    )
    install.add_argument(
        "--retrievers", default="", help="noms des agents retrievers, séparés par des virgules"
    )
    install.add_argument(
        "--force",
        action="store_true",
        help="réécrit les fichiers du kit (jamais truthloop.yaml)",
    )
    install.set_defaults(handler=cmd_install_copilot)
    return parser


def cmd_init(args: argparse.Namespace, console: Console) -> int:
    config_path: Path = args.config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
        console.print(f"créé : {config_path}", markup=False)
    else:
        console.print(f"conservé : {config_path}", markup=False)
    config = load_config(config_path)
    for relative in (config.paths.runs, config.paths.golden, config.paths.reports):
        resolve_path(config_path, relative).mkdir(parents=True, exist_ok=True)
    schemas_dir = resolve_path(config_path, "schemas")
    written = export_schemas(schemas_dir)
    console.print(f"{len(written)} schémas exportés dans {schemas_dir}", markup=False)
    console.print("Prochaine étape : renseigner knowledge.path dans truthloop.yaml.")
    return 0


def cmd_verify(args: argparse.Namespace, console: Console) -> int:
    config_path: Path = args.config
    config = load_config(config_path)
    knowledge = open_knowledge(
        config.knowledge.kind,
        resolve_path(config_path, config.knowledge.path),
        config.knowledge.queries,
    )
    verdict = evaluate(RunDir(args.run), config, knowledge, iteration=args.iteration)
    if args.as_json:
        sys.stdout.write(verdict.model_dump_json(indent=2) + "\n")
    else:
        render_verdict(verdict, console)
    return EXIT_CODES[verdict.decision]


def cmd_schema_export(args: argparse.Namespace, console: Console) -> int:
    written = export_schemas(args.out)
    console.print(f"{len(written)} schémas exportés dans {args.out}", markup=False)
    return 0


def cmd_trace(args: argparse.Namespace, console: Console) -> int:
    run = RunDir(args.run)
    run.load_question()
    rows = run.history()
    if args.as_json:
        sys.stdout.write(
            json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2) + "\n"
        )
    else:
        render_trace(rows, console)
    return 0


def cmd_install_copilot(args: argparse.Namespace, console: Console) -> int:
    knowledge = parse_knowledge(args.knowledge) if args.knowledge else None
    retrievers = [name.strip() for name in str(args.retrievers).split(",") if name.strip()]
    target = args.target.resolve()
    results = install_copilot(args.target, knowledge, retrievers, force=args.force)
    console.print(f"Installation dans {target} :", markup=False)
    config_conserved = False
    orchestrator_conserved = False
    for result in results:
        relative = result.path.relative_to(target)
        console.print(f"{result.status} : {relative}", markup=False)
        if relative == Path("truthloop.yaml") and result.status == "conservé":
            config_conserved = True
        if relative.name == "truthloop-orchestrator.agent.md" and result.status == "conservé":
            orchestrator_conserved = True
    if args.knowledge and config_conserved:
        console.print("truthloop.yaml existant conservé : --knowledge ignoré", markup=False)
    if retrievers and orchestrator_conserved:
        console.print(
            "orchestrateur existant conservé : --retrievers ignoré (utiliser --force)", markup=False
        )
    console.print(
        "Étapes suivantes : ouvrir le dépôt cible dans VS Code, lancer le prompt /truthloop-install,",
        markup=False,
    )
    console.print("puis dérouler .github/truthloop/ACCEPTANCE.md.", markup=False)
    return 0
