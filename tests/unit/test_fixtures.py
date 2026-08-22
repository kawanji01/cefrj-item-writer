from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from tests.support import (
    FIXTURES,
    GOLDEN,
    GOLDEN_CASE_FILES,
    OFFICIAL_FORMATS,
    ROOT,
    canonical_bytes,
    load_json,
    machine_for_path,
)
from flow_control import review_semantic_problems


def indexed_files(directory: Path) -> set[str]:
    return {item["file"] for item in load_json(directory / "index.json")["cases"]}


def actual_json_files(directory: Path) -> set[str]:
    return {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*.json")
        if path != directory / "index.json"
    }


TEST_PRODUCT_CONTRACTS = (
    frozenset({"body", "target"}),
    frozenset({"violations"}),
    frozenset({"checks"}),
    frozenset({"sentence_grammar_inventory"}),
    frozenset({"machine_check_disputes"}),
    frozenset({"candidate", "machine_report"}),
    frozenset({"questions"}),
    frozenset({"action"}),
    frozenset({"check_id", "result"}),
    frozenset({"grammar_item_id", "level_source"}),
    frozenset({"code", "location"}),
    frozenset({"machine_violation_code", "location"}),
    frozenset({"accepted_question_id", "attempted_question_ids"}),
    frozenset({"config_snapshot", "final_question_ids"}),
    frozenset({"detail", "error_code", "message", "remedy"}),
    frozenset(
        {
            "actual_level",
            "code",
            "evidence",
            "expected_level",
            "location",
            "suggestion",
        }
    ),
    frozenset({"detail", "message", "remedy", "warning_code"}),
    frozenset(
        {
            "claim",
            "dispute_type",
            "evidence",
            "location",
            "machine_violation_code",
            "suggested_correction",
        }
    ),
    frozenset({"audit_format", "exit_code", "kind", "stderr_base64"}),
)
GENERATOR_PRODUCT_CONTRACTS = (
    frozenset(
        {
            "candidate",
            "constraints_snapshot",
            "machine_report",
            "readable_resources",
            "target_ref",
        }
    ),
    frozenset(
        {
            "accepted_question_id",
            "attempted_question_ids",
            "slot_question_id",
            "teacher_decision",
        }
    ),
    frozenset(
        {
            "config_snapshot",
            "created_at",
            "final_question_ids",
            "requested_count",
            "tool",
        }
    ),
)


def contract_dict_violations(
    source: str,
    filename: str,
    signatures: tuple[frozenset[str], ...],
) -> list[str]:
    tree = ast.parse(source, filename=filename)
    violations: set[str] = set()
    imported_call_aliases: dict[str, str] = {}
    imported_targets: dict[str, str] = {}
    imported_modules: dict[str, str] = {}
    function_return_containers: dict[str, dict[object, str]] = {}
    container_kind_key = object()
    local_callables = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                local_name = alias.asname or alias.name
                imported_targets[local_name] = f"{node.module}.{alias.name}"
                if node.module in {"ast", "builtins", "json"}:
                    imported_call_aliases[local_name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules[alias.asname or alias.name.split(".", 1)[0]] = (
                    alias.name
                )

    def static_call_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return imported_call_aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            owner = static_call_name(node.value)
            if node.attr == "fromkeys" and owner == "dict":
                return "dict.fromkeys"
            return node.attr
        return None

    def container_elements(
        container: dict[object, str],
    ) -> dict[object, str]:
        return {
            key: identity
            for key, identity in container.items()
            if key is not container_kind_key
        }

    def container_kind(container: dict[object, str]) -> str:
        return container.get(container_kind_key, "container-kind:unknown")

    def tagged_container(
        elements: dict[object, str], kind: str
    ) -> dict[object, str]:
        tagged = {container_kind_key: f"container-kind:{kind}"}
        tagged.update(elements)
        return tagged

    def call_identity(
        node: ast.AST,
        aliases: dict[str, str] | None = None,
        containers: dict[str, dict[object, str]] | None = None,
    ) -> str | None:
        aliases = {} if aliases is None else aliases
        containers = {} if containers is None else containers
        if isinstance(node, ast.Name):
            if node.id in aliases:
                return aliases[node.id]
            if node.id in local_callables:
                return f"{filename}:{node.id}"
            if node.id in imported_targets:
                return imported_targets[node.id]
            if node.id in imported_modules:
                return imported_modules[node.id]
            return f"{filename}:{node.id}"
        if isinstance(node, ast.Attribute):
            owner = call_identity(node.value, aliases, containers)
            if owner is None:
                return None
            if node.attr == "__call__" and (
                owner in sensitive_identities
                or owner.startswith("unresolved-sensitive:")
                or identity_terminal(owner) in known_sensitive_names
            ):
                return owner
            identity = f"{owner}.{node.attr}"
            return aliases.get(identity, identity)
        if isinstance(node, ast.IfExp):
            body = call_identity(node.body, aliases, containers)
            other = call_identity(node.orelse, aliases, containers)
            return body if body is not None and body == other else None
        if isinstance(node, ast.Subscript):
            key = (
                node.slice.value
                if isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, (int, str, bytes))
                else None
            )
            if key is None:
                key_values = static_string_values(node.slice)
                if key_values is not None and len(key_values) == 1:
                    key = next(iter(key_values))
            if key is not None and isinstance(node.value, ast.Call):
                mapping_name = static_call_name(node.value.func)
                owner: str | None = None
                if (
                    mapping_name == "next"
                    and len(node.value.args) == 1
                    and not node.value.keywords
                ):
                    values = static_iteration_values(
                        node.value.args[0], aliases, containers
                    )
                    if values:
                        return call_identity(
                            ast.Subscript(
                                value=values[0],
                                slice=ast.Constant(key),
                                ctx=ast.Load(),
                            ),
                            aliases,
                            containers,
                        )
                returned_container = function_return_containers.get(
                    call_identity(node.value.func, aliases, containers) or ""
                )
                if returned_container is not None:
                    return returned_container.get(key)
                if mapping_name in {"globals", "locals"} and not node.value.args:
                    return call_identity(
                        ast.Name(id=str(key)), aliases, containers
                    )
                if (
                    mapping_name == "vars"
                    and len(node.value.args) == 1
                    and not node.value.keywords
                ):
                    owner = call_identity(
                        node.value.args[0], aliases, containers
                    )
                if owner is not None:
                    identity = f"{owner}.{key}"
                    return aliases.get(identity, identity)
            if (
                key is not None
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "__dict__"
            ):
                owner = call_identity(
                    node.value.value, aliases, containers
                )
                if owner is not None:
                    identity = f"{owner}.{key}"
                    return aliases.get(identity, identity)
            if isinstance(node.value, ast.Name) and key is not None:
                return containers.get(node.value.id, {}).get(key)
            if isinstance(node.value, (ast.Tuple, ast.List)) and isinstance(key, int):
                index = key if key >= 0 else len(node.value.elts) + key
                if 0 <= index < len(node.value.elts):
                    return call_identity(
                        node.value.elts[index], aliases, containers
                    )
            if isinstance(node.value, ast.Dict) and key is not None:
                for dict_key, dict_value in zip(
                    node.value.keys, node.value.values, strict=True
                ):
                    if (
                        isinstance(dict_key, ast.Constant)
                        and dict_key.value == key
                    ):
                        return call_identity(dict_value, aliases, containers)
            return None
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in containers
        ):
            container = container_elements(containers[node.func.value.id])
            if node.func.attr == "pop" and not node.keywords:
                if not node.args and len(container) == 1:
                    return next(iter(container.values()))
                if len(node.args) == 1 and isinstance(
                    node.args[0], ast.Constant
                ):
                    return container.get(node.args[0].value)
        if (
            isinstance(node, ast.Call)
            and static_call_name(node.func) == "next"
            and len(node.args) == 1
            and not node.keywords
        ):
            values = static_iteration_values(
                node.args[0], aliases, containers
            )
            if values:
                identity = call_identity(values[0], aliases, containers)
                if identity is not None:
                    return identity
        if (
            isinstance(node, ast.Call)
            and static_call_name(node.func) == "getattr"
            and len(node.args) == 2
            and not node.keywords
        ):
            owner = call_identity(node.args[0], aliases, containers)
            attributes = static_string_values(node.args[1])
            if owner is not None and attributes is not None and len(attributes) == 1:
                attribute = next(iter(attributes))
                if attribute == "__call__" and (
                    owner in sensitive_identities
                    or owner.startswith("unresolved-sensitive:")
                    or identity_terminal(owner) in known_sensitive_names
                ):
                    return owner
                identity = f"{owner}.{attribute}"
                return aliases.get(identity, identity)
            if owner is not None and any(
                identity.startswith(f"{owner}.")
                for identity in sensitive_identities
            ):
                return "unresolved-sensitive:reflective-call"
        return None

    approved_contract_sources = frozenset(
        {
            "flow_control.build_config_snapshot",
            "flow_control.build_finalize_metadata",
            "flow_control.build_review_request",
            "flow_control.build_session_from_candidate",
            "flow_control.build_session_input",
            "flow_control.build_slot_outcome",
            "tests.support.finalize_metadata",
            "tests.support.review_request",
            "tests.support.review_result",
            "tests.replay.harness.flow_cli",
            "tests/generate_assets.py:official_candidates",
            "tests/generate_assets.py:run_machine",
            "tests/support.py:review_request",
            "tests/support.py:review_result",
            "tests/unit/test_flow_control.py:chk03_review_for_candidate",
        }
    )
    approved_contract_loaders = frozenset(
        {
            "tests.support.load_json",
            "tests/generate_assets.py:load_json",
            "tests/support.py:load_json",
        }
    )
    approved_contract_encoders = frozenset(
        {
            "flow_control.canonical_bytes",
            "tests.support.canonical_bytes",
            "tests/generate_assets.py:canonical_bytes",
            "tests/support.py:canonical_bytes",
        }
    )
    approved_process_sources = frozenset(
        {
            "tests.support.machine_for_path",
            "tests.support.run_cli",
            "tests/generate_assets.py:run_cli",
            "tests/support.py:machine_for_path",
            "tests/support.py:run_cli",
        }
    )
    approved_process_decoders = frozenset(
        {
            "tests.support.stderr_json",
            "tests.support.stdout_json",
            "tests/support.py:stderr_json",
            "tests/support.py:stdout_json",
        }
    )
    approved_contract_parameters = {
        ("tests/generate_assets.py", "make_golden_and_schema_assets"): frozenset(
            {"official"}
        ),
        ("tests/support.py", "review_request"): frozenset(
            {"candidate", "machine"}
        ),
        ("tests/unit/test_set.py", "finalize"): frozenset(
            {"metadata"}
        ),
    }
    approved_path_parameters = {
        ("tests/replay/harness.py", "run_scenario"): {
            "path": "canonical-path",
        },
        ("tests/support.py", "install_attempt"): {
            "candidate_source": "canonical-path",
            "set_dir": "product-path",
        },
        ("tests/support.py", "machine_for_path"): {
            "candidate_path": "approved-input-path",
        },
        ("tests/support.py", "run_final_check"): {
            "set_dir": "product-path",
        },
        ("tests/support.py", "run_incremental"): {
            "set_dir": "product-path",
        },
        ("tests/unit/test_set.py", "finalize"): {
            "set_dir": "product-path",
        },
    }
    approved_repo_path_sources = frozenset(
        {"tests/unit/test_flow_control.py:make_isolated_config_repo"}
    )
    approved_path_bindings = {
        ("tests/support.py", "install_attempt"): {
            "candidate_path": "product-path",
        },
        (
            "tests/unit/test_flow_control.py",
            "test_m8_reviewer_preflight_rejects_tampered_request_before_child_launch",
        ): {
            "request_path": "product-path",
        },
    }
    approved_origin_bindings = {
        (
            "tests/unit/test_fixtures.py",
            "test_ci_fix_01_replay_pass_reviews_have_complete_known_grammar_inventory",
        ): frozenset({"candidate"}),
        (
            "tests/unit/test_flow_control.py",
            "test_m8_chk03_semantics_accept_real_excess_for_vocab_and_grammar_limits",
        ): frozenset({"candidate"}),
    }

    def static_payload_values(
        node: ast.AST,
        known: dict[str, set[str | bytes]] | None = None,
    ) -> set[str | bytes] | None:
        known = known or {}
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            return {node.value}
        if isinstance(node, ast.Name):
            values = known.get(node.id)
            return set(values) if values is not None else None
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            values: set[str | bytes] = set()
            for element in node.elts:
                nested = static_payload_values(element, known)
                if nested is None:
                    return None
                values.update(nested)
            return values
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = static_payload_values(node.left, known)
            right = static_payload_values(node.right, known)
            if left is None or right is None:
                return None
            if any(type(prefix) is not type(suffix) for prefix in left for suffix in right):
                return None
            return {prefix + suffix for prefix in left for suffix in right}
        if isinstance(node, ast.JoinedStr):
            parts: list[set[str]] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append({value.value})
                elif isinstance(value, ast.FormattedValue):
                    nested = static_payload_values(value.value, known)
                    if nested is None or any(not isinstance(item, str) for item in nested):
                        return None
                    parts.append({item for item in nested if isinstance(item, str)})
                else:
                    return None
            combined = {""}
            for part in parts:
                combined = {prefix + suffix for prefix in combined for suffix in part}
            return combined
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
            and len(node.args) == 1
            and not node.keywords
        ):
            separators = static_payload_values(node.func.value, known)
            items = static_payload_values(node.args[0], known)
            if (
                separators is None
                or items is None
                or any(not isinstance(value, str) for value in separators | items)
            ):
                return None
            ordered_items: list[str] = []
            if isinstance(node.args[0], (ast.Tuple, ast.List)):
                for element in node.args[0].elts:
                    values = static_string_values(element, known)
                    if values is None or len(values) != 1:
                        return None
                    ordered_items.append(next(iter(values)))
            else:
                return None
            return {
                separator.join(ordered_items)
                for separator in separators
                if isinstance(separator, str)
            }
        return None

    def static_string_values(
        node: ast.AST,
        known: dict[str, set[str | bytes]] | None = None,
    ) -> set[str] | None:
        values = static_payload_values(node, known)
        if values is None or any(not isinstance(value, str) for value in values):
            return None
        return {value for value in values if isinstance(value, str)}

    def static_dict_keys(
        node: ast.AST,
        known_builders: dict[str, set[str]] | None = None,
        known_strings: dict[str, set[str | bytes]] | None = None,
    ) -> set[str] | None:
        known_builders = known_builders or {}
        known_strings = known_strings or {}
        if isinstance(node, ast.Name):
            keys = known_builders.get(node.id)
            return set(keys) if keys is not None else None
        if isinstance(node, ast.Dict):
            keys: set[str] = set()
            for key, value in zip(node.keys, node.values, strict=True):
                if key is None:
                    nested = static_dict_keys(
                        value, known_builders, known_strings
                    )
                    if nested is not None:
                        keys.update(nested)
                else:
                    values = static_string_values(key, known_strings)
                    if values is not None:
                        keys.update(values)
            return keys
        if isinstance(node, ast.DictComp):
            local_strings = dict(known_strings)
            for generator in node.generators:
                if not isinstance(generator.target, ast.Name):
                    return None
                values = static_string_values(generator.iter, local_strings)
                if values is None:
                    return None
                local_strings[generator.target.id] = values
            return static_string_values(node.key, local_strings)
        if isinstance(node, ast.Call):
            function_name = static_call_name(node.func)
            if function_name == "dict":
                keys = {
                    keyword.arg for keyword in node.keywords if keyword.arg is not None
                }
                for argument in node.args:
                    if (
                        isinstance(argument, ast.Call)
                        and isinstance(argument.func, ast.Name)
                        and argument.func.id == "zip"
                        and argument.args
                    ):
                        keys.update(
                            static_string_values(argument.args[0], known_strings)
                            or set()
                        )
                    nested = static_dict_keys(
                        argument, known_builders, known_strings
                    )
                    if nested is not None:
                        keys.update(nested)
                for keyword in node.keywords:
                    if keyword.arg is None:
                        nested = static_dict_keys(
                            keyword.value, known_builders, known_strings
                        )
                        if nested is not None:
                            keys.update(nested)
                return keys
            if function_name == "dict.fromkeys" and node.args:
                return static_string_values(node.args[0], known_strings)
            if call_identity(node.func) not in approved_contract_sources:
                keys: set[str] = set()
                parsed_any = False
                for argument in node.args:
                    payloads = static_payload_values(argument, known_strings)
                    if payloads is None:
                        continue
                    for payload in payloads:
                        values: list[object] = []
                        try:
                            values.append(json.loads(payload))
                        except (UnicodeDecodeError, ValueError):
                            pass
                        if isinstance(payload, str):
                            try:
                                values.append(ast.literal_eval(payload))
                            except (ValueError, SyntaxError):
                                pass
                        for value in values:
                            if isinstance(value, dict):
                                parsed_any = True
                                keys.update(
                                    key for key in value if isinstance(key, str)
                                )
                return keys if parsed_any else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = static_dict_keys(node.left, known_builders, known_strings)
            right = static_dict_keys(node.right, known_builders, known_strings)
            if left is None and right is None:
                return None
            return (left or set()) | (right or set())
        return None

    def record(keys: set[str], lineno: int) -> None:
        if any(required <= keys for required in signatures):
            violations.add(f"{filename}:{lineno}:contract-dict")

    def has_contract_signature(keys: set[str]) -> bool:
        return any(required <= keys for required in signatures)

    def static_path_origin(
        node: ast.AST,
        known_paths: dict[str, str],
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]] | None = None,
    ) -> str:
        def safe_relative_parts(values: set[str] | None) -> bool:
            return values is not None and all(
                not value.startswith(("/", "\\"))
                and ".." not in value.replace("\\", "/").split("/")
                for value in values
            )

        containers = {} if containers is None else containers
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                normalized = node.value.replace("\\", "/")
                if not safe_relative_parts({normalized}):
                    return "unknown-path"
                if normalized.startswith(
                    ("tests/fixtures/", "tests/golden/")
                ):
                    return "canonical-path"
                if normalized.startswith("output/"):
                    return "product-path"
                if normalized.startswith(("data/", "schemas/")):
                    return "support-path"
            return "literal"
        if isinstance(node, ast.Name):
            if node.id in known_paths:
                return known_paths[node.id]
            if node.id == "ROOT" and filename in {
                "tests/generate_assets.py",
                "tests/support.py",
            }:
                return "repo-path"
            target = call_identity(node, aliases, containers)
            if target in {
                "tests.support.FIXTURES",
                "tests.support.GOLDEN",
                "tests/support.py:FIXTURES",
                "tests/support.py:GOLDEN",
            }:
                return "canonical-path"
            if target in {
                "tests.support.ROOT",
                "tests/generate_assets.py:ROOT",
                "tests/support.py:ROOT",
            }:
                return "repo-path"
            return "unknown-path"
        if isinstance(node, ast.Attribute):
            return "unknown-path"
        if isinstance(node, ast.Subscript):
            return static_path_origin(
                node.value, known_paths, aliases, containers
            )
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            element_origins = {
                static_path_origin(
                    element.value if isinstance(element, ast.Starred) else element,
                    known_paths,
                    aliases,
                    containers,
                )
                for element in node.elts
            }
            if len(element_origins) == 1:
                return element_origins.pop()
            return "unknown-path"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parent = static_path_origin(
                node.left, known_paths, aliases, containers
            )
            parts = static_string_values(node.right)
            if not safe_relative_parts(parts):
                return "unknown-path"
            if parent in {
                "approved-input-path",
                "canonical-path",
                "product-path",
            }:
                return parent
            if parent == "support-path":
                return "support-path"
            if parent == "repo-path" and parts is not None:
                if "tests" in parts:
                    return "tests-path"
                if "output" in parts:
                    return "product-path"
                return "support-path"
            if parent == "tests-path" and parts is not None:
                if parts & {"fixtures", "golden"}:
                    return "canonical-path"
                return "tests-path"
            return "unknown-path"
        if isinstance(node, ast.Call):
            if (
                call_identity(node.func, aliases, containers)
                in approved_repo_path_sources
            ):
                return "repo-path"
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "resolve"
                and not node.args
                and not node.keywords
            ):
                return static_path_origin(
                    node.func.value, known_paths, aliases, containers
                )
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "glob",
                "rglob",
                "with_name",
            }:
                values = (
                    static_string_values(node.args[0])
                    if len(node.args) == 1 and not node.keywords
                    else None
                )
                if not safe_relative_parts(values):
                    return "unknown-path"
                return static_path_origin(
                    node.func.value, known_paths, aliases, containers
                )
            if static_call_name(node.func) in {"str", "fspath"} and node.args:
                return static_path_origin(
                    node.args[0], known_paths, aliases, containers
                )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "as_posix"
                and not node.args
                and not node.keywords
            ):
                return static_path_origin(
                    node.func.value, known_paths, aliases, containers
                )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "relative_to"
                and len(node.args) == 1
                and not node.keywords
                and static_path_origin(
                    node.args[0], known_paths, aliases, containers
                )
                == "repo-path"
            ):
                return static_path_origin(
                    node.func.value, known_paths, aliases, containers
                )
            if (
                call_identity(node.func, aliases, containers) == "pathlib.Path"
                and node.args
            ):
                values = static_string_values(node.args[0])
                if safe_relative_parts(values):
                    if all(
                        value.startswith("tests/fixtures/")
                        or value.startswith("tests/golden/")
                        for value in values
                    ):
                        return "canonical-path"
                    if all(value.startswith("output/") for value in values):
                        return "product-path"
                    if all(
                        value.startswith(("data/", "schemas/"))
                        for value in values
                    ):
                        return "support-path"
            if static_call_name(node.func) in {"list", "sorted", "tuple"} and node.args:
                return static_path_origin(
                    node.args[0], known_paths, aliases, containers
                )
        return "unknown-path"

    def expression_origin(
        node: ast.AST,
        origins: dict[str, str],
        builders: dict[str, set[str]],
        literals: dict[str, set[str | bytes]],
        paths: dict[str, str],
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]] | None = None,
    ) -> str:
        containers = {} if containers is None else containers
        if isinstance(node, ast.Name):
            return origins.get(node.id, "unknown")
        if isinstance(node, (ast.Subscript, ast.Attribute)):
            parent_origin = expression_origin(
                node.value,
                origins,
                builders,
                literals,
                paths,
                aliases,
                containers,
            )
            if isinstance(node, ast.Attribute) and node.attr in {"stdout", "stderr"}:
                return "approved" if parent_origin == "process" else "unknown"
            return parent_origin
        keys = static_dict_keys(node, builders, literals)
        if keys is not None and has_contract_signature(keys):
            return "unapproved"
        if isinstance(node, ast.Call):
            function_name = static_call_name(node.func)
            identity = call_identity(node.func, aliases, containers)
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "read_bytes"
                and not node.args
                and not node.keywords
            ):
                path_origin = static_path_origin(
                    node.func.value, paths, aliases, containers
                )
                if path_origin in {
                    "approved-input-path",
                    "canonical-path",
                    "product-path",
                }:
                    return "approved"
                if path_origin == "support-path":
                    return "support"
                return "unknown"
            if identity in approved_contract_loaders:
                path_argument: ast.AST | None = None
                if len(node.args) == 1 and not node.keywords:
                    path_argument = node.args[0]
                elif not node.args and len(node.keywords) == 1:
                    keyword = node.keywords[0]
                    if keyword.arg == "path":
                        path_argument = keyword.value
                if path_argument is None:
                    return "unknown"
                path_origin = static_path_origin(
                    path_argument, paths, aliases, containers
                )
                if path_origin in {"canonical-path", "product-path"}:
                    return "approved"
                if path_origin == "support-path":
                    return "support"
                return "unknown"
            if identity in approved_contract_sources:
                return "approved"
            argument_origins = [
                expression_origin(
                    argument,
                    origins,
                    builders,
                    literals,
                    paths,
                    aliases,
                    containers,
                )
                for argument in node.args
            ]
            argument_origins.extend(
                expression_origin(
                    keyword.value,
                    origins,
                    builders,
                    literals,
                    paths,
                    aliases,
                    containers,
                )
                for keyword in node.keywords
                if keyword.arg is not None
            )
            if any(keyword.arg is None for keyword in node.keywords):
                argument_origins.append("unknown")
            if identity in approved_process_sources:
                return "process"
            if identity in approved_process_decoders and "process" in argument_origins:
                return "approved"
            if identity in approved_contract_encoders and argument_origins == [
                "approved"
            ]:
                return "approved"
            if identity in approved_contract_encoders and argument_origins == [
                "support"
            ]:
                return "support"
            if function_name in {"copy", "deepcopy", "dict", "dumps", "loads"} and (
                "approved" in argument_origins
            ):
                return "approved"
            if function_name in {"copy", "deepcopy", "dict", "dumps", "loads"} and (
                "support" in argument_origins
                and all(origin in {"support", "literal"} for origin in argument_origins)
            ):
                return "support"
            return "unknown"
        return "unknown"

    contract_sinks = {
        "flow_control.build_review_request": (
            (0, "candidate", False),
            (1, "machine", False),
        ),
        "flow_control.review_semantic_problems": (
            (0, "review", False),
            (1, "candidate", False),
            (3, "machine_report", True),
        ),
        "tests.support.finalize_metadata": ((1, "candidate", False),),
        "tests.support.review_request": (
            (0, "candidate", False),
            (1, "machine", False),
        ),
        "tests.support.write_json": ((1, "value", False),),
        "tests/generate_assets.py:make_golden_and_schema_assets": (
            (0, "official", False),
        ),
        "tests/support.py:review_request": (
            (0, "candidate", False),
            (1, "machine", False),
        ),
        "tests/support.py:write_json": ((1, "value", False),),
    }
    known_sink_names = frozenset(
        identity.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
        for identity in contract_sinks
    )
    allowed_non_sink_identities = frozenset(
        {"tests/generate_assets.py:write_json"}
    )

    approved_product_tuple_sources = frozenset(
        {
            "tests.replay.harness.run_scenario",
            "tests/unit/test_flow_control.py:initialize_explicit_flow",
            "tests/unit/test_flow_control.py:start_explicit_flow",
        }
    )

    sensitive_identities = frozenset(
        {
            *contract_sinks,
            *approved_contract_loaders,
            *approved_contract_sources,
            *approved_contract_encoders,
            *approved_process_sources,
            *approved_process_decoders,
        }
    )
    known_sensitive_names = frozenset(
        identity.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
        for identity in sensitive_identities
    )
    direct_process_identities = frozenset(
        {"subprocess.Popen", "subprocess.run"}
    )
    constructed_process_identities = frozenset(
        {"subprocess.CompletedProcess"}
    )
    approved_direct_process_scopes = frozenset(
        {
            ("tests/generate_assets.py", "run_cli"),
            ("tests/generate_assets.py", "run_machine"),
            ("tests/support.py", "run_cli"),
            ("tests/unit/test_cli.py", "clone_for_doctor"),
            ("tests/unit/test_flow_control.py", "invoke"),
            (
                "tests/unit/test_normalized.py",
                "test_ci_nrm_06_source_checksum_mismatch",
            ),
            ("tests/unit/test_set.py", "test_ci_set_04_parallel_finalize_and_symlink"),
        }
    )
    approved_raw_process_stdin_scopes = frozenset(
        {
            ("tests/generate_assets.py", "build_golden_set"),
            ("tests/unit/test_cli.py", "test_ci_cli_01_invalid_json_stdin"),
            (
                "tests/unit/test_flow_control.py",
                "test_m8_flow_process_failure_three_times_returns_cli05_abort",
            ),
            (
                "tests/unit/test_flow_control.py",
                "test_m8_flow_state_read_tools_guard_denies_only_internal_state",
            ),
        }
    )
    approved_dynamic_process_scopes = frozenset(
        {
            ("tests/replay/harness.py", "flow_cli"),
            ("tests/support.py", "machine_for_path"),
            ("tests/unit/test_cli.py", "test_ci_cli_01_argument_errors"),
            ("tests/unit/test_cli.py", "test_ci_cli_01_invalid_json_stdin"),
            ("tests/unit/test_cli.py", "test_ci_cli_01_missing_paths"),
            (
                "tests/unit/test_flow_control.py",
                "test_m8_candidate_raw_is_preserved_when_canonical_audit_collides",
            ),
            (
                "tests/unit/test_flow_control.py",
                "test_m8_flow_config_snapshot_mismatch_aborts_and_preserves_audits",
            ),
            (
                "tests/unit/test_flow_control.py",
                "test_m8_flow_defined_error_removes_state_and_preserves_collision",
            ),
            (
                "tests/unit/test_flow_control.py",
                "test_m8_flow_preflight_failure_removes_state_and_preserves_audits",
            ),
            (
                "tests/unit/test_flow_control.py",
                "test_m8_flow_process_failure_three_times_returns_cli05_abort",
            ),
            (
                "tests/unit/test_flow_control.py",
                "test_m8_review_preflight_cli_help_required_arguments_and_success",
            ),
            (
                "tests/unit/test_flow_control.py",
                "test_m8_review_preflight_cli_rejects_missing_or_mismatched_request",
            ),
            ("tests/unit/test_html.py", "generate"),
            ("tests/unit/test_machine_lookup.py", "report"),
            ("tests/unit/test_machine_lookup.py", "raw"),
            (
                "tests/unit/test_normalized.py",
                "test_ci_nrm_04_normalized_schemas_via_cli",
            ),
            ("tests/unit/test_schemas.py", "test_ci_sch_03_invalid_examples"),
            ("tests/unit/test_schemas.py", "test_ci_sch_02_valid_examples"),
            ("tests/unit/test_schemas.py", "test_ci_sch_04_format_union"),
            ("tests/unit/test_schemas.py", "test_ci_sch_05_identifier_formats"),
            (
                "tests/unit/test_fixtures.py",
                "test_ci_fix_01_golden_cases_machine_pass",
            ),
        }
    )

    def identity_terminal(identity: str) -> str:
        return identity.rsplit(".", 1)[-1].rsplit(":", 1)[-1]

    def process_call_violations(
        node: ast.Call,
        identity: str | None,
        scope_name: str,
        origins: dict[str, str],
        builders: dict[str, set[str]],
        strings: dict[str, set[str | bytes]],
        paths: dict[str, str],
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> set[str]:
        problems: set[str] = set()
        scope_key = (filename, scope_name)
        if identity in direct_process_identities:
            if scope_key not in approved_direct_process_scopes:
                problems.add("contract-process-direct")
            return problems
        if identity in constructed_process_identities:
            if (
                any(isinstance(argument, ast.Starred) for argument in node.args)
                or any(keyword.arg is None for keyword in node.keywords)
                or len(node.args) > 4
                or any(
                    keyword.arg not in {"args", "returncode", "stderr", "stdout"}
                    for keyword in node.keywords
                    if keyword.arg is not None
                )
            ):
                problems.add("contract-process-shape")
                return problems
            keyword_arguments = {
                keyword.arg: keyword.value
                for keyword in node.keywords
                if keyword.arg is not None
            }
            resolved: dict[str, ast.AST | None] = {}
            for position, name in enumerate(
                ("args", "returncode", "stdout", "stderr")
            ):
                positional = (
                    node.args[position]
                    if position < len(node.args)
                    else None
                )
                keyword = keyword_arguments.get(name)
                if positional is not None and keyword is not None:
                    problems.add("contract-process-shape")
                resolved[name] = positional if positional is not None else keyword
            returncode = resolved["returncode"]
            if resolved["args"] is None or not (
                isinstance(returncode, ast.Constant)
                and type(returncode.value) is int
            ):
                problems.add("contract-process-shape")
                return problems
            if returncode.value == 0:
                stdout = resolved["stdout"]
                if stdout is None:
                    problems.add("contract-process-shape")
                elif (
                    expression_origin(
                        stdout,
                        origins,
                        builders,
                        strings,
                        paths,
                        aliases,
                        containers,
                    )
                    != "approved"
                ):
                    problems.add("contract-process-stdout")
            return problems
        if identity not in approved_process_sources:
            return problems
        if any(keyword.arg is None for keyword in node.keywords):
            problems.add("contract-process-shape")
            return problems
        keyword_arguments = {
            keyword.arg: keyword.value
            for keyword in node.keywords
            if keyword.arg is not None
        }
        if identity.endswith("machine_for_path"):
            candidate_path = (
                node.args[0]
                if node.args
                else keyword_arguments.get("candidate_path")
            )
            if candidate_path is None or static_path_origin(
                candidate_path, paths, aliases, containers
            ) not in {
                "approved-input-path",
                "canonical-path",
                "product-path",
            } and scope_key not in approved_dynamic_process_scopes:
                problems.add("contract-process-path")
            return problems
        if not identity.endswith("run_cli"):
            return problems
        stdin = keyword_arguments.get("stdin")
        if stdin is not None and not (
            isinstance(stdin, ast.Constant) and stdin.value is None
        ):
            stdin_origin = expression_origin(
                stdin,
                origins,
                builders,
                strings,
                paths,
                aliases,
                containers,
            )
            if (
                stdin_origin != "approved"
                and scope_key not in approved_raw_process_stdin_scopes
            ):
                problems.add("contract-process-stdin")
        if any(isinstance(argument, ast.Starred) for argument in node.args):
            if scope_key not in approved_dynamic_process_scopes:
                problems.add("contract-process-shape")
            return problems
        path_flags = {
            "--candidate",
            "--file",
            "--set",
            "--set-dir",
            "--source-dir",
        }
        for index, argument in enumerate(node.args[:-1]):
            flags = static_string_values(argument, strings)
            if flags is None or not flags <= path_flags:
                continue
            path_argument = node.args[index + 1]
            path_values = static_string_values(path_argument, strings)
            if path_values == {"-"}:
                continue
            path_origin = static_path_origin(
                path_argument, paths, aliases, containers
            )
            if path_origin not in {
                "canonical-path",
                "product-path",
                "support-path",
            } and scope_key not in approved_dynamic_process_scopes:
                problems.add("contract-process-path")
        return problems

    def sensitive_terminal_in(
        node: ast.AST,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> str | None:
        for item in ast.walk(node):
            if isinstance(item, ast.Name) and item.id in containers:
                for identity in container_elements(
                    containers[item.id]
                ).values():
                    terminal = identity_terminal(identity)
                    if (
                        identity in sensitive_identities
                        or identity.startswith("unresolved-sensitive:")
                        or terminal in known_sensitive_names
                    ):
                        return terminal
            if not isinstance(
                item, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)
            ):
                continue
            identity = call_identity(item, aliases, containers)
            if identity is None:
                continue
            terminal = identity_terminal(identity)
            if (
                identity in sensitive_identities
                or identity.startswith("unresolved-sensitive:")
                or terminal in known_sensitive_names
            ):
                return terminal
        return None

    def sink_terminal_in(
        node: ast.AST,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> str | None:
        for item in ast.walk(node):
            if not isinstance(
                item, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)
            ):
                continue
            identity = call_identity(item, aliases, containers)
            if identity is None:
                continue
            terminal = identity_terminal(identity)
            if identity in contract_sinks or terminal in known_sink_names:
                return terminal
        return None

    def static_callable_container(
        node: ast.AST,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> dict[object, str] | None:
        if isinstance(node, ast.Name) and node.id in containers:
            return dict(containers[node.id])
        values: list[tuple[object, ast.AST]]
        kind: str
        if isinstance(node, (ast.Tuple, ast.List)):
            values = list(enumerate(node.elts))
            kind = "sequence"
        elif isinstance(node, ast.Dict):
            values = []
            kind = "mapping"
            for key, value in zip(node.keys, node.values, strict=True):
                if not isinstance(key, ast.Constant) or not isinstance(
                    key.value, (int, str, bytes)
                ):
                    continue
                values.append((key.value, value))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"items", "keys", "values"}
            and not node.args
            and not node.keywords
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in containers
        ):
            elements = container_elements(
                containers[node.func.value.id]
            )
            if node.func.attr == "keys":
                elements = {
                    key: f"shadowed:container-key:{key!r}"
                    for key in elements
                }
            return tagged_container(elements, node.func.attr)
        else:
            return None
        identities: dict[object, str] = {}
        contains_sensitive = False
        for key, value in values:
            identity = call_identity(value, aliases, containers)
            if identity is None:
                terminal = (
                    unresolved_binding_terminal(value, aliases, containers)
                    if isinstance(value, ast.Call)
                    else sensitive_terminal_in(value, aliases, containers)
                )
                if terminal is not None:
                    identity = f"unresolved-sensitive:{terminal}"
            if identity is None:
                identity = f"shadowed:container-element:{key!r}"
            identities[key] = identity
            if (
                identity in sensitive_identities
                or identity.startswith("unresolved-sensitive:")
                or identity_terminal(identity) in known_sensitive_names
            ):
                contains_sensitive = True
        return tagged_container(identities, kind) if contains_sensitive else None

    def static_iteration_values(
        node: ast.AST,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> list[ast.AST] | None:
        if isinstance(node, (ast.Tuple, ast.List)):
            return list(node.elts)
        if isinstance(node, ast.Name) and node.id in containers:
            container = container_elements(containers[node.id])
            kind = container_kind(containers[node.id])
            if kind in {
                "container-kind:sequence",
                "container-kind:values",
            }:
                return [
                    ast.Subscript(
                        value=node,
                        slice=ast.Constant(key),
                        ctx=ast.Load(),
                    )
                    for key in container
                ]
            if kind == "container-kind:items":
                return [
                    ast.Tuple(
                        elts=[
                            ast.Constant(key),
                            ast.Subscript(
                                value=node,
                                slice=ast.Constant(key),
                                ctx=ast.Load(),
                            ),
                        ],
                        ctx=ast.Load(),
                    )
                    for key in container
                ]
            if kind in {
                "container-kind:keys",
                "container-kind:mapping",
            }:
                return [ast.Constant(key) for key in container]
            return None
        if not isinstance(node, ast.Call):
            return None
        if (
            static_call_name(node.func) == "iter"
            and len(node.args) == 1
            and not node.keywords
        ):
            return static_iteration_values(
                node.args[0], aliases, containers
            )
        if not (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in containers
            and not node.args
            and not node.keywords
        ):
            return None
        container = container_elements(containers[node.func.value.id])
        if node.func.attr == "keys":
            return [ast.Constant(key) for key in container]
        values = [
            ast.Subscript(
                value=node.func.value,
                slice=ast.Constant(key),
                ctx=ast.Load(),
            )
            for key in container
        ]
        if node.func.attr == "values":
            return values
        if node.func.attr == "items":
            return [
                ast.Tuple(
                    elts=[ast.Constant(key), value],
                    ctx=ast.Load(),
                )
                for key, value in zip(container, values, strict=True)
            ]
        return None

    def returned_callable_container(
        definition: ast.FunctionDef | ast.AsyncFunctionDef,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> dict[object, str] | None:
        state_type = tuple[dict[str, str], dict[str, dict[object, str]]]

        direct_nodes: list[ast.AST] = []
        stack: list[ast.AST] = list(definition.body)
        while stack:
            node = stack.pop()
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                continue
            direct_nodes.append(node)
            stack.extend(ast.iter_child_nodes(node))
        tracked_names = {
            node.value.id
            for node in direct_nodes
            if isinstance(node, ast.Return)
            and isinstance(node.value, ast.Name)
        }
        changed = True
        while changed:
            changed = False
            for node in direct_nodes:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                value = node.value
                if not isinstance(value, ast.Name):
                    continue
                targets = (
                    node.targets
                    if isinstance(node, ast.Assign)
                    else [node.target]
                )
                target_names = {
                    name
                    for target in targets
                    for name, _ in target_bindings(target, value)
                }
                if target_names & tracked_names and value.id not in tracked_names:
                    tracked_names.add(value.id)
                    changed = True

        returned: list[dict[object, str] | None] = []

        def copy_state(state: state_type) -> state_type:
            state_aliases, state_containers = state
            return (
                dict(state_aliases),
                {
                    name: dict(container)
                    for name, container in state_containers.items()
                },
            )

        def unique_states(states: list[state_type]) -> list[state_type]:
            unique: list[state_type] = []
            for state in states:
                if not any(state == existing for existing in unique):
                    unique.append(state)
            return unique

        def bind_assignment(
            node: ast.Assign | ast.AnnAssign, state: state_type
        ) -> state_type:
            state_aliases, state_containers = copy_state(state)
            value = node.value
            if value is None:
                return state_aliases, state_containers
            targets = (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            for target in targets:
                for name, binding_value in target_bindings(
                    target, value, state_aliases, state_containers
                ):
                    if name not in tracked_names:
                        continue
                    bind_callable_name(
                        name,
                        binding_value,
                        state_aliases,
                        state_containers,
                    )
            return state_aliases, state_containers

        def block_affects_summary(statements: list[ast.stmt]) -> bool:
            stack: list[ast.AST] = list(statements)
            while stack:
                node = stack.pop()
                if isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                        ast.ClassDef,
                        ast.Lambda,
                    ),
                ):
                    continue
                if isinstance(node, ast.Return):
                    return True
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    value = node.value
                    targets = (
                        node.targets
                        if isinstance(node, ast.Assign)
                        else [node.target]
                    )
                    names = {
                        name
                        for target in targets
                        for name, _ in target_bindings(target, value)
                    }
                    if names & tracked_names:
                        return True
                stack.extend(ast.iter_child_nodes(node))
            return False

        def analyze_block(
            statements: list[ast.stmt], states: list[state_type]
        ) -> list[state_type]:
            current = states
            for statement in statements:
                if not current:
                    break
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    current = [
                        bind_assignment(statement, state) for state in current
                    ]
                    continue
                if isinstance(statement, ast.Return):
                    for state_aliases, state_containers in current:
                        returned.append(
                            static_callable_container(
                                statement.value,
                                state_aliases,
                                state_containers,
                            )
                            if statement.value is not None
                            else None
                        )
                    current = []
                    break
                branches: list[list[ast.stmt]] | None = None
                include_previous = False
                if isinstance(statement, ast.If):
                    branches = [statement.body, statement.orelse]
                    include_previous = not statement.orelse
                elif isinstance(statement, ast.Try):
                    branches = [
                        [*statement.body, *statement.orelse],
                        *(handler.body for handler in statement.handlers),
                    ]
                elif isinstance(statement, ast.Match):
                    branches = [case.body for case in statement.cases]
                    include_previous = not (
                        statement.cases
                        and isinstance(statement.cases[-1].pattern, ast.MatchAs)
                        and statement.cases[-1].pattern.pattern is None
                        and statement.cases[-1].pattern.name is None
                    )
                elif isinstance(
                    statement, (ast.For, ast.AsyncFor, ast.While)
                ):
                    branches = [statement.body, []]
                    include_previous = True
                elif isinstance(statement, (ast.With, ast.AsyncWith)):
                    branches = [statement.body]
                if branches is None:
                    continue
                if not any(block_affects_summary(branch) for branch in branches):
                    continue
                branched: list[state_type] = []
                for state in current:
                    if include_previous:
                        branched.append(copy_state(state))
                    for branch in branches:
                        branched.extend(
                            analyze_block(branch, [copy_state(state)])
                        )
                current = unique_states(branched)
                finalbody = (
                    statement.finalbody
                    if isinstance(statement, ast.Try)
                    else statement.orelse
                    if isinstance(
                        statement, (ast.For, ast.AsyncFor, ast.While)
                    )
                    else []
                )
                if finalbody:
                    current = analyze_block(finalbody, current)
            return unique_states(current)

        initial_state: state_type = (
            dict(aliases),
            {name: dict(value) for name, value in containers.items()},
        )
        fallthrough = analyze_block(definition.body, [initial_state])
        if returned and fallthrough:
            returned.append(None)
        concrete = [container for container in returned if container is not None]
        if not concrete:
            return None
        if len(concrete) == len(returned) and all(
            container == concrete[0] for container in concrete[1:]
        ):
            return dict(concrete[0])

        merged: dict[object, str] = {}
        keys = set().union(
            *(container_elements(container) for container in concrete)
        )
        for key in keys:
            identities = {
                container_elements(container).get(key)
                for container in concrete
            }
            identities.discard(None)
            sensitive = [
                identity
                for identity in identities
                if identity is not None
                and (
                    identity in sensitive_identities
                    or identity.startswith("unresolved-sensitive:")
                    or identity_terminal(identity) in known_sensitive_names
                )
            ]
            if len(identities) == 1 and len(concrete) == len(returned):
                merged[key] = next(iter(identities))
            elif sensitive:
                merged[key] = (
                    f"unresolved-sensitive:{identity_terminal(sensitive[0])}"
                )
        kinds = {container_kind(container) for container in concrete}
        kind = (
            next(iter(kinds)).removeprefix("container-kind:")
            if len(kinds) == 1
            else "unknown"
        )
        return tagged_container(merged, kind) if merged else None

    def unresolved_binding_terminal(
        value: ast.AST,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> str | None:
        if isinstance(value, ast.Call):
            callee_identity = call_identity(value.func, aliases, containers)
            if callee_identity in sensitive_identities:
                return None
            if callee_identity is not None and (
                callee_identity.startswith("unresolved-sensitive:")
                or identity_terminal(callee_identity)
                in known_sensitive_names
            ):
                return identity_terminal(callee_identity)
            if (
                isinstance(value.func, ast.Attribute)
                and isinstance(value.func.value, ast.Name)
                and value.func.value.id in containers
                and value.func.attr not in {"items", "keys", "values"}
            ):
                for identity in container_elements(
                    containers[value.func.value.id]
                ).values():
                    if (
                        identity in sensitive_identities
                        or identity.startswith("unresolved-sensitive:")
                        or identity_terminal(identity) in known_sensitive_names
                    ):
                        return identity_terminal(identity)
            for argument in [
                *value.args,
                *(keyword.value for keyword in value.keywords),
            ]:
                argument_identity = call_identity(
                    argument, aliases, containers
                )
                if argument_identity in sensitive_identities:
                    return identity_terminal(argument_identity)
                terminal = sensitive_terminal_in(
                    argument, aliases, containers
                )
                if terminal is not None:
                    return terminal
            return None
        return sensitive_terminal_in(value, aliases, containers)

    def returned_sensitive_terminal(
        definition: ast.FunctionDef | ast.AsyncFunctionDef,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> str | None:
        stack: list[ast.AST] = list(definition.body)
        while stack:
            node = stack.pop()
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                continue
            if isinstance(node, ast.Return) and node.value is not None:
                identity = call_identity(
                    node.value, aliases, containers
                )
                terminal = None
                if identity is not None and (
                    identity in sensitive_identities
                    or identity.startswith("unresolved-sensitive:")
                    or identity_terminal(identity)
                    in known_sensitive_names
                ):
                    terminal = identity_terminal(identity)
                elif isinstance(
                    node.value,
                    (ast.Call, ast.IfExp, ast.Subscript),
                ):
                    terminal = unresolved_binding_terminal(
                        node.value, aliases, containers
                    )
                if terminal is not None:
                    return terminal
            stack.extend(ast.iter_child_nodes(node))
        return None

    def bind_sensitive_class_attributes(
        definition: ast.ClassDef,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> None:
        owner = call_identity(
            ast.Name(id=definition.name), aliases, containers
        )
        if owner is None:
            return
        for statement in definition.body:
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            value = statement.value
            if value is None:
                continue
            identity = call_identity(value, aliases, containers)
            terminal = unresolved_binding_terminal(
                value, aliases, containers
            )
            if not (
                identity in sensitive_identities
                or identity is not None
                and identity.startswith("unresolved-sensitive:")
                or terminal is not None
            ):
                continue
            targets = (
                statement.targets
                if isinstance(statement, ast.Assign)
                else [statement.target]
            )
            for target in targets:
                for name, binding_value in target_bindings(
                    target, value, aliases, containers
                ):
                    symbol = f"{owner}.{name}"
                    binding_identity = (
                        call_identity(binding_value, aliases, containers)
                        if binding_value is not None
                        else None
                    )
                    aliases[symbol] = (
                        binding_identity
                        if binding_identity in sensitive_identities
                        else f"unresolved-sensitive:{terminal}"
                    )

    def target_bindings(
        target: ast.AST,
        value: ast.AST | None,
        aliases: dict[str, str] | None = None,
        containers: dict[str, dict[object, str]] | None = None,
    ) -> list[tuple[str, ast.AST | None]]:
        aliases = {} if aliases is None else aliases
        containers = {} if containers is None else containers
        if isinstance(target, ast.Name):
            return [(target.id, value)]
        if isinstance(target, ast.Starred):
            return target_bindings(target.value, None, aliases, containers)
        if isinstance(target, (ast.Tuple, ast.List)):
            if (
                isinstance(value, (ast.Tuple, ast.List))
                and len(value.elts) == len(target.elts)
            ):
                value_elements: list[ast.AST | None] = list(value.elts)
            else:
                iteration_values = (
                    static_iteration_values(value, aliases, containers)
                    if value is not None
                    else None
                )
                if (
                    iteration_values is not None
                    and len(iteration_values) == len(target.elts)
                ):
                    value_elements = list(iteration_values)
                else:
                    value_elements = [None] * len(target.elts)
            bindings: list[tuple[str, ast.AST | None]] = []
            for element, element_value in zip(
                target.elts, value_elements, strict=True
            ):
                bindings.extend(
                    target_bindings(
                        element,
                        element_value,
                        aliases,
                        containers,
                    )
                )
            return bindings
        return []

    def bind_callable_name(
        name: str,
        value: ast.AST | None,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> None:
        previous = call_identity(ast.Name(id=name), aliases, containers)
        identity = (
            call_identity(value, aliases, containers)
            if value is not None
            else None
        )
        container = (
            static_callable_container(value, aliases, containers)
            if value is not None
            else None
        )
        if identity is not None:
            aliases[name] = identity
        elif container is not None or isinstance(
            value, (ast.Tuple, ast.List, ast.Dict, ast.Set)
        ):
            aliases[name] = f"shadowed:{name}"
        else:
            terminal = (
                unresolved_binding_terminal(value, aliases, containers)
                if value is not None
                else None
            )
            if terminal is None and previous is not None:
                previous_terminal = identity_terminal(previous)
                if (
                    previous in sensitive_identities
                    or previous.startswith("unresolved-sensitive:")
                    or previous_terminal in known_sensitive_names
                ):
                    terminal = previous_terminal
            aliases[name] = (
                f"unresolved-sensitive:{terminal}"
                if terminal is not None
                else f"shadowed:{name}"
            )
        if container is None:
            containers.pop(name, None)
        else:
            containers[name] = container

    def bind_callable_attribute(
        target: ast.Attribute,
        value: ast.AST | None,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> None:
        owner = call_identity(target.value, aliases, containers)
        if owner is None:
            return
        symbol = f"{owner}.{target.attr}"
        previous = aliases.get(symbol, symbol)
        identity = (
            call_identity(value, aliases, containers)
            if value is not None
            else None
        )
        if identity is not None:
            aliases[symbol] = identity
            return
        terminal = (
            unresolved_binding_terminal(value, aliases, containers)
            if value is not None
            else None
        )
        previous_terminal = identity_terminal(previous)
        if terminal is None and (
            previous in sensitive_identities
            or previous.startswith("unresolved-sensitive:")
            or previous_terminal in known_sensitive_names
        ):
            terminal = previous_terminal
        aliases[symbol] = (
            f"unresolved-sensitive:{terminal}"
            if terminal is not None
            else f"shadowed:{symbol}"
        )

    def bind_container_slot(
        target: ast.Subscript,
        value: ast.AST | None,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> None:
        if not isinstance(target.value, ast.Name):
            return
        container = containers.get(target.value.id)
        if container is None:
            return
        key = (
            target.slice.value
            if isinstance(target.slice, ast.Constant)
            and isinstance(target.slice.value, (int, str, bytes))
            else None
        )
        keys = (
            [key]
            if key is not None
            else list(container_elements(container))
        )
        for item_key in keys:
            previous = container.get(item_key)
            identity = (
                call_identity(value, aliases, containers)
                if value is not None
                else None
            )
            if identity is not None:
                container[item_key] = identity
            elif previous is not None:
                container[item_key] = (
                    f"unresolved-sensitive:{identity_terminal(previous)}"
                )

    unknown_branch_value = object()

    def final_branch_values(
        statements: list[ast.stmt],
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> dict[str, ast.AST | object]:
        values: dict[str, ast.AST | object] = {}
        for statement in statements:
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                value = statement.value
                targets = (
                    statement.targets
                    if isinstance(statement, ast.Assign)
                    else [statement.target]
                )
                for target in targets:
                    for name, binding_value in target_bindings(
                        target, value, aliases, containers
                    ):
                        values[name] = (
                            binding_value
                            if binding_value is not None
                            else unknown_branch_value
                        )
            elif isinstance(
                statement,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                values[statement.name] = unknown_branch_value
            else:
                for nested in ast.walk(statement):
                    if isinstance(nested, ast.NamedExpr):
                        for name, binding_value in target_bindings(
                            nested.target,
                            nested.value,
                            aliases,
                            containers,
                        ):
                            values[name] = (
                                binding_value
                                if binding_value is not None
                                else unknown_branch_value
                            )
                    elif isinstance(
                        nested, (ast.Assign, ast.AnnAssign, ast.For, ast.AsyncFor)
                    ):
                        targets = (
                            nested.targets
                            if isinstance(nested, ast.Assign)
                            else [nested.target]
                        )
                        value = (
                            nested.value
                            if isinstance(nested, (ast.Assign, ast.AnnAssign))
                            else None
                        )
                        for target in targets:
                            for name, binding_value in target_bindings(
                                target, value, aliases, containers
                            ):
                                values[name] = (
                                    binding_value
                                    if binding_value is not None
                                    else unknown_branch_value
                                )
        return values

    def branch_identity(
        name: str,
        value: ast.AST | object,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> str:
        previous = call_identity(ast.Name(id=name), aliases, containers)
        if value is not unknown_branch_value:
            assert isinstance(value, ast.AST)
            identity = call_identity(value, aliases, containers)
            if identity is not None:
                return identity
            terminal = unresolved_binding_terminal(value, aliases, containers)
            if terminal is not None:
                return f"unresolved-sensitive:{terminal}"
        if previous is not None:
            previous_terminal = identity_terminal(previous)
            if (
                previous in sensitive_identities
                or previous.startswith("unresolved-sensitive:")
                or previous_terminal in known_sensitive_names
            ):
                return f"unresolved-sensitive:{previous_terminal}"
        return f"shadowed:{name}"

    def control_flow_merge_taints(
        node: ast.If | ast.Try | ast.Match | ast.For | ast.AsyncFor | ast.While,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> dict[str, str]:
        branches: list[list[ast.stmt]]
        include_previous = False
        if isinstance(node, ast.If):
            branches = [node.body, node.orelse]
            include_previous = not node.orelse
        elif isinstance(node, ast.Try):
            branches = [
                [*node.body, *node.orelse, *node.finalbody],
                *(
                    [*handler.body, *node.finalbody]
                    for handler in node.handlers
                ),
            ]
            include_previous = True
        elif isinstance(node, ast.Match):
            branches = [case.body for case in node.cases]
            include_previous = True
        else:
            branches = [[*node.body, *node.orelse], node.orelse]
            include_previous = True
        branch_values = [
            final_branch_values(branch, aliases, containers)
            for branch in branches
        ]
        names = set().union(*(values.keys() for values in branch_values))
        taints: dict[str, str] = {}
        for name in names:
            previous = call_identity(ast.Name(id=name), aliases, containers)
            identities = {
                branch_identity(name, values[name], aliases, containers)
                if name in values
                else previous
                for values in branch_values
            }
            if include_previous:
                identities.add(previous)
            if len(identities) <= 1:
                continue
            for identity in identities:
                if identity is None:
                    continue
                terminal = identity_terminal(identity)
                if (
                    identity in sensitive_identities
                    or identity.startswith("unresolved-sensitive:")
                    or terminal in known_sensitive_names
                ):
                    taints[name] = terminal
                    break
        return taints

    assigned_values: dict[str, list[ast.AST]] = {}
    for assignment in ast.walk(tree):
        if not isinstance(assignment, (ast.Assign, ast.AnnAssign)):
            continue
        value = assignment.value
        if value is None:
            continue
        targets = (
            assignment.targets
            if isinstance(assignment, ast.Assign)
            else [assignment.target]
        )
        for target in targets:
            for name, binding_value in target_bindings(target, value):
                if binding_value is not None:
                    assigned_values.setdefault(name, []).append(binding_value)

    def callable_identity_candidates(
        node: ast.AST,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
        seen: frozenset[str] = frozenset(),
    ) -> set[str]:
        identities: set[str] = set()
        identity = call_identity(node, aliases, containers)
        if identity is not None:
            identities.add(identity)
        if isinstance(node, ast.Name) and node.id not in seen:
            for value in assigned_values.get(node.id, []):
                identities.update(
                    callable_identity_candidates(
                        value,
                        aliases,
                        containers,
                        seen | {node.id},
                    )
                )
        elif isinstance(node, ast.IfExp):
            identities.update(
                callable_identity_candidates(
                    node.body, aliases, containers, seen
                )
            )
            identities.update(
                callable_identity_candidates(
                    node.orelse, aliases, containers, seen
                )
            )
        return identities

    def assigned_sequence(
        node: ast.AST,
        seen: frozenset[str] = frozenset(),
    ) -> list[ast.AST] | None:
        if isinstance(node, (ast.Tuple, ast.List)):
            return list(node.elts)
        if isinstance(node, ast.Name) and node.id not in seen:
            values = assigned_values.get(node.id, [])
            if len(values) == 1:
                return assigned_sequence(values[0], seen | {node.id})
        return None

    def assigned_keywords(
        node: ast.AST,
        seen: frozenset[str] = frozenset(),
    ) -> dict[str, ast.AST] | None:
        if isinstance(node, ast.Dict):
            entries: dict[str, ast.AST] = {}
            for key, value in zip(node.keys, node.values, strict=True):
                if not (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                ):
                    return None
                entries[key.value] = value
            return entries
        if isinstance(node, ast.Name) and node.id not in seen:
            values = assigned_values.get(node.id, [])
            if len(values) == 1:
                return assigned_keywords(values[0], seen | {node.id})
        return None

    def parameter_callee_names(
        definition: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> set[str]:
        parameter_names = {
            parameter.arg
            for parameter in [
                *definition.args.posonlyargs,
                *definition.args.args,
                *definition.args.kwonlyargs,
            ]
        }
        if definition.args.vararg is not None:
            parameter_names.add(definition.args.vararg.arg)
        if definition.args.kwarg is not None:
            parameter_names.add(definition.args.kwarg.arg)
        callees: set[str] = set()
        stack: list[ast.AST] = list(definition.body)
        while stack:
            node = stack.pop()
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                continue
            if (
                isinstance(node, ast.Call)
                and (
                    isinstance(node.func, ast.Name)
                    and node.func.id in parameter_names
                    or isinstance(node.func, ast.Subscript)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in parameter_names
                )
            ):
                callees.add(
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.value.id
                )
            stack.extend(ast.iter_child_nodes(node))
        return callees

    def local_function_call_mappings(
        definition: ast.FunctionDef | ast.AsyncFunctionDef,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
    ) -> list[tuple[dict[str, ast.AST], set[str]]]:
        identity = f"{filename}:{definition.name}"
        positional = [
            *definition.args.posonlyargs,
            *definition.args.args,
        ]
        keywordable = {
            parameter.arg
            for parameter in [
                *definition.args.args,
                *definition.args.kwonlyargs,
            ]
        }
        mappings: list[tuple[dict[str, ast.AST], set[str]]] = []
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call) or identity not in (
                callable_identity_candidates(call.func, aliases, containers)
            ):
                continue
            mapping: dict[str, ast.AST] = {}
            uncertain: set[str] = set()
            vararg_values: list[ast.AST] = []
            kwarg_keys: list[ast.AST] = []
            kwarg_values: list[ast.AST] = []
            position = 0
            for argument in call.args:
                values = (
                    assigned_sequence(argument.value)
                    if isinstance(argument, ast.Starred)
                    else [argument]
                )
                if values is None:
                    remaining = {
                        parameter.arg
                        for parameter in positional[position:]
                    }
                    uncertain.update(remaining)
                    if definition.args.vararg is not None:
                        uncertain.add(definition.args.vararg.arg)
                    continue
                for value in values:
                    if position < len(positional):
                        mapping[positional[position].arg] = value
                        position += 1
                    elif definition.args.vararg is not None:
                        vararg_values.append(value)
                    else:
                        uncertain.update(
                            parameter.arg for parameter in positional
                        )
            for keyword in call.keywords:
                if keyword.arg is not None:
                    if keyword.arg in keywordable:
                        if keyword.arg in mapping:
                            uncertain.add(keyword.arg)
                        mapping[keyword.arg] = keyword.value
                    elif definition.args.kwarg is not None:
                        kwarg_keys.append(ast.Constant(value=keyword.arg))
                        kwarg_values.append(keyword.value)
                    continue
                entries = assigned_keywords(keyword.value)
                if entries is None:
                    uncertain.update(keywordable)
                    if definition.args.kwarg is not None:
                        uncertain.add(definition.args.kwarg.arg)
                    continue
                for name, value in entries.items():
                    if name in keywordable:
                        if name in mapping:
                            uncertain.add(name)
                        mapping[name] = value
                    elif definition.args.kwarg is not None:
                        kwarg_keys.append(ast.Constant(value=name))
                        kwarg_values.append(value)
            if definition.args.vararg is not None and vararg_values:
                mapping[definition.args.vararg.arg] = ast.Tuple(
                    elts=vararg_values,
                    ctx=ast.Load(),
                )
            if definition.args.kwarg is not None and kwarg_values:
                mapping[definition.args.kwarg.arg] = ast.Dict(
                    keys=kwarg_keys,
                    values=kwarg_values,
                )
            mappings.append((mapping, uncertain))
        return mappings

    verified_local_wrapper_identities = frozenset(
        f"{filename}:{definition.name}"
        for definition in ast.walk(tree)
        if isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef))
        and parameter_callee_names(definition)
    )

    def sensitive_callable_argument_terminal(
        node: ast.AST,
        aliases: dict[str, str],
        containers: dict[str, dict[object, str]],
        seen: frozenset[str] = frozenset(),
    ) -> str | None:
        if isinstance(node, ast.Starred):
            return sensitive_callable_argument_terminal(
                node.value, aliases, containers, seen
            )
        if isinstance(node, ast.Call):
            identity = call_identity(node, aliases, containers)
            if identity is not None and (
                identity in sensitive_identities
                or identity.startswith("unresolved-sensitive:")
            ):
                return identity_terminal(identity)
            callee_identity = call_identity(
                node.func, aliases, containers
            )
            if callee_identity is not None and callee_identity.startswith(
                "unresolved-sensitive:"
            ) and identity_terminal(callee_identity) in known_sensitive_names:
                return identity_terminal(callee_identity)
            return None
        if isinstance(node, ast.Name):
            identity = call_identity(node, aliases, containers)
            values = (
                assigned_values.get(node.id, [])
                if node.id not in seen
                else []
            )
            if identity is not None and identity in sensitive_identities:
                return identity_terminal(identity)
            if values:
                for value in values:
                    terminal = sensitive_callable_argument_terminal(
                        value,
                        aliases,
                        containers,
                        seen | {node.id},
                    )
                    if terminal is not None:
                        return terminal
                return None
            if identity is not None and identity.startswith(
                "unresolved-sensitive:"
            ):
                return identity_terminal(identity)
            return None
        if isinstance(node, ast.IfExp):
            return sensitive_callable_argument_terminal(
                node.body, aliases, containers, seen
            ) or sensitive_callable_argument_terminal(
                node.orelse, aliases, containers, seen
            )
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for element in node.elts:
                terminal = sensitive_callable_argument_terminal(
                    element, aliases, containers, seen
                )
                if terminal is not None:
                    return terminal
            return None
        if isinstance(node, ast.Dict):
            for value in node.values:
                terminal = sensitive_callable_argument_terminal(
                    value, aliases, containers, seen
                )
                if terminal is not None:
                    return terminal
            return None
        identity = call_identity(node, aliases, containers)
        if identity is not None and identity in sensitive_identities:
            return identity_terminal(identity)
        return None

    for node in ast.walk(tree):
        keys = static_dict_keys(node)
        if keys is not None:
            record(keys, node.lineno)

    scope_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    scopes: list[ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = [tree]
    scopes.extend(
        node
        for node in ast.walk(tree)
        if isinstance(node, scope_types)
    )
    scope_parents: dict[int, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = {}

    def register_scope_parents(
        node: ast.AST,
        parent: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, scope_types):
                scope_parents[id(child)] = parent
                register_scope_parents(child, child)
            else:
                register_scope_parents(child, parent)

    register_scope_parents(tree, tree)
    scope_states: dict[
        int,
        tuple[
            dict[str, set[str | bytes]],
            dict[str, str],
            dict[str, str],
            dict[str, str],
            dict[str, dict[object, str]],
        ],
    ] = {}
    for scope in scopes:
        builders: dict[str, set[str]] = {}
        if scope is tree:
            strings: dict[str, set[str | bytes]] = {}
            origins: dict[str, str] = {}
            paths: dict[str, str] = {}
            aliases: dict[str, str] = {}
            containers: dict[str, dict[object, str]] = {}
        else:
            parent = scope_parents[id(scope)]
            if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                while isinstance(parent, ast.ClassDef):
                    parent = scope_parents[id(parent)]
            (
                parent_strings,
                parent_origins,
                parent_paths,
                parent_aliases,
                parent_containers,
            ) = scope_states[id(parent)]
            strings = {
                key: set(value) for key, value in parent_strings.items()
            }
            origins = dict(parent_origins)
            paths = dict(parent_paths)
            aliases = dict(parent_aliases)
            containers = {
                key: dict(value) for key, value in parent_containers.items()
            }
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            call_strings = {
                key: set(value) for key, value in strings.items()
            }
            call_origins = dict(origins)
            call_paths = dict(paths)
            call_aliases = dict(aliases)
            call_containers = {
                key: dict(value) for key, value in containers.items()
            }
            positional_parameters = [
                *scope.args.posonlyargs,
                *scope.args.args,
            ]
            positional_default_parameters = (
                positional_parameters[-len(scope.args.defaults) :]
                if scope.args.defaults
                else []
            )
            defaults: dict[str, ast.AST] = {
                parameter.arg: default
                for parameter, default in zip(
                    positional_default_parameters,
                    scope.args.defaults,
                    strict=True,
                )
            }
            defaults.update(
                {
                    parameter.arg: default
                    for parameter, default in zip(
                        scope.args.kwonlyargs,
                        scope.args.kw_defaults,
                        strict=True,
                    )
                    if default is not None
                }
            )
            parameters = [
                *positional_parameters,
                *scope.args.kwonlyargs,
            ]
            if scope.args.vararg is not None:
                parameters.append(scope.args.vararg)
            if scope.args.kwarg is not None:
                parameters.append(scope.args.kwarg)
            callee_parameters = parameter_callee_names(scope)
            call_mappings = (
                local_function_call_mappings(
                    scope, call_aliases, call_containers
                )
                if callee_parameters
                else []
            )
            for parameter in parameters:
                default = defaults.get(parameter.arg)
                bind_callable_name(
                    parameter.arg,
                    default,
                    aliases,
                    containers,
                )
                if not callee_parameters:
                    continue
                actual_values = [
                    mapping.get(parameter.arg, default)
                    for mapping, _ in call_mappings
                ]
                is_uncertain = not call_mappings or any(
                    parameter.arg in uncertain
                    for _, uncertain in call_mappings
                )
                if parameter.arg in callee_parameters:
                    callable_containers = [
                        static_callable_container(
                            value, call_aliases, call_containers
                        )
                        if value is not None
                        else None
                        for value in actual_values
                    ]
                    concrete_containers = [
                        value
                        for value in callable_containers
                        if value is not None
                    ]
                    container_bound = (
                        not is_uncertain
                        and bool(concrete_containers)
                        and len(concrete_containers)
                        == len(callable_containers)
                        and all(
                            value == concrete_containers[0]
                            for value in concrete_containers
                        )
                    )
                    if container_bound:
                        aliases[parameter.arg] = (
                            f"shadowed:{parameter.arg}"
                        )
                        containers[parameter.arg] = dict(
                            concrete_containers[0]
                        )
                        exact_identities: set[str] = set()
                    else:
                        exact_identities = set().union(
                            *[
                                callable_identity_candidates(
                                    value, call_aliases, call_containers
                                )
                                if value is not None
                                else set()
                                for value in actual_values
                            ]
                        )
                    sensitive = {
                        identity
                        for identity in exact_identities
                        if identity in sensitive_identities
                        or identity.startswith("unresolved-sensitive:")
                        or identity_terminal(identity)
                        in known_sensitive_names
                    }
                    if container_bound:
                        pass
                    elif (
                        not is_uncertain
                        and len(exact_identities) == 1
                        and len(sensitive) == 1
                    ):
                        aliases[parameter.arg] = next(iter(sensitive))
                    elif sensitive:
                        terminal = identity_terminal(next(iter(sensitive)))
                        aliases[parameter.arg] = (
                            f"unresolved-sensitive:{terminal}"
                        )
                    elif is_uncertain or len(exact_identities) != 1:
                        aliases[parameter.arg] = (
                            f"unresolved-sensitive:{parameter.arg}"
                        )
                    else:
                        aliases[parameter.arg] = next(iter(exact_identities))
                if is_uncertain or any(
                    value is None for value in actual_values
                ):
                    origins[parameter.arg] = "unknown"
                    paths.pop(parameter.arg, None)
                    strings.pop(parameter.arg, None)
                    continue
                argument_origins = {
                    expression_origin(
                        value,
                        call_origins,
                        builders,
                        call_strings,
                        call_paths,
                        call_aliases,
                        call_containers,
                    )
                    for value in actual_values
                    if value is not None
                }
                origins[parameter.arg] = (
                    next(iter(argument_origins))
                    if len(argument_origins) == 1
                    else "unknown"
                )
                path_origins = {
                    static_path_origin(
                        value,
                        call_paths,
                        call_aliases,
                        call_containers,
                    )
                    for value in actual_values
                    if value is not None
                }
                if len(path_origins) == 1:
                    paths[parameter.arg] = next(iter(path_origins))
                else:
                    paths.pop(parameter.arg, None)
                payload_values = [
                    static_payload_values(value, call_strings)
                    for value in actual_values
                    if value is not None
                ]
                if payload_values and all(
                    values is not None for values in payload_values
                ):
                    strings[parameter.arg] = set().union(
                        *(values for values in payload_values if values is not None)
                    )
                else:
                    strings.pop(parameter.arg, None)
            for parameter in approved_contract_parameters.get(
                (filename, scope.name), frozenset()
            ):
                origins[parameter] = "approved"
            paths.update(
                approved_path_parameters.get((filename, scope.name), {})
            )
        direct_nodes: list[ast.AST] = []
        stack = list(scope.body)
        while stack:
            node = stack.pop()
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
            ):
                if not isinstance(node, ast.Lambda):
                    direct_nodes.append(node)
                continue
            direct_nodes.append(node)
            stack.extend(ast.iter_child_nodes(node))
        nodes = sorted(
            direct_nodes,
            key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)),
        )
        external_scope_names = {
            name
            for item in nodes
            if isinstance(item, (ast.Global, ast.Nonlocal))
            for name in item.names
        }
        pending_conditional_taints: list[tuple[int, dict[str, str]]] = []
        for node in nodes:
            current_line = getattr(node, "lineno", 0)
            still_pending: list[tuple[int, dict[str, str]]] = []
            for end_line, taints in pending_conditional_taints:
                if end_line >= current_line:
                    still_pending.append((end_line, taints))
                    continue
                for name, terminal in taints.items():
                    aliases[name] = f"unresolved-sensitive:{terminal}"
                    containers.pop(name, None)
            pending_conditional_taints = still_pending
            if isinstance(
                node,
                (ast.If, ast.Try, ast.Match, ast.For, ast.AsyncFor, ast.While),
            ):
                taints = control_flow_merge_taints(node, aliases, containers)
                if taints:
                    pending_conditional_taints.append(
                        (node.end_lineno or node.lineno, taints)
                    )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_identity = f"{filename}:{node.name}"
                returned_container = returned_callable_container(
                    node, aliases, containers
                )
                if returned_container is not None:
                    function_return_containers[function_identity] = (
                        returned_container
                    )
                    terminal = None
                else:
                    function_return_containers.pop(function_identity, None)
                    terminal = returned_sensitive_terminal(
                        node, aliases, containers
                    )
                aliases[node.name] = (
                    f"unresolved-sensitive:{terminal}"
                    if terminal is not None
                    else function_identity
                )
                containers.pop(node.name, None)
            elif isinstance(node, ast.ClassDef):
                aliases[node.name] = f"{filename}:{node.name}"
                containers.pop(node.name, None)
                bind_sensitive_class_attributes(
                    node, aliases, containers
                )
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                for imported in node.names:
                    local_name = imported.asname or imported.name
                    aliases[local_name] = f"{node.module}.{imported.name}"
                    containers.pop(local_name, None)
            elif isinstance(node, ast.Import):
                for imported in node.names:
                    local_name = imported.asname or imported.name.split(".", 1)[0]
                    aliases[local_name] = imported.name
                    containers.pop(local_name, None)
            if isinstance(node, ast.AugAssign):
                for target_name, _ in target_bindings(
                    node.target, None, aliases, containers
                ):
                    bind_callable_name(
                        target_name, None, aliases, containers
                    )
                if isinstance(node.target, ast.Attribute):
                    bind_callable_attribute(
                        node.target, None, aliases, containers
                    )
                elif isinstance(node.target, ast.Subscript):
                    bind_container_slot(
                        node.target, None, aliases, containers
                    )
            elif isinstance(node, ast.Delete):
                for target in node.targets:
                    for target_name, _ in target_bindings(
                        target, None, aliases, containers
                    ):
                        bind_callable_name(
                            target_name, None, aliases, containers
                        )
                    if isinstance(target, ast.Attribute):
                        bind_callable_attribute(
                            target, None, aliases, containers
                        )
                    elif isinstance(target, ast.Subscript):
                        bind_container_slot(
                            target, None, aliases, containers
                        )
            if isinstance(node, (ast.For, ast.AsyncFor)):
                iteration_values = static_iteration_values(
                    node.iter, aliases, containers
                )
                iteration_bindings: dict[str, list[ast.AST | None]] = {}
                if iteration_values is not None:
                    for iteration_value in iteration_values:
                        for target_name, target_value in target_bindings(
                            node.target,
                            iteration_value,
                            aliases,
                            containers,
                        ):
                            iteration_bindings.setdefault(
                                target_name, []
                            ).append(target_value)
                if iteration_bindings:
                    for target_name, target_values in iteration_bindings.items():
                        identities = {
                            call_identity(value, aliases, containers)
                            for value in target_values
                            if value is not None
                        }
                        identities.discard(None)
                        sensitive = {
                            identity
                            for identity in identities
                            if identity is not None
                            and (
                                identity in sensitive_identities
                                or identity.startswith("unresolved-sensitive:")
                                or identity_terminal(identity)
                                in known_sensitive_names
                            )
                        }
                        if len(identities) == 1 and all(
                            value is not None for value in target_values
                        ):
                            aliases[target_name] = next(iter(identities))
                        elif sensitive:
                            terminal = identity_terminal(next(iter(sensitive)))
                            aliases[target_name] = (
                                f"unresolved-sensitive:{terminal}"
                            )
                        else:
                            aliases[target_name] = f"shadowed:{target_name}"
                        containers.pop(target_name, None)
                else:
                    iterator_terminal = sensitive_terminal_in(
                        node.iter, aliases, containers
                    )
                    for target_name, _ in target_bindings(
                        node.target, None, aliases, containers
                    ):
                        if iterator_terminal is None:
                            bind_callable_name(
                                target_name, node.iter, aliases, containers
                            )
                        else:
                            aliases[target_name] = (
                                f"unresolved-sensitive:{iterator_terminal}"
                            )
                            containers.pop(target_name, None)
            if isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(
                node.target, ast.Name
            ):
                values = static_string_values(node.iter, strings)
                if values is None:
                    strings.pop(node.target.id, None)
                else:
                    strings[node.target.id] = values
                iter_path_origin = static_path_origin(
                    node.iter, paths, aliases, containers
                )
                if iter_path_origin in {"canonical-path", "product-path"}:
                    paths[node.target.id] = iter_path_origin
                else:
                    paths.pop(node.target.id, None)
            if isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars is None:
                        continue
                    for target_name, _ in target_bindings(
                        item.optional_vars,
                        item.context_expr,
                        aliases,
                        containers,
                    ):
                        bind_callable_name(
                            target_name, item.context_expr, aliases, containers
                        )
                    if not isinstance(item.optional_vars, ast.Name):
                        continue
                    if (
                        isinstance(item.context_expr, ast.Call)
                        and call_identity(
                            item.context_expr.func, aliases, containers
                        )
                        == "tests.support.output_set"
                    ):
                        paths[item.optional_vars.id] = "product-path"
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if value is None:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    reflective_identity = call_identity(
                        target, aliases, containers
                    )
                    if reflective_identity is not None and (
                        reflective_identity in sensitive_identities
                        or identity_terminal(reflective_identity)
                        in known_sensitive_names
                    ) and isinstance(target, ast.Subscript):
                        violations.add(
                            f"{filename}:{node.lineno}:contract-scope-rebind"
                        )
                        aliases[reflective_identity] = (
                            "unresolved-sensitive:reflective-rebind"
                        )
                    for target_name, target_value in target_bindings(
                        target, value, aliases, containers
                    ):
                        previous_identity = call_identity(
                            ast.Name(id=target_name), aliases, containers
                        )
                        bind_callable_name(
                            target_name, target_value, aliases, containers
                        )
                        rebound_identity = call_identity(
                            ast.Name(id=target_name), aliases, containers
                        )
                        if (
                            target_name in external_scope_names
                            and rebound_identity != previous_identity
                            and previous_identity is not None
                            and (
                                previous_identity in sensitive_identities
                                or identity_terminal(previous_identity)
                                in known_sensitive_names
                            )
                        ):
                            violations.add(
                                f"{filename}:{node.lineno}:contract-scope-rebind"
                            )
                    if isinstance(target, ast.Attribute):
                        bind_callable_attribute(
                            target, value, aliases, containers
                        )
                    elif isinstance(target, ast.Subscript):
                        bind_container_slot(
                            target, value, aliases, containers
                        )
                for target in targets:
                    if isinstance(target, ast.Name):
                        path_origin = static_path_origin(
                            value, paths, aliases, containers
                        )
                        path_origin = approved_path_bindings.get(
                            (filename, getattr(scope, "name", "<module>")), {}
                        ).get(target.id, path_origin)
                        if path_origin == "unknown-path":
                            paths.pop(target.id, None)
                        else:
                            paths[target.id] = path_origin
                        origins[target.id] = expression_origin(
                            value,
                            origins,
                            builders,
                            strings,
                            paths,
                            aliases,
                            containers,
                        )
                        if target.id in approved_origin_bindings.get(
                            (
                                filename,
                                getattr(scope, "name", "<module>"),
                            ),
                            frozenset(),
                        ):
                            origins[target.id] = "approved"
                        payload_values = static_payload_values(value, strings)
                        if payload_values is None:
                            strings.pop(target.id, None)
                        else:
                            strings[target.id] = payload_values
                        if isinstance(value, ast.Name) and value.id in builders:
                            builders[target.id] = builders[value.id]
                            record(builders[target.id], node.lineno)
                            continue
                        keys = static_dict_keys(value, builders, strings)
                        if keys is None:
                            builders.pop(target.id, None)
                        else:
                            builders[target.id] = set(keys)
                            record(builders[target.id], node.lineno)
                            if has_contract_signature(builders[target.id]):
                                origins[target.id] = "unapproved"
                    elif (
                        isinstance(target, (ast.Tuple, ast.List))
                        and isinstance(value, ast.Call)
                        and call_identity(value.func, aliases, containers)
                        in approved_product_tuple_sources
                    ):
                        if target.elts and isinstance(target.elts[0], ast.Name):
                            paths[target.elts[0].id] = "product-path"
                    elif (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id in builders
                    ):
                        keys = static_string_values(target.slice, strings)
                        if keys is not None:
                            builders[target.value.id].update(keys)
                            record(builders[target.value.id], node.lineno)
            elif isinstance(node, ast.NamedExpr):
                for target_name, target_value in target_bindings(
                    node.target, node.value, aliases, containers
                ):
                    bind_callable_name(
                        target_name, target_value, aliases, containers
                    )
                    origins[target_name] = expression_origin(
                        node.value,
                        origins,
                        builders,
                        strings,
                        paths,
                        aliases,
                        containers,
                    )
            elif isinstance(node, ast.ExceptHandler) and node.name is not None:
                bind_callable_name(node.name, None, aliases, containers)
            elif (
                isinstance(node, ast.AugAssign)
                and isinstance(node.op, ast.BitOr)
                and isinstance(node.target, ast.Name)
                and node.target.id in builders
            ):
                keys = static_dict_keys(node.value, builders, strings)
                if keys is not None:
                    builders[node.target.id].update(keys)
                    record(builders[node.target.id], node.lineno)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "update"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in builders
            ):
                keys: set[str] = {
                    keyword.arg for keyword in node.keywords if keyword.arg is not None
                }
                for argument in node.args:
                    keys.update(
                        static_dict_keys(argument, builders, strings) or set()
                    )
                for keyword in node.keywords:
                    if keyword.arg is None:
                        keys.update(
                            static_dict_keys(keyword.value, builders, strings)
                            or set()
                        )
                builders[node.func.value.id].update(keys)
                record(builders[node.func.value.id], node.lineno)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setdefault"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in builders
                and node.args
            ):
                keys = static_string_values(node.args[0], strings)
                if keys is not None:
                    builders[node.func.value.id].update(keys)
                    record(builders[node.func.value.id], node.lineno)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setitem"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in builders
            ):
                keys = static_string_values(node.args[1], strings)
                if keys is not None:
                    builders[node.args[0].id].update(keys)
                    record(builders[node.args[0].id], node.lineno)
            if isinstance(node, ast.Call):
                identity = call_identity(node.func, aliases, containers)
                sensitive_argument = next(
                    (
                        terminal
                        for argument in [
                            *node.args,
                            *(keyword.value for keyword in node.keywords),
                        ]
                        if (
                            terminal := sensitive_callable_argument_terminal(
                                argument, aliases, containers
                            )
                        )
                        is not None
                    ),
                    None,
                )
                if (
                    sensitive_argument is not None
                    and identity not in verified_local_wrapper_identities
                ):
                    violations.add(
                        f"{filename}:{node.lineno}:contract-call-identity"
                    )
                if (
                    static_call_name(node.func) == "setattr"
                    and len(node.args) >= 2
                ):
                    owner = call_identity(node.args[0], aliases, containers)
                    attributes = static_string_values(node.args[1], strings)
                    if owner is not None and (
                        attributes is None
                        and any(
                            item.startswith(f"{owner}.")
                            for item in sensitive_identities
                        )
                        or attributes is not None
                        and any(
                            f"{owner}.{attribute}" in sensitive_identities
                            for attribute in attributes
                        )
                    ):
                        violations.add(
                            f"{filename}:{node.lineno}:contract-scope-rebind"
                        )
                        continue
                scope_name = (
                    scope.name
                    if isinstance(
                        scope,
                        (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                    )
                    else "<module>"
                )
                process_problems = process_call_violations(
                    node,
                    identity,
                    scope_name,
                    origins,
                    builders,
                    strings,
                    paths,
                    aliases,
                    containers,
                )
                for problem in process_problems:
                    violations.add(f"{filename}:{node.lineno}:{problem}")
                if (
                    identity in direct_process_identities
                    or identity in constructed_process_identities
                    or identity in approved_process_sources
                ):
                    continue
                unresolved_terminal = (
                    sink_terminal_in(node.func, aliases, containers)
                    if identity is None
                    else None
                )
                if (
                    identity is not None
                    and identity.startswith("unresolved-sensitive:")
                    and "." not in identity.removeprefix(
                        "unresolved-sensitive:"
                    )
                ) or unresolved_terminal is not None:
                    violations.add(
                        f"{filename}:{node.lineno}:contract-call-identity"
                    )
                    continue
                terminal_name = (
                    identity_terminal(identity)
                    if identity is not None
                    else static_call_name(node.func)
                )
                sink_arguments = contract_sinks.get(identity)
                if (
                    sink_arguments is None
                    and terminal_name in known_sink_names
                    and identity not in allowed_non_sink_identities
                ):
                    violations.add(
                        f"{filename}:{node.lineno}:contract-call-identity"
                    )
                    continue
                if sink_arguments is None:
                    continue
                keyword_arguments = {
                    keyword.arg: keyword.value
                    for keyword in node.keywords
                    if keyword.arg is not None
                }
                if any(keyword.arg is None for keyword in node.keywords):
                    violations.add(
                        f"{filename}:{node.lineno}:contract-call-shape"
                    )
                write_target_origin: str | None = None
                if terminal_name == "write_json":
                    if node.args:
                        write_target = node.args[0]
                    else:
                        write_target = keyword_arguments.get("path")
                    if write_target is None:
                        violations.add(
                            f"{filename}:{node.lineno}:contract-call-shape"
                        )
                    else:
                        write_target_origin = static_path_origin(
                            write_target, paths, aliases, containers
                        )
                for position, keyword_name, optional in sink_arguments:
                    argument: ast.AST | None = None
                    if position < len(node.args):
                        argument = node.args[position]
                        if keyword_name in keyword_arguments:
                            violations.add(
                                f"{filename}:{node.lineno}:contract-call-shape"
                            )
                    elif keyword_name in keyword_arguments:
                        argument = keyword_arguments[keyword_name]
                    elif optional:
                        continue
                    else:
                        violations.add(
                            f"{filename}:{node.lineno}:contract-call-shape"
                        )
                        continue
                    if optional and isinstance(argument, ast.Constant) and argument.value is None:
                        continue
                    argument_origin = expression_origin(
                        argument,
                        origins,
                        builders,
                        strings,
                        paths,
                        aliases,
                        containers,
                    )
                    origin_is_allowed = argument_origin == "approved" or (
                        terminal_name == "write_json"
                        and write_target_origin == "support-path"
                        and argument_origin == "support"
                    )
                    if not origin_is_allowed:
                        violations.add(
                            f"{filename}:{node.lineno}:contract-origin"
                        )
        for _, taints in pending_conditional_taints:
            for name, terminal in taints.items():
                aliases[name] = f"unresolved-sensitive:{terminal}"
                containers.pop(name, None)
        scope_states[id(scope)] = (
            {key: set(value) for key, value in strings.items()},
            dict(origins),
            dict(paths),
            dict(aliases),
            {
                key: dict(value) for key, value in containers.items()
            },
        )
    return sorted(violations)


def test_ci_fix_01_indexes_are_complete() -> None:
    """CI-FIX-01: 必須4 index.jsonが配下の全fixtureを過不足なく登録する。"""

    for directory in (
        FIXTURES / "candidates",
        FIXTURES / "reviews",
        FIXTURES / "machine",
        FIXTURES / "cli",
        FIXTURES / "schemas" / "invalid",
    ):
        index = load_json(directory / "index.json")
        assert set(index) == {"cases"}
        assert indexed_files(directory) == actual_json_files(directory)
        for case in index["cases"]:
            assert set(case) == {"expected", "file", "purpose", "test_ids"}
            assert case["purpose"] and case["expected"] and case["test_ids"]


def test_ci_fix_01_fixed_required_inventories() -> None:
    """CI-SCH-02/04・CI-HTM-02/03・CI-FIX-01・GLD-05: 必須目録の縮退を拒否する。"""

    expected_sets = {f"{fmt}.set.json" for fmt in OFFICIAL_FORMATS}
    expected_html = {f"{fmt}.html" for fmt in OFFICIAL_FORMATS}
    expected_candidates = {f"official_{fmt}.json" for fmt in OFFICIAL_FORMATS}
    assert {path.name for path in (GOLDEN / "sets").glob("*.set.json")} == expected_sets
    assert {path.name for path in (GOLDEN / "html").glob("*.html")} == expected_html
    assert {
        path.name for path in (FIXTURES / "candidates").glob("official_*.json")
    } == expected_candidates
    assert {path.name for path in (GOLDEN / "cases").glob("*.candidate.json")} == set(
        GOLDEN_CASE_FILES
    )


def test_ci_r_03_json_inputs_are_fixture_or_product_outputs() -> None:
    """CI-R-03: 全テストの製品契約dict直書きと生成器の正本再構築を拒否する。"""

    violations: list[str] = []
    for path in sorted((ROOT / "tests").rglob("*.py")):
        signatures = (
            GENERATOR_PRODUCT_CONTRACTS
            if path.name == "generate_assets.py"
            else TEST_PRODUCT_CONTRACTS
        )
        violations.extend(
            contract_dict_violations(
                path.read_text(encoding="utf-8"),
                path.relative_to(ROOT).as_posix(),
                signatures,
            )
        )
    assert violations == []


def test_ci_r_03_contract_dict_meta_test_detects_direct_and_variable_inputs() -> None:
    """CI-R-03: 完全・部分製品JSONの直接・変数経由直書きを自己検査する。"""

    snippets = (
        "canonical_bytes({'detail': {}, 'error_code': 'E-X', 'message': 'm', 'remedy': 'r'})",
        (
            "report = {'actual_level': None, 'code': 'V-SET-02', 'evidence': 'e', "
            "'expected_level': None, 'location': 'l', 'suggestion': 's'}\n"
            "canonical_bytes(report)"
        ),
        (
            "warning = {'detail': {}, 'message': 'm', 'remedy': 'r', "
            "'warning_code': 'W-CLEANUP-01'}\ncanonical_bytes(warning)"
        ),
        (
            "machine = {'violations': [{'code': 'V-LEX-02', 'location': 'x'}]}\n"
            "review_semantic_problems(review, candidate, None, machine)"
        ),
        (
            "machine = {'schema_version': '1.1.0', 'scope': 'question', "
            "'verdict': 'pass', 'violations': [], 'warnings': [], 'stats': {}}"
        ),
        (
            "review = {'checks': [], 'sentence_grammar_inventory': [], "
            "'violations': [], 'machine_check_disputes': [], 'verdict': 'pass'}"
        ),
        "machine = dict(violations=[dict(code='V-LEX-02', location='x')])",
        (
            "review = dict(checks=[], sentence_grammar_inventory=[], violations=[], "
            "machine_check_disputes=[], verdict='pass')"
        ),
        (
            "machine = {}\n"
            "machine['violations'] = [dict(code='V-LEX-02', location='x')]"
        ),
        (
            "review = {}\n"
            "review.update(dict(checks=[]))\n"
            "review['sentence_grammar_inventory'] = []"
        ),
        "candidate = {'body': {}} | {'target': {}}",
        "candidate = {**{'body': {}}, **{'target': {}}}",
        "machine = json.loads('{\"violations\": []}')",
        (
            "machine = {}\n"
            "alias = machine\n"
            "alias['violations'] = []"
        ),
        (
            "machine = {}\n"
            "for key in ('violations',):\n"
            "    machine[key] = []"
        ),
        (
            "machine = {}\n"
            "prefix = 'viola'\n"
            "suffix = 'tions'\n"
            "machine[prefix + suffix] = []"
        ),
        "machine = {key: [] for key in ('violations',)}",
        "machine = dict(zip(('violations',), ([],)))",
        "machine = {}\nmachine.setdefault('violations', [])",
        (
            "PAYLOAD = '{\"violations\": []}'\n"
            "def test_product():\n"
            "    machine = json.loads(PAYLOAD)"
        ),
        (
            "from json import loads as parse_json\n"
            "machine = parse_json('{\"violations\": []}')"
        ),
        "machine = dict.fromkeys(('violations',), [])",
        "machine = json.JSONDecoder().decode('{\"violations\": []}')",
        "machine = json.loads(b'{\"violations\": []}')",
        (
            "PAYLOAD = b'{\"violations\": []}'\n"
            "alias = PAYLOAD\n"
            "machine = unknown_decoder(alias)"
        ),
        (
            "review = load_json(review_path)\n"
            "candidate = load_json(candidate_path)\n"
            "machine = unknown_helper()\n"
            "review_semantic_problems(review, candidate, None, machine)"
        ),
        "write_json(candidate_path, unknown_helper())",
        "write_json(candidate_path, json.loads(unknown_helper().stdout))",
        (
            "def load_json(path):\n"
            "    return unknown_helper()\n"
            "write_json(candidate_path, load_json(candidate_path))"
        ),
    )
    for index, source in enumerate(snippets, start=1):
        assert contract_dict_violations(
            source, f"self-negative-{index}.py", TEST_PRODUCT_CONTRACTS
        )


def test_ci_r_03_contract_origin_meta_test_covers_call_shapes_and_paths() -> None:
    """CI-R-03/R14〜R20: call identityと入力由来をfail-closed化する。"""

    rejected_sources = (
        (
            "from tests.support import write_json\n"
            "write_json(candidate_path, data=unknown_helper())"
        ),
        (
            "from flow_control import review_semantic_problems\n"
            "from tests.support import FIXTURES, load_json\n"
            "review = load_json(FIXTURES / 'reviews' / 'pass_q01_gen1.json')\n"
            "candidate = load_json(FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
            "review_semantic_problems(review=review, candidate=candidate, topic=None, "
            "machine_report=unknown_helper(), grammar_index=None)"
        ),
        (
            "from tests.support import write_json\n"
            "alias = write_json\n"
            "alias(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import load_json, write_json\n"
            "candidate = load_json(path=tmp_path / 'candidate.json')\n"
            "write_json(candidate_path, candidate)"
        ),
        (
            "from tests.support import write_json\n"
            "write_json(**unknown_helper())"
        ),
        (
            "from tests.support import write_json as persist\n"
            "persist(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "alias = write_json if condition else unknown_helper\n"
            "alias(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "write_json(tmp_path / 'x.json', unknown_helper())"
        ),
        (
            "from tests.support import FIXTURES, load_json, write_json\n"
            "load_json = lambda path: unknown_helper()\n"
            "candidate = load_json(FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
            "write_json(candidate_path, candidate)"
        ),
        (
            "from tests import support\n"
            "getattr(support, 'write_json')(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import FIXTURES, load_json, write_json\n"
            "load_json, helper = (lambda path: unknown_helper()), unknown_helper\n"
            "candidate = load_json(FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
            "write_json(candidate_path, candidate)"
        ),
        (
            "from tests.support import FIXTURES, load_json, write_json\n"
            "load_json: object = lambda path: unknown_helper()\n"
            "candidate = load_json(FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
            "write_json(candidate_path, candidate)"
        ),
        (
            "from tests.support import FIXTURES, load_json, write_json\n"
            "(load_json := (lambda path: unknown_helper()))\n"
            "candidate = load_json(FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
            "write_json(candidate_path, candidate)"
        ),
        (
            "from tests.support import write_json\n"
            "sinks = (write_json,)\n"
            "sinks[0](candidate_path, unknown_helper())"
        ),
        (
            "import tests.support as support\n"
            "from tests.support import FIXTURES\n"
            "support.load_json = lambda path: unknown_helper()\n"
            "candidate = support.load_json(FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
            "support.write_json(candidate_path, candidate)"
        ),
        (
            "from tests.support import FIXTURES, load_json, write_json\n"
            "def outer():\n"
            "    load_json = lambda path: unknown_helper()\n"
            "    def inner():\n"
            "        candidate = load_json(FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
            "        write_json(candidate_path, candidate)\n"
            "    return inner"
        ),
        (
            "from tests.support import FIXTURES, load_json, write_json\n"
            "safe = load_json\n"
            "if condition:\n"
            "    load_json = lambda path: unknown_helper()\n"
            "else:\n"
            "    load_json = safe\n"
            "candidate = load_json(FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
            "write_json(candidate_path, candidate)"
        ),
        (
            "from tests.support import machine_for_path, stdout_json, write_json\n"
            "completed = machine_for_path(tmp_path / 'candidate.json', '20990101-000000-r16')\n"
            "write_json(machine_path, stdout_json(completed))"
        ),
        (
            "from tests.support import canonical_bytes, run_cli\n"
            "payload = canonical_bytes({'violations': []})\n"
            "run_cli('scripts/validate.py', '--file', '-', stdin=payload)"
        ),
        (
            "from tests.support import FIXTURES, load_json, write_json\n"
            "safe = load_json\n"
            "try:\n"
            "    load_json = lambda path: unknown_helper()\n"
            "except Exception:\n"
            "    load_json = safe\n"
            "candidate = load_json(FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
            "write_json(candidate_path, candidate)"
        ),
        (
            "from tests.support import write_json\n"
            "globals()['write_json'](candidate_path, unknown_helper())"
        ),
        (
            "import tests.support as support\n"
            "support.__dict__['write_json'](candidate_path, unknown_helper())"
        ),
        (
            "import tests.support as support\n"
            "name = ''.join(('write_', 'json'))\n"
            "getattr(support, name)(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import FIXTURES, load_json, write_json\n"
            "candidate = load_json(FIXTURES.parent.parent / 'data' / 'config' / 'limits.json')\n"
            "write_json(candidate_path, candidate)"
        ),
        (
            "from tests.support import canonical_bytes, run_cli\n"
            "payload = canonical_bytes({''.join(('violations',)): []})\n"
            "run_cli('scripts/validate.py', '--file', '-', stdin=payload)"
        ),
        (
            "from tests.support import FIXTURES, load_json, write_json\n"
            "def replace_loader():\n"
            "    global load_json\n"
            "    load_json = lambda path: unknown_helper()\n"
            "replace_loader()\n"
            "candidate = load_json(FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
            "write_json(candidate_path, candidate)"
        ),
        (
            "import subprocess\n"
            "subprocess.run(['python', 'scripts/validate.py'], check=False)"
        ),
        (
            "import subprocess\n"
            "from tests.support import stdout_json\n"
            "completed = subprocess.CompletedProcess([], 0, b'{}\\n', b'')\n"
            "stdout_json(completed)"
        ),
        (
            "from tests.support import run_cli\n"
            "run_cli('scripts/validate.py', **unknown_helper())"
        ),
        (
            "import subprocess\n"
            "from tests.support import stdout_json\n"
            "completed = subprocess.CompletedProcess(**unknown_helper())\n"
            "stdout_json(completed)"
        ),
        (
            "import contextlib\n"
            "from tests.support import write_json\n"
            "with contextlib.nullcontext(write_json) as persist:\n"
            "    persist(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "persist = next(iter((write_json,)))\n"
            "persist(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "for persist in (write_json,):\n"
            "    persist(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import run_cli\n"
            "def invoke(payload, runner=run_cli):\n"
            "    return runner('scripts/validate.py', '--file', '-', stdin=payload)\n"
            "invoke(unknown_helper())"
        ),
        (
            "from tests.support import run_cli\n"
            "def invoke(payload, *, runner=run_cli):\n"
            "    return runner('scripts/validate.py', '--file', '-', stdin=payload)\n"
            "invoke(unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def persist(data, sink=write_json):\n"
            "    sink(candidate_path, data)\n"
            "persist(unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def get_sink():\n"
            "    return write_json\n"
            "get_sink()(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "class Box:\n"
            "    sink = write_json\n"
            "Box.sink(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def persist(sink, data):\n"
            "    sink(candidate_path, data)\n"
            "persist(write_json, unknown_helper())"
        ),
        (
            "from tests.support import run_cli\n"
            "def invoke(runner, payload):\n"
            "    return runner('scripts/validate.py', '--file', '-', stdin=payload)\n"
            "invoke(run_cli, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def persist(data, *, sink):\n"
            "    sink(candidate_path, data)\n"
            "persist(unknown_helper(), sink=write_json)"
        ),
        (
            "from tests.support import run_cli\n"
            "def invoke(payload, *, runner):\n"
            "    return runner('scripts/validate.py', '--file', '-', stdin=payload)\n"
            "invoke(unknown_helper(), runner=run_cli)"
        ),
        (
            "from tests.support import write_json\n"
            "sink_alias = write_json\n"
            "def persist(sink, data):\n"
            "    sink(candidate_path, data)\n"
            "wrapper = persist\n"
            "wrapper(sink_alias, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def persist(sink, data):\n"
            "    sink(candidate_path, data)\n"
            "arguments = (write_json, unknown_helper())\n"
            "persist(*arguments)"
        ),
        (
            "from tests.support import write_json\n"
            "def persist(*, sink, data):\n"
            "    sink(candidate_path, data)\n"
            "arguments = {'sink': write_json, 'data': unknown_helper()}\n"
            "persist(**arguments)"
        ),
        (
            "from tests.support import write_json\n"
            "def persist(*args):\n"
            "    args[0](candidate_path, args[1])\n"
            "persist(write_json, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def persist(**kwargs):\n"
            "    kwargs['sink'](candidate_path, kwargs['data'])\n"
            "persist(sink=write_json, data=unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def persist(write_json, data):\n"
            "    write_json(candidate_path, data)\n"
            "persist(write_json, unknown_helper())"
        ),
        (
            "import operator\n"
            "from tests.support import write_json\n"
            "operator.call(write_json, candidate_path, unknown_helper())"
        ),
        (
            "import operator\n"
            "from tests.support import run_cli\n"
            "operator.call(run_cli, 'scripts/validate.py', '--file', '-', "
            "stdin=unknown_helper())"
        ),
        (
            "import itertools\n"
            "from tests.support import write_json\n"
            "list(itertools.starmap(write_json, "
            "[(candidate_path, unknown_helper())]))"
        ),
        (
            "from tests.support import write_json\n"
            "write_json.__call__(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "getattr(write_json, '__call__')(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "calls = [write_json]\n"
            "[fn] = calls\n"
            "fn(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "calls = [write_json]\n"
            "fn = calls.pop()\n"
            "fn(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def choose():\n"
            "    return (write_json,)\n"
            "choose()[0](candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "calls = {'sink': write_json}\n"
            "fn, = calls.values()\n"
            "fn(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "calls = [write_json]\n"
            "fn = calls.unknown_extract()\n"
            "fn(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "calls = [write_json]\n"
            "for fn in calls:\n"
            "    fn(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "calls = {'sink': write_json}\n"
            "(key, fn), = calls.items()\n"
            "fn(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def choose():\n"
            "    calls = (write_json,)\n"
            "    return calls\n"
            "choose()[0](candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "calls = {'sink': write_json}\n"
            "fn = next(iter(calls.values()))\n"
            "fn(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "calls = {'sink': write_json}\n"
            "next(iter(calls.items()))[1](candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "calls = {'sink': write_json}\n"
            "view = calls.items()\n"
            "(key, fn), = view\n"
            "fn(candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def choose(flag):\n"
            "    if flag:\n"
            "        calls = (write_json,)\n"
            "    else:\n"
            "        calls = (write_json,)\n"
            "    return calls\n"
            "choose(True)[0](candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def choose_try():\n"
            "    try:\n"
            "        calls = (write_json,)\n"
            "    except Exception:\n"
            "        calls = (write_json,)\n"
            "    return calls\n"
            "choose_try()[0](candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def choose_match(flag):\n"
            "    match flag:\n"
            "        case True:\n"
            "            calls = (write_json,)\n"
            "        case _:\n"
            "            calls = (write_json,)\n"
            "    return calls\n"
            "choose_match(True)[0](candidate_path, unknown_helper())"
        ),
        (
            "from tests.support import write_json\n"
            "def choose_loop(flag):\n"
            "    calls = (write_json,)\n"
            "    while flag:\n"
            "        calls = (write_json,)\n"
            "    return calls\n"
            "choose_loop(True)[0](candidate_path, unknown_helper())"
        ),
    )
    for index, source in enumerate(rejected_sources, start=1):
        assert contract_dict_violations(
            source, f"origin-negative-{index}.py", TEST_PRODUCT_CONTRACTS
        )

    approved_source = (
        "from flow_control import review_semantic_problems\n"
        "from tests.support import (FIXTURES, canonical_bytes, load_json, "
        "machine_for_path, run_cli, stdout_json, write_json)\n"
        "review = load_json(FIXTURES / 'reviews' / 'pass_q01_gen1.json')\n"
        "candidate = load_json(path=FIXTURES / 'candidates' / 'replay_q01_pass.json')\n"
        "persist = write_json\n"
        "persist(candidate_path, candidate)\n"
        "import tests.support as support\n"
        "writers = (getattr(support, 'write_json'),)\n"
        "writers[0](candidate_path, candidate)\n"
        "list_calls = [write_json]\n"
        "[list_writer] = list_calls\n"
        "list_writer(candidate_path, candidate)\n"
        "pop_calls = [write_json]\n"
        "pop_writer = pop_calls.pop()\n"
        "pop_writer(candidate_path, candidate)\n"
        "def choose_writer():\n"
        "    return (write_json,)\n"
        "choose_writer()[0](candidate_path, candidate)\n"
        "dict_calls = {'sink': write_json}\n"
        "dict_writer, = dict_calls.values()\n"
        "dict_writer(candidate_path, candidate)\n"
        "loop_calls = [write_json]\n"
        "for loop_writer in loop_calls:\n"
        "    loop_writer(candidate_path, candidate)\n"
        "item_calls = {'sink': write_json}\n"
        "(item_key, item_writer), = item_calls.items()\n"
        "item_writer(candidate_path, candidate)\n"
        "def choose_bound_writer():\n"
        "    bound_calls = (write_json,)\n"
        "    return bound_calls\n"
        "choose_bound_writer()[0](candidate_path, candidate)\n"
        "nested_calls = {'sink': write_json}\n"
        "nested_writer = next(iter(nested_calls.values()))\n"
        "nested_writer(candidate_path, candidate)\n"
        "nested_item_calls = {'sink': write_json}\n"
        "next(iter(nested_item_calls.items()))[1](candidate_path, candidate)\n"
        "view_calls = {'sink': write_json}\n"
        "view = view_calls.items()\n"
        "(view_key, view_writer), = view\n"
        "view_writer(candidate_path, candidate)\n"
        "def choose_branched_writer(flag):\n"
        "    if flag:\n"
        "        branched_calls = (write_json,)\n"
        "    else:\n"
        "        branched_calls = (write_json,)\n"
        "    return branched_calls\n"
        "choose_branched_writer(True)[0](candidate_path, candidate)\n"
        "def choose_try_writer():\n"
        "    try:\n"
        "        try_calls = (write_json,)\n"
        "    except Exception:\n"
        "        try_calls = (write_json,)\n"
        "    return try_calls\n"
        "choose_try_writer()[0](candidate_path, candidate)\n"
        "def choose_match_writer(flag):\n"
        "    match flag:\n"
        "        case True:\n"
        "            match_calls = (write_json,)\n"
        "        case _:\n"
        "            match_calls = (write_json,)\n"
        "    return match_calls\n"
        "choose_match_writer(True)[0](candidate_path, candidate)\n"
        "def choose_loop_writer(flag):\n"
        "    loop_bound_calls = (write_json,)\n"
        "    while flag:\n"
        "        loop_bound_calls = (write_json,)\n"
        "    return loop_bound_calls\n"
        "choose_loop_writer(True)[0](candidate_path, candidate)\n"
        "def approved_writer(sink, data):\n"
        "    sink(candidate_path, data)\n"
        "approved_writer(write_json, candidate)\n"
        "completed = machine_for_path(FIXTURES / 'candidates' / 'replay_q01_pass.json', "
        "'20990101-000000-r16')\n"
        "writers[0](machine_path, stdout_json(completed))\n"
        "run_cli('scripts/validate.py', '--schema', 'candidate', '--file', '-', "
        "stdin=canonical_bytes(candidate))\n"
        "review_semantic_problems(review=review, candidate=candidate, topic=None)"
    )
    assert (
        contract_dict_violations(
            approved_source, "origin-approved.py", TEST_PRODUCT_CONTRACTS
        )
        == []
    )


def test_ci_fix_01_all_documented_layer_test_ids_are_traced() -> None:
    """CI-FIX-01/TST-08: 第1層・第2層の全テストIDを関数名かdocstringへ追跡する。"""

    pattern = re.compile(r"(?:CI-[A-Z]+-\d{2}|RPL-\d{2})")
    specification = (ROOT / "docs" / "testing-and-acceptance.md").read_text(
        encoding="utf-8"
    )
    layer_sections = specification[
        specification.index("## 2.") : specification.index("## 4.")
    ]
    required = set(pattern.findall(layer_sections))
    documented = set(pattern.findall(specification))
    implemented: set[str] = set()
    untraced_functions: list[str] = []
    for path in sorted(
        [*(ROOT / "tests" / "unit").glob("*.py"), *(ROOT / "tests" / "replay").glob("*.py")]
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            function_ids = set(
                pattern.findall(f"{node.name} {ast.get_docstring(node) or ''}")
            )
            if not function_ids:
                untraced_functions.append(
                    f"{path.relative_to(ROOT).as_posix()}:{node.lineno}:{node.name}"
                )
            implemented.update(function_ids)
    assert untraced_functions == []
    assert required - implemented == set()
    assert implemented - documented == set()


def test_ci_fix_01_fixture_canonical_form() -> None:
    """CI-FIX-01: JSON fixtureをUTF-8・BOMなし・LF・正準インデントで保存する。"""

    intentional_raw = {
        FIXTURES / "reviews" / "invalid_json.json",
        FIXTURES / "reviews" / "invalid_surrogate.json",
    }
    huge = set((FIXTURES / "candidates").glob("mch_18_integer_*.json"))
    for path in FIXTURES.rglob("*.json"):
        payload = path.read_bytes()
        assert not payload.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in payload
        assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
        if path in intentional_raw:
            continue
        if path in huge:
            matches = list(
                re.finditer(
                    rb'(?m)^  "unexpected_m8_integer": ([0-9]+)$',
                    payload,
                )
            )
            assert len(matches) == 1
            match = matches[0]
            digits = match.group(1)
            placeholder = b'"__M8_HUGE_INTEGER__"'
            parseable = (
                payload[: match.start(1)]
                + placeholder
                + payload[match.end(1) :]
            )
            expected = canonical_bytes(json.loads(parseable)).replace(
                placeholder, digits
            )
            assert payload == expected
            continue
        assert payload == canonical_bytes(json.loads(payload))


def test_ci_fix_01_candidate_and_review_schema_contracts() -> None:
    """CI-FIX-01: 意図した不当例以外の候補・レビューfixtureが各スキーマに合格する。"""

    candidate_validator = Draft202012Validator(load_json(ROOT / "schemas" / "candidate.schema.json"))
    review_validator = Draft202012Validator(load_json(ROOT / "schemas" / "review_result.schema.json"))
    candidate_exceptions = {
        "mch_18_integer_4300.json": ("CI-MCH-18",),
        "mch_18_integer_4301.json": ("CI-MCH-18",),
        "mch_18_integer_5000.json": ("CI-MCH-18",),
        "rpl_06_missing_question_id.json": ("RPL-06",),
        "rpl_06_question_id_type.json": ("RPL-06",),
        "sch_04_inconsistent_format.json": ("CI-SCH-04",),
    }
    review_exceptions = {
        "invalid_json.json": ("RPL-05",),
        "invalid_schema.json": ("RPL-05",),
        "invalid_surrogate.json": ("RPL-05",),
    }

    class SchemaInteger(int):
        def __repr__(self) -> str:
            return "<unbounded JSON integer>"

    def parse_unbounded_json_integer(value: str) -> int:
        sign = -1 if value.startswith("-") else 1
        digits = value.removeprefix("-")
        result = 0
        for offset in range(0, len(digits), 1000):
            chunk = digits[offset : offset + 1000]
            result = result * (10 ** len(chunk)) + int(chunk)
        return SchemaInteger(sign * result)

    def assert_schema_invalid(path: Path, validator: Draft202012Validator) -> None:
        try:
            instance = load_json(path)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        except ValueError as exc:
            assert "Exceeds the limit" in str(exc), path.name
            instance = json.loads(
                path.read_text(encoding="utf-8"),
                parse_int=parse_unbounded_json_integer,
            )
        assert not validator.is_valid(instance), path.name

    seen_candidate_exceptions: set[str] = set()
    for case in load_json(FIXTURES / "candidates" / "index.json")["cases"]:
        path = FIXTURES / "candidates" / case["file"]
        expected_test_ids = candidate_exceptions.get(path.name)
        if expected_test_ids is not None:
            assert tuple(case["test_ids"]) == expected_test_ids
            assert_schema_invalid(path, candidate_validator)
            seen_candidate_exceptions.add(path.name)
            continue
        candidate_validator.validate(load_json(path))
    assert seen_candidate_exceptions == set(candidate_exceptions)

    seen_review_exceptions: set[str] = set()
    for case in load_json(FIXTURES / "reviews" / "index.json")["cases"]:
        path = FIXTURES / "reviews" / case["file"]
        expected_test_ids = review_exceptions.get(path.name)
        if expected_test_ids is not None:
            assert tuple(case["test_ids"]) == expected_test_ids
            assert_schema_invalid(path, review_validator)
            seen_review_exceptions.add(path.name)
            continue
        review_validator.validate(load_json(path))
    assert seen_review_exceptions == set(review_exceptions)


def test_ci_fix_01_replay_pass_reviews_have_complete_known_grammar_inventory() -> None:
    """CI-FIX-01/R8-01: 全pass/fail reviewが固定候補の既知全文法構造を列挙する。"""

    has_estimate = (
        "時制・相(現在)(主動詞have・3人称単数)",
        "reviewer_estimate: 主動詞haveの3人称単数現在形hasは、"
        "基本的な所有・状態を表す現在時制として導入レベルをA1.1と推定しました。",
    )
    known = {
        "q01": frozenset(
            {
                ("gp:6", "kyoinban", "your", "A1.1-A1.2"),
                ("gp:69", "kyoinban", "will accept", "A1.2-A1.3"),
                ("gp:141", "kyoinban", "will accept", "A1.2-A2.2"),
                (
                    "gp:196",
                    "kyoinban",
                    "I will accept your plan today.",
                    "A1.1-A2.2",
                ),
            }
        ),
        "q02": frozenset(
            {
                ("gp:7", "kyoinban", "us", "A1.1-A1.2"),
                ("gp:14", "kyoinban", "the", "A1.1"),
                ("gp:88", "kyoinban", "to help", "A1.1-A2.2"),
                (
                    "gp:196",
                    "kyoinban",
                    "She has the ability to help us.",
                    "A1.1-A2.2",
                ),
                (None, "reviewer_estimate", "has", "A1.1"),
            }
        ),
        "q03": frozenset(
            {
                ("gp:6", "kyoinban", "My", "A1.1-A1.2"),
                ("gp:69", "kyoinban", "will study", "A1.2-A1.3"),
                ("gp:141", "kyoinban", "will study", "A1.2-A2.2"),
                (
                    "gp:194",
                    "kyoinban",
                    "My sister will study abroad next year.",
                    "A1.1-A2.2",
                ),
            }
        ),
        "q04": frozenset(
            {
                ("gp:6", "kyoinban", "my", "A1.1-A1.2"),
                ("gp:21", "kyoinban", "to dinner", "A1.1-A2.2"),
                ("gp:69", "kyoinban", "will invite", "A1.2-A1.3"),
                ("gp:141", "kyoinban", "will invite", "A1.2-A2.2"),
                (
                    "gp:196",
                    "kyoinban",
                    "I will invite my friend to dinner.",
                    "A1.1-A2.2",
                ),
            }
        ),
        "q05": frozenset(
            {
                ("gp:6", "kyoinban", "our", "A1.1-A1.2"),
                ("gp:123", "kyoinban", "can achieve", "A1.2-A2.2"),
                (
                    "gp:196",
                    "kyoinban",
                    "We can achieve our goal this year.",
                    "A1.1-A2.2",
                ),
            }
        ),
        "q06": frozenset(
            {
                ("gp:11", "kyoinban", "this school", "A1.1-A1.2"),
                ("gp:21", "kyoinban", "at this school", "A1.1-A2.2"),
                ("gp:59", "kyoinban", "advise", "A1.1"),
                (
                    "gp:196",
                    "kyoinban",
                    "They advise students at this school.",
                    "A1.1-A2.2",
                ),
            }
        ),
        "conflict": frozenset(
            {
                ("gp:6", "kyoinban", "your", "A1.1-A1.2"),
                ("gp:59", "kyoinban", "accept", "A1.1"),
                ("gp:196", "kyoinban", "I accept your ability.", "A1.1-A2.2"),
            }
        ),
        "machine_fail": frozenset(
            {
                ("gp:11", "kyoinban", "this book", "A1.1-A1.2"),
                ("gp:59", "kyoinban", "abandon", "A1.1"),
                ("gp:196", "kyoinban", "I abandon this book.", "A1.1-A2.2"),
            }
        ),
    }
    pass_reviews = sorted((FIXTURES / "reviews").glob("pass*.json"))
    fail_reviews = sorted((FIXTURES / "reviews").glob("fail_q*.json"))
    assert len(pass_reviews) == 23
    assert len(fail_reviews) == 18
    grammar = load_json(ROOT / "data" / "normalized" / "grammar.json")
    grammar_index = {item["id"]: item for item in grammar["entries"]}
    for path in [*pass_reviews, *fail_reviews]:
        if path.name.startswith("pass_conflict_"):
            expected = known["conflict"]
            question_id = path.name.split("_")[2]
            candidate_name = f"replay_{question_id}_conflict.json"
        elif path.name.startswith("pass_machine_fail_"):
            expected = known["machine_fail"]
            candidate_name = "mch_06_high_level_abandon.json"
        else:
            question_id = path.name[5:8]
            expected = known[question_id]
            candidate_name = f"replay_{question_id}_pass.json"
        review = load_json(path)
        candidate = load_json(FIXTURES / "candidates" / candidate_name)
        actual = frozenset(
            (
                item["grammar_item_id"],
                item["level_source"],
                item["span"],
                item["level"],
            )
            for item in review["sentence_grammar_inventory"]
        )
        if path.name.startswith("pass"):
            assert actual == expected, path.name
        else:
            assert expected < actual, path.name
        for item in review["sentence_grammar_inventory"]:
            assert item["structure"] and item["evidence"]
            if (
                item["grammar_item_id"],
                item["level_source"],
                item["span"],
                item["level"],
            ) == (None, "reviewer_estimate", "has", "A1.1"):
                assert (item["structure"], item["evidence"]) == has_estimate
        assert not review_semantic_problems(
            review,
            candidate,
            None,
            grammar_index=grammar_index,
        ), path.name


def test_ci_fix_01_no_personal_fixture_data() -> None:
    """CI-FIX-01: fixtureとgolden caseに個人メールアドレスを含めない。"""

    email = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    paths = [*FIXTURES.rglob("*"), *(GOLDEN / "cases").glob("*.json")]
    assert not [path for path in paths if path.is_file() and email.search(path.read_bytes())]


def test_ci_fix_01_golden_cases_machine_pass() -> None:
    """CI-FIX-01: GLD-05の2候補がcandidateスキーマとmachine検査に合格する。"""

    validator = Draft202012Validator(load_json(ROOT / "schemas" / "candidate.schema.json"))
    for name in GOLDEN_CASE_FILES:
        path = GOLDEN / "cases" / name
        validator.validate(load_json(path))
        completed = machine_for_path(path, "20990101-090909-fix1")
        assert completed.returncode == 0, completed.stderr.decode()
        assert json.loads(completed.stdout)["verdict"] == "pass"
