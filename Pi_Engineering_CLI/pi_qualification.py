"""Operator-invoked, read-only contract checks for configured MCP services."""
import asyncio
import json
from pathlib import Path
import time
import uuid

from jsonschema import Draft202012Validator
from pydantic import Field

from pi_tools import ToolBroker
from pi_workspace import StrictModel, UserError, canonical, fingerprint


class Probe(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    tool: str = Field(min_length=1, max_length=128)
    arguments: dict
    input_schema_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    response_schema: dict


class Contract(StrictModel):
    version: int = Field(default=1, ge=1, le=1)
    probes: list[Probe] = Field(min_length=1, max_length=32)


async def qualify(workspace, path, broker_factory=ToolBroker):
    path = Path(path)
    try:
        with path.open("rb") as stream:
            data = stream.read(256001)
    except OSError as exc:
        raise UserError("Cannot read integration contract; check its path and file permissions") from exc
    if len(data) > 256000:
        raise UserError("Integration contract exceeds 256 KB")
    try:
        contract = Contract.model_validate_json(data)
    except ValueError as exc:
        raise UserError("Invalid integration contract; check probe fields and schema hashes") from exc
    if len({p.name for p in contract.probes}) != len(contract.probes):
        raise UserError("Integration probe names must be unique")
    config = workspace.config()
    report = {"id": "qualification_" + uuid.uuid4().hex[:16], "created": time.time(),
              "contract_hash": fingerprint(contract.model_dump()),
              "config_hash": fingerprint(config.model_dump()), "status": "passed", "probes": []}
    async with asyncio.timeout(300):
        async with broker_factory(workspace, config, [p.tool for p in contract.probes]) as broker:
            # Validate the whole contract before dispatching even the first read.
            for probe in contract.probes:
                broker.validate(probe.tool, probe.arguments)
                tool = broker.tools[probe.tool]
                if tool["server"] == "local" or not tool["read"]:
                    raise UserError("Qualification permits only MCP tools explicitly classified as reads")
                if fingerprint(tool["inputSchema"]) != probe.input_schema_sha256:
                    raise UserError(f"Input schema drift for probe {probe.name}; review the new schema")
                Draft202012Validator.check_schema(probe.response_schema)
                # Remote references could cause extra network requests with sensitive context.
                pending = [probe.response_schema]
                while pending:
                    item = pending.pop()
                    if isinstance(item, dict):
                        for key in ("$ref", "$dynamicRef"):
                            if key in item and not item[key].startswith("#"):
                                raise UserError("Response schemas must use local references only")
                        pending.extend(item.values())
                    elif isinstance(item, list):
                        pending.extend(item)
            for probe in contract.probes:
                if fingerprint(workspace.config().model_dump()) != report["config_hash"]:
                    raise UserError("Configuration changed during qualification")
                started = time.monotonic()
                row = {"name": probe.name, "tool": probe.tool, "passed": False}
                try:
                    result = await broker.call(probe.tool, probe.arguments)
                    Draft202012Validator(probe.response_schema).validate(result["server_response"])
                    row.update(passed=True, result_hash=fingerprint(result))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # Never include customer observations, arguments or credential-bearing errors.
                    row["error_type"] = type(exc).__name__
                    report["status"] = "failed"
                row["seconds"] = round(time.monotonic() - started, 3)
                report["probes"].append(row)
    with workspace.database() as db:
        db.execute("INSERT INTO events(task_id,kind,body,created) VALUES(?,?,?,?)",
                   (report["id"], "integration_qualification", canonical(report), time.time()))
    return report
