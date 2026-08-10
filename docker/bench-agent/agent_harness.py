#!/usr/bin/env python3
"""Executable tool loop and scoring primitives for bench-agent."""

from __future__ import annotations

import json
import math
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ToolExecutionError(RuntimeError):
    """Expected tool failure returned to the model as an observation."""


@dataclass
class ToolState:
    sandbox: Path
    attempts: dict[str, int] = field(default_factory=dict)


def public_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in tool.items() if not key.startswith("x-")}


def validate_arguments(arguments: Any, schema: dict[str, Any]) -> list[str]:
    if not isinstance(arguments, dict):
        return ["arguments must be a JSON object"]
    errors: list[str] = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    for name in required:
        if name not in arguments:
            errors.append(f"missing required argument: {name}")
    if schema.get("additionalProperties") is False:
        for name in arguments:
            if name not in properties:
                errors.append(f"unexpected argument: {name}")
    expected_types = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for name, value in arguments.items():
        spec = properties.get(name)
        if not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        python_type = expected_types.get(expected)
        if python_type and (not isinstance(value, python_type) or expected in ("number", "integer") and isinstance(value, bool)):
            errors.append(f"argument {name} must be {expected}")
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"argument {name} must be one of {spec['enum']}")
    return errors


def _lookup_metric(arguments: dict[str, Any]) -> dict[str, Any]:
    dataset = str(arguments.get("dataset", "")).lower()
    metric = str(arguments.get("metric", "")).lower()
    location = str(arguments.get("location", "")).upper()
    year = int(arguments.get("year", 2024))
    fixtures = {
        ("climate", "temperature", "CAN", 2024): (12.5, "celsius"),
        ("climate", "temperature", "USA", 2024): (13.9, "celsius"),
        ("demography", "population", "USA", 2024): (340_000_000, "people"),
    }
    value = fixtures.get((dataset, metric, location, year))
    if value is None:
        raise ToolExecutionError("metric_not_found")
    return {
        "dataset": dataset,
        "metric": metric,
        "location": location,
        "year": year,
        "value": value[0],
        "unit": value[1],
    }


def _convert_units(arguments: dict[str, Any]) -> dict[str, Any]:
    value = float(arguments["value"])
    source = str(arguments["from_unit"]).lower()
    target = str(arguments["to_unit"]).lower()
    if (source, target) == ("celsius", "fahrenheit"):
        converted = value * 9 / 5 + 32
    elif (source, target) == ("fahrenheit", "celsius"):
        converted = (value - 32) * 5 / 9
    elif source == target:
        converted = value
    else:
        raise ToolExecutionError("unsupported_conversion")
    return {"value": round(converted, 4), "unit": target}


def _safe_artifact_path(sandbox: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in (".", ".."):
        raise ToolExecutionError("invalid_artifact_name")
    path = (sandbox / name).resolve()
    if path.parent != sandbox.resolve():
        raise ToolExecutionError("artifact_path_outside_sandbox")
    return path


def execute_tool(tool: dict[str, Any], arguments: dict[str, Any], state: ToolState) -> dict[str, Any]:
    mapped = dict(arguments)
    for public_name, executor_name in tool.get("x-arg-map", {}).items():
        if public_name in mapped:
            mapped[executor_name] = mapped.pop(public_name)
    executor = str(tool.get("x-executor", tool.get("function", {}).get("name", "")))
    if executor == "lookup_metric":
        result = _lookup_metric(mapped)
    elif executor == "convert_units":
        result = _convert_units(mapped)
    elif executor == "list_datasets":
        result = {"datasets": ["climate", "demography"]}
    elif executor == "write_artifact":
        path = _safe_artifact_path(state.sandbox, str(mapped["name"]))
        path.write_text(str(mapped["content"]), encoding="utf-8")
        result = {"written": True, "name": path.name, "bytes": path.stat().st_size}
    elif executor == "read_artifact":
        path = _safe_artifact_path(state.sandbox, str(mapped["name"]))
        if not path.exists():
            raise ToolExecutionError("artifact_not_found")
        result = {"name": path.name, "content": path.read_text(encoding="utf-8")}
    elif executor == "unstable_lookup":
        attempts = state.attempts.get(executor, 0) + 1
        state.attempts[executor] = attempts
        if attempts == 1:
            raise ToolExecutionError("transient_backend_error; retry with retry_token=retry-ok")
        if mapped.get("retry_token") != "retry-ok":
            raise ToolExecutionError("invalid_retry_token")
        result = _lookup_metric(mapped)
    else:
        raise ToolExecutionError(f"executor_not_found:{executor}")

    shape = tool.get("x-return-shape", "default")
    if shape == "nested_result":
        return {"ok": True, "result": {"payload": result}}
    if shape == "renamed_fields" and "value" in result:
        return {"ok": True, "measurement": result["value"], "measurement_unit": result.get("unit")}
    return {"ok": True, **result}


def chat_completion(base_url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        decoded = json.loads(response.read())
    choices = decoded.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("chat completion response missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("chat completion response missing message")
    return message


def parse_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    calls = message.get("tool_calls", [])
    if calls is None:
        return []
    if not isinstance(calls, list):
        raise RuntimeError("message.tool_calls must be an array")
    return [call for call in calls if isinstance(call, dict)]


def _contains_all(text: str, needles: list[str]) -> bool:
    normalized = text.lower()
    return all(str(needle).lower() in normalized for needle in needles)


def score_plan(case: dict[str, Any], final_text: str) -> dict[str, Any]:
    cursor = 0
    normalized = final_text.lower()
    matched = 0
    for term in case.get("expected", {}).get("ordered_terms", []):
        index = normalized.find(str(term).lower(), cursor)
        if index < 0:
            continue
        matched += 1
        cursor = index + len(str(term))
    total = len(case.get("expected", {}).get("ordered_terms", []))
    score = matched / total if total else 0.0
    return {"plan_correctness": score, "final_task_success": float(math.isclose(score, 1.0))}


def score_execution(case: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    calls = trace["calls"]
    expected = case.get("expected", {})
    called_names = [call["name"] for call in calls]
    required = expected.get("required_tools", [])
    forbidden = expected.get("forbidden_tools", [])
    selection_ok = all(name in called_names for name in required) and not any(name in called_names for name in forbidden)
    if expected.get("no_tool"):
        selection_ok = not calls
    schema_score = sum(call["schema_valid"] for call in calls) / len(calls) if calls else float(expected.get("no_tool", False))
    valid_calls = [call for call in calls if call["schema_valid"]]
    execution_score = sum(call["executed"] for call in valid_calls) / len(valid_calls) if valid_calls else float(expected.get("no_tool", False))
    final_contains = expected.get("final_contains", [])
    observation_score = float(_contains_all(trace["final_text"], final_contains)) if final_contains else 1.0
    error_seen = any(call.get("error") for call in calls)
    success_after_error = False
    if error_seen:
        first_error = next(index for index, call in enumerate(calls) if call.get("error"))
        success_after_error = any(call["executed"] for call in calls[first_error + 1 :])
    recovery_expected = bool(expected.get("recovery"))
    recovery_score = float(success_after_error) if recovery_expected else 1.0
    expected_arguments = expected.get("expected_arguments", {})
    argument_score = 1.0
    if expected_arguments:
        matched = 0
        for tool_name, wanted in expected_arguments.items():
            found = any(
                call["name"] == tool_name
                and call.get("schema_valid")
                and all(call.get("parsed_arguments", {}).get(key) == value for key, value in wanted.items())
                for call in calls
            )
            matched += int(found)
        argument_score = matched / len(expected_arguments)
    final_success = selection_ok and argument_score == 1.0 and observation_score == 1.0 and recovery_score == 1.0
    if required:
        final_success = final_success and all(
            any(call["name"] == name and call["executed"] for call in calls) for name in required
        )
    scores = {
        "tool_selection": float(selection_ok),
        "schema_validity": schema_score,
        "execution_success": execution_score,
        "observation_interpretation": observation_score,
        "final_task_success": float(final_success),
    }
    if expected_arguments:
        scores["argument_accuracy"] = argument_score
    if recovery_expected:
        scores["recovery_success"] = recovery_score
    return scores


def run_case(
    *,
    case: dict[str, Any],
    base_url: str,
    model: str,
    sandbox: Path,
    timeout: int,
    max_steps: int,
    max_tokens: int,
) -> dict[str, Any]:
    sandbox.mkdir(parents=True, exist_ok=True)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "Use only the current tool definitions. Treat tool observations as authoritative. Finish with a concise answer.",
        },
        {"role": "user", "content": f"Case {case['id']}: {case['prompt']}"},
    ]
    tools = case.get("tools", []) if case.get("mode", "execute") == "execute" else []
    tool_by_name = {tool["function"]["name"]: tool for tool in tools}
    state = ToolState(sandbox=sandbox)
    trace: dict[str, Any] = {"case_id": case["id"], "calls": [], "messages": [], "final_text": ""}

    for _ in range(max_steps):
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = [public_tool(tool) for tool in tools]
            payload["tool_choice"] = "auto"
        message = chat_completion(base_url, payload, timeout)
        trace["messages"].append(message)
        calls = parse_tool_calls(message)
        if not calls:
            final_text = str(message.get("content") or message.get("reasoning_content") or "").strip()
            trace["final_text"] = final_text
            break

        messages.append(
            {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": calls,
            }
        )
        for index, call in enumerate(calls):
            function = call.get("function", {})
            name = str(function.get("name", ""))
            call_id = str(call.get("id", f"call-{len(trace['calls'])}-{index}"))
            raw_arguments = function.get("arguments", "{}")
            record = {"name": name, "arguments": raw_arguments, "schema_valid": False, "executed": False, "error": ""}
            tool = tool_by_name.get(name)
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                record["parsed_arguments"] = arguments
                if tool is None:
                    raise ToolExecutionError("unknown_tool")
                errors = validate_arguments(arguments, tool["function"].get("parameters", {}))
                if errors:
                    raise ToolExecutionError("; ".join(errors))
                record["schema_valid"] = True
                observation = execute_tool(tool, arguments, state)
                record["executed"] = True
            except (json.JSONDecodeError, ToolExecutionError, KeyError, TypeError, ValueError) as exc:
                record["error"] = str(exc)
                observation = {"ok": False, "error": str(exc)}
            trace["calls"].append(record)
            messages.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": json.dumps(observation)})
    else:
        trace["final_text"] = ""
        trace["max_steps_exceeded"] = True

    if case.get("mode", "execute") == "plan":
        scores = score_plan(case, trace["final_text"])
    else:
        scores = score_execution(case, trace)
    trace["scores"] = scores
    trace["score"] = sum(scores.values()) / len(scores) if scores else 0.0
    return trace
