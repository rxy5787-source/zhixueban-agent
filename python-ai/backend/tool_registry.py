"""Schema, authorization and execution boundary for educational tools."""
from __future__ import annotations

from dataclasses import dataclass
import math
import multiprocessing
from pathlib import Path
import re
import time
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError
from requests import RequestException, Timeout


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', allow_inf_nan=False)


@dataclass(frozen=True)
class ToolContext:
    """Constructed by the host from its authenticated task and scoped Store."""

    root: Path
    owner: str
    library_id: str
    file_ids: frozenset[str]
    capabilities: frozenset[str]
    job_id: str | None = None
    preferred_difficulty: Literal['auto', 'basic', 'intermediate', 'advanced'] = 'auto'
    preferred_question_count: int = 0


class ToolFailure(Exception):
    def __init__(self, code: Literal['resource_unavailable', 'insufficient_evidence', 'invalid_candidate']):
        self.code = code


class ToolResult(Contract):
    status: Literal['ok', 'rejected', 'retryable_error', 'fatal_error']
    code: str | None = None
    data: dict[str, JsonValue] | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_type: type[Contract]
    output_type: type[Contract]
    capability: str
    timeout: float
    handler: Callable[[ToolContext, Contract], dict]


def _run_handler(sender, spec, context, args):
    with sender:
        try:
            value = spec.handler(context, args)
        except ToolFailure as exc:
            result = ToolResult(status='rejected', code=exc.code)
        except Timeout:
            result = ToolResult(status='retryable_error', code='timeout')
        except RequestException:
            result = ToolResult(status='retryable_error', code='model_unavailable')
        except Exception:
            result = ToolResult(status='fatal_error', code='tool_failed')
        else:
            try:
                data = spec.output_type.model_validate(value).model_dump(mode='json')
                result = ToolResult(status='ok', data=data)
                if len(result.model_dump_json().encode('utf-8')) > 96_000:
                    result = ToolResult(status='fatal_error', code='output_limit')
            except (ValueError, TypeError):
                result = ToolResult(status='fatal_error', code='invalid_output')
        sender.send_bytes(result.model_dump_json().encode('utf-8'))


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if (not re.fullmatch(r'[a-z][a-z_0-9]{0,63}', spec.name)
                or spec.name in self._tools or not math.isfinite(spec.timeout)
                or not 0 < spec.timeout <= 300):
            raise ValueError('Invalid or duplicate tool registration')
        self._tools[spec.name] = spec

    def catalog(self, context: ToolContext) -> list[dict]:
        return [
            {'name': spec.name, 'description': spec.description,
             'inputSchema': spec.input_type.model_json_schema()}
            for spec in self._tools.values() if spec.capability in context.capabilities
        ]

    def execute(self, context: ToolContext, name: str, arguments: dict, *,
                cancelled=lambda: False, deadline: float | None = None) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None or spec.capability not in context.capabilities:
            return ToolResult(status='rejected', code='tool_not_allowed')
        try:
            args = spec.input_type.model_validate(arguments)
        except ValidationError:
            return ToolResult(status='rejected', code='invalid_arguments')
        if cancelled():
            return ToolResult(status='rejected', code='cancelled')
        limit = time.monotonic() + spec.timeout
        if deadline is not None:
            limit = min(limit, deadline)
        if time.monotonic() >= limit:
            return ToolResult(status='retryable_error', code='timeout')
        return self._execute_process(spec, context, args, cancelled, limit)

    @staticmethod
    def _execute_process(spec, context, args, cancelled, limit):
        spawn = multiprocessing.get_context('spawn')
        reader, writer = spawn.Pipe(duplex=False)
        child = spawn.Process(target=_run_handler, args=(writer, spec, context, args), daemon=True)
        with reader, writer:
            try:
                child.start()
                writer.close()
                while (remaining := limit - time.monotonic()) > 0:
                    if cancelled():
                        return ToolResult(status='rejected', code='cancelled')
                    if reader.poll(min(remaining, 0.05)):
                        result = ToolResult.model_validate_json(reader.recv_bytes(96_000))
                        if cancelled():
                            return ToolResult(status='rejected', code='cancelled')
                        if time.monotonic() >= limit:
                            break
                        return result
                    if not child.is_alive():
                        return ToolResult(status='fatal_error', code='tool_failed')
                return ToolResult(status='retryable_error', code='timeout')
            except (OSError, EOFError, RuntimeError, ValidationError):
                return ToolResult(status='fatal_error', code='tool_failed')
            finally:
                if child.pid is not None:
                    child.join(timeout=0.05)
                    if child.is_alive():
                        child.kill()
                        child.join()
                    child.close()
