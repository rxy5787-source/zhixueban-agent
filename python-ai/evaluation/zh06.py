"""ZH-06: run the repository's 20 existing study cases against a local trial service.

No fake model calls, fabricated scores or network access during import/plan/report.
"run" requires --confirm-live and permits loopback HTTP only.
Raw task responses and review notes remain on the user's machine; do not commit them.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import re
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from http.cookiejar import MozillaCookieJar
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "docs" / "STUDY_GENERATION_EVAL.md"
DEFAULT_SQL = ROOT / "web-prototype" / "test-materials" / "SQL短文本资料.txt"
DEFAULT_OUTPUT = ROOT / "web-prototype" / ".verification" / "zh06-eval"
TERMINAL = {"succeeded", "partial", "failed", "cancelled", "interrupted"}
KIND = {
    "口诀": "mnemonic", "问答": "reply", "填空": "cloze",
    "选择题": "single_choice", "基础选择题": "single_choice", "缺失依据": "reply",
}
CSV_FIELDS = [
    "case_id", "kind", "source_group", "task_status", "artifact",
    "reviewed", "facts_correct", "source_supported", "goal_covered",
    "usable", "refusal_correct", "failure_category", "notes",
]
BOOL_CHOICES = {"yes", "no", "na", ""}


def load_cases(path: Path = SUITE) -> list[dict]:
    """Derive requests from the exact numbered source document, not a second list."""
    cases = []
    group = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "## 计算机系统讲义":
            group = "system"
        elif line == "## SQL 短资料":
            group = "sql"
        elif line.startswith("## ") and group:
            group = None
        match = re.fullmatch(r"(\d+)\.\s*(.+)", line)
        if not match or group is None:
            continue
        number = int(match.group(1))
        label, sep, requirement = match.group(2).partition("：")
        if not sep or label not in KIND or not requirement.strip():
            raise ValueError(f"Unsupported suite item {number}: {line}")
        cases.append({
            "id": number, "group": group, "kind": KIND[label],
            "label": label, "requirement": requirement.strip(),
            "negative": label == "缺失依据",
        })
    if [case["id"] for case in cases] != list(range(1, 21)):
        raise ValueError("The committed ZH-06 document must contain exactly cases 1-20.")
    if sum(case["negative"] for case in cases) != 1 or cases[-1]["id"] != 20:
        raise ValueError("The negative-control case must remain case 20.")
    return cases


def case_prompt(case: dict) -> str:
    """Turn the existing evaluation requirement into a direct learner request.

    Keep the checklist text unchanged in the case manifest; case 20 is the
    negative-control question, not an instruction to tell the model to refuse.
    """
    if case["negative"]:
        return "请仅依据我上传的SQL学习资料，说明TCP三次握手过程中序号如何变化，并标出直接支持回答的资料依据。"
    prefix = {
        "mnemonic": "请根据资料编写一条便于回忆的记忆口诀：",
        "reply": "请仅依据资料解答以下问题：",
        "cloze": "请根据资料生成一道填空练习：",
        "single_choice": "请根据资料生成一道四选一单选题：",
    }[case["kind"]]
    return prefix + case["requirement"]


def select_cases(cases: list[dict], value: str) -> list[dict]:
    if value == "all":
        return cases
    try:
        numbers = [int(piece.strip()) for piece in value.split(",")]
    except ValueError as exc:
        raise ValueError("Use comma-separated case numbers, e.g. 13,20") from exc
    if not numbers or len(numbers) != len(set(numbers)) or any(i not in range(1, 21) for i in numbers):
        raise ValueError("Use distinct case numbers from 1 to 20.")
    lookup = {case["id"]: case for case in cases}
    return [lookup[i] for i in numbers]


def loopback_origin(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost"}
            or url.username or url.password or url.path not in {"", "/"}
            or url.query or url.fragment or url.port is None):
        raise ValueError("Evaluation accepts only http://127.0.0.1:PORT or http://localhost:PORT.")
    return value.rstrip("/")


def source_paths(cases, system_source, sql_source) -> dict:
    files = {"sql": Path(sql_source).expanduser()}
    if system_source:
        files["system"] = Path(system_source).expanduser()
    for group in {case["group"] for case in cases}:
        if group not in files:
            raise ValueError("Cases 1-12 require --system-source pointing to the original lecture Word file.")
        file = files[group]
        if (not file.is_file() or file.is_symlink() or
                file.suffix.lower() not in {".txt", ".docx", ".pdf"} or
                not 0 < file.stat().st_size <= 20 * 1024 * 1024):
            raise ValueError(f"Invalid/missing source for {group}: {file}")
    return files


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Existing evaluation artifact will not be overwritten: {path}")
    temporary = path.with_suffix(path.suffix + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def code_revision() -> str | None:
    """Record a reproducible source revision without changing the checkout."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        value = result.stdout.strip()
        return value if re.fullmatch(r"[0-9a-f]{40}", value) else None
    except (OSError, subprocess.SubprocessError):
        return None


def checked_local_response(response):
    """Do not follow a redirect to a nonlocal host from a nominal loopback URL."""
    if 300 <= response.status_code < 400:
        raise RuntimeError("Local trial returned a redirect; refusing to follow it.")
    response.raise_for_status()
    return response


def save_private_session(jar: MozillaCookieJar) -> None:
    """Session credentials are never printed, committed, or included in reports."""
    path = Path(jar.filename)
    if path.is_symlink():
        raise RuntimeError("Refusing to write a symlinked evaluation cookie file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    jar.save(ignore_discard=True, ignore_expires=False)
    if os.name != "nt":
        path.chmod(0o600)


def resume_artifact(existing: dict, case: dict, source_sha: str) -> None:
    if (existing.get("caseId") != case["id"] or
            existing.get("kind") != case["kind"] or
            existing.get("sourceSha256") != source_sha or
            existing.get("requestSent") != case_prompt(case) or
            not re.fullmatch(r"[0-9a-f]{32}", str(existing.get("clientRequestId", "")))):
        raise RuntimeError("Saved evaluation case does not match current source/requirements; use a separate output folder.")


def write_progress(path: Path, data: dict, *, permitted: bool) -> None:
    """Never replace a result without explicit --resume; atomic file replacement."""
    if path.is_symlink() or (path.exists() and not permitted):
        raise FileExistsError(f"Existing result not overwritten: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def receipt_for_case(session, origin: str, client_request_id: str) -> str | None:
    """Recover the accepted task without uploading a second copy."""
    response = session.get(
        origin + "/api/generation-submissions/" + client_request_id,
        timeout=20, allow_redirects=False,
    )
    if response.status_code == 404:
        return None
    checked_local_response(response)
    task_id = response.json().get("taskId")
    if not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-f]{32}", task_id):
        raise RuntimeError("Malformed submission receipt; refusing a new upload.")
    return task_id


def run_live(args, cases) -> None:
    if not args.confirm_live:
        raise ValueError("Model evaluation sends files and costs time. Add --confirm-live to execute.")
    origin = loopback_origin(args.base_url)
    selected = select_cases(cases, args.cases)
    paths = source_paths(selected, args.system_source, args.sql_source)
    if not 10 <= args.timeout_seconds <= 1800 or not 1 <= args.poll_seconds <= 30:
        raise ValueError("Use --timeout-seconds 10-1800 and --poll-seconds 1-30.")
    if not args.resume and any((args.output / f"case-{case['id']:02d}.json").exists() for case in selected):
        raise FileExistsError("Existing cases require --resume or a new output directory.")
    import requests

    args.output.mkdir(parents=True, exist_ok=True)
    cookies_file = args.output / ".local-trial.cookies"
    if cookies_file.is_symlink():
        raise RuntimeError("Refusing symlinked session credentials.")
    if cookies_file.exists() and not args.resume:
        raise RuntimeError("This evaluation directory has an existing session; use --resume or a new directory.")
    jar = MozillaCookieJar(str(cookies_file))
    if args.resume:
        if not cookies_file.is_file():
            raise RuntimeError("Missing saved browser session; do not start a new one for an existing run.")
        jar.load(ignore_discard=True, ignore_expires=False)
        if not list(jar):
            raise RuntimeError("Saved session expired. Open a new isolated evaluation directory.")
    session = requests.Session()
    session.trust_env = False
    session.cookies = jar
    session.headers.update({"Origin": origin})
    if not args.resume:
        checked_local_response(session.get(origin + "/", timeout=20, allow_redirects=False))
        if not list(jar):
            raise RuntimeError("No trial session cookie. Use a local trial without invitation gate.")
        save_private_session(jar)
    health_response = session.get(origin + "/api/evaluation-preflight", timeout=20, allow_redirects=False)
    checked_local_response(health_response)
    health = health_response.json()
    if not isinstance(health, dict) or health.get("localPreview") is not True:
        raise RuntimeError("This server is not an approved local evaluation preview.")
    if not health.get("generationReady"):
        raise RuntimeError("Local Qwen model is not ready; check Ollama and AI_TEXT_MODEL.")
    model = health.get("requiredTextModel") or health.get("textModel")
    revision = code_revision()
    print(f"Live evaluation: {len(selected)} cases, local service {origin}")
    print("Only the configured local trial receives the source files. Do not use sensitive documents.")
    initialized = set()
    for case in selected:
        group = case["group"]
        library = "zh06-system" if group == "system" else "zh06-sql"
        source = paths[group]
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        record_path = args.output / f"case-{case['id']:02d}.json"
        prior = None
        if record_path.exists():
            if not args.resume:
                raise FileExistsError(f"Result already exists: {record_path}")
            prior = json.loads(record_path.read_text(encoding="utf-8"))
            resume_artifact(prior, case, digest)
            if prior["runStatus"] in TERMINAL:
                print(f"Case {case['id']:02d}: already terminal, preserving original result.", flush=True)
                continue
        if library not in initialized:
            checked_local_response(session.put(
                origin + "/api/libraries/" + library, json={"title": "ZH-06 " + group},
                timeout=20, allow_redirects=False,
            ))
            initialized.add(library)

        artifact = prior or {
            "caseId": case["id"], "group": group, "kind": case["kind"],
            "expectedNegative": case["negative"], "requirement": case["requirement"],
            "sourceName": source.name, "sourceSha256": digest,
            "requestSent": case_prompt(case),
            "runStartedUtc": datetime.now(timezone.utc).isoformat(),
            "taskId": None, "clientRequestId": uuid.uuid4().hex,
            "model": model, "codeRevision": revision,
            "runStatus": "prepared", "modelCallCount": None, "task": None,
        }
        if prior is not None and prior.get("model") != model:
            raise RuntimeError("Evaluation model has changed. Do not mix models within one run.")
        if prior is None:
            write_progress(record_path, artifact, permitted=False)
        started = time.monotonic()
        try:
            print(f"Case {case['id']:02d}: {case['label']} · {group}", flush=True)
            task_id = artifact.get("taskId")
            if task_id is None:
                task_id = receipt_for_case(session, origin, artifact["clientRequestId"])
            if task_id is None:
                # Identical request id is committed BEFORE POST. A lost HTTP
                # response can be recovered through the receipt endpoint.
                with source.open("rb") as file:
                    response = checked_local_response(session.post(
                        origin + "/api/generation-tasks",
                        data={
                            "libraryId": library, "libraryName": "ZH-06 " + group,
                            "requirements": case_prompt(case), "questionCount": "1",
                            "questionType": case["kind"],
                            "clientRequestId": artifact["clientRequestId"],
                        },
                        files={"files": (source.name, file, mimetypes.guess_type(source.name)[0] or "application/octet-stream")},
                        timeout=(10, 90), allow_redirects=False,
                    ))
                task_id = response.json().get("taskId")
            if not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-f]{32}", task_id):
                raise RuntimeError("Unexpected task ID; aborting without resubmission.")
            artifact["taskId"] = task_id
            artifact["runStatus"] = "submitted"
            write_progress(record_path, artifact, permitted=True)
            deadline = time.monotonic() + args.timeout_seconds
            while True:
                task = checked_local_response(session.get(
                    origin + "/api/generation-tasks/" + task_id, timeout=20,
                    allow_redirects=False,
                )).json()
                artifact["task"] = task
                status = task.get("status")
                if status in TERMINAL:
                    artifact["runStatus"] = status
                    break
                if time.monotonic() >= deadline:
                    artifact["runStatus"] = "still_running_at_timeout"
                    break
                time.sleep(args.poll_seconds)
        except (requests.RequestException, KeyError, TypeError, ValueError, RuntimeError) as exc:
            artifact["runStatus"] = "request_error"
            artifact["error"] = f"{type(exc).__name__}: {str(exc)[:350]}"
        artifact["elapsedWallMs"] = (artifact.get("elapsedWallMs") or 0) + round(
            1000 * (time.monotonic() - started)
        )
        artifact["runFinishedUtc"] = datetime.now(timezone.utc).isoformat()
        write_progress(record_path, artifact, permitted=True)
        print(f"  {artifact['runStatus']} · {artifact['elapsedWallMs']/1000:.1f}s", flush=True)
        if artifact["runStatus"] not in TERMINAL:
            print("Stopped after incomplete execution. Re-run same cases/output with --resume.")
            break


def read_artifacts(out: Path) -> dict[int, dict]:
    artifacts = {}
    for path in sorted(out.glob("case-??.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        number = data.get("caseId")
        if not isinstance(number, int) or number not in range(1, 21) or number in artifacts:
            raise ValueError(f"Invalid or duplicate case artifact: {path}")
        artifacts[number] = data
    return artifacts


def review_template(out: Path, cases: list[dict]) -> None:
    artifacts = read_artifacts(out)
    path = out / "human_review.csv"
    if path.exists():
        raise FileExistsError("human_review.csv already exists; manual labels must not be overwritten.")
    path.parent.mkdir(parents=True, exist_ok=True)
    by_id = {case["id"]: case for case in cases}
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for number, artifact in sorted(artifacts.items()):
            case = by_id[number]
            writer.writerow({
                "case_id": number, "kind": case["kind"],
                "source_group": case["group"], "task_status": artifact["runStatus"],
                "artifact": f"case-{number:02d}.json",
                "reviewed": "", "facts_correct": "", "source_supported": "",
                "goal_covered": "", "usable": "", "refusal_correct": "",
                "failure_category": "", "notes": "",
            })
    print(f"Manual review template: {path}")


def read_reviews(path: Path) -> dict[int, dict]:
    if not path.is_file():
        return {}
    rows = {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not set(CSV_FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("Review CSV columns have changed.")
        for row in reader:
            number = int(row["case_id"])
            if number not in range(1, 21) or number in rows:
                raise ValueError("Duplicate/unknown case in review CSV.")
            for name in ("reviewed", "facts_correct", "source_supported", "goal_covered", "usable", "refusal_correct"):
                row[name] = (row[name] or "").strip().lower()
                if row[name] not in BOOL_CHOICES:
                    raise ValueError(f"Invalid {name} for case {number}: use yes/no/na.")
            rows[number] = row
    return rows


def metric(rows: list[dict], field: str) -> dict:
    judged = [row for row in rows if row.get(field) in {"yes", "no"}]
    return {
        "numerator": sum(row[field] == "yes" for row in judged),
        "denominator": len(judged),
        "rate": round(sum(row[field] == "yes" for row in judged) / len(judged), 4) if judged else None,
    }


def build_report(artifacts: dict[int, dict], reviews: dict[int, dict]) -> dict:
    outcomes = {"system": Counter(), "sql": Counter(), "missingEvidence": Counter()}
    for case in load_cases():
        record = artifacts.get(case["id"])
        status = record["runStatus"] if record is not None else "not_run"
        group = "missingEvidence" if case["negative"] else case["group"]
        outcomes[group][status] += 1
    terminal = {number: record for number, record in artifacts.items() if record.get("runStatus") in TERMINAL}
    manually_reviewed = {number: row for number, row in reviews.items()
                         if number in terminal and row.get("reviewed") == "yes"}
    positive = [row for number, row in manually_reviewed.items() if number != 20]
    negative = [row for number, row in manually_reviewed.items() if number == 20]
    durations = [record["elapsedWallMs"] for record in terminal.values()
                 if isinstance(record.get("elapsedWallMs"), int)]
    return {
        "suite": "ZH-06 original 20-case checklist",
        "expectedCases": 20,
        "attemptedCases": len(artifacts),
        "terminalCases": len(terminal),
        "executionOutcomes": {group: dict(sorted(counts.items())) for group, counts in outcomes.items()},
        "humanReviewedCases": len(manually_reviewed),
        "humanUsability": metric(positive, "usable"),
        "factualCorrectness": metric(positive, "facts_correct"),
        "sourceSupport": metric(positive, "source_supported"),
        "goalCoverage": metric(positive, "goal_covered"),
        "correctRefusal": metric(negative, "refusal_correct"),
        "medianTaskWallMs": statistics.median(durations) if durations else None,
        "modelCallCount": None,
        "modelCallCountNote": "Not exposed by the browser trial API; do not infer from retry events.",
        "note": "Auto-validation is not factual correctness. Only completed, human-reviewed cases enter human metrics.",
    }


def report(out: Path) -> None:
    artifacts = read_artifacts(out)
    reviews = read_reviews(out / "human_review.csv")
    result = build_report(artifacts, reviews)
    json_path = out / "report.json"
    md_path = out / "report.md"
    # A report can be regenerated after human labels change.
    out.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    def show(item):
        return f"{item['numerator']}/{item['denominator']} ({item['rate']*100:.1f}%)" if item["rate"] is not None else "尚无人工有效样本"
    md = [
        "# ZH-06 出题质量评测报告",
        "",
        f"- 计划案例：20；已有运行记录：{result['attemptedCases']}；到达终态：{result['terminalCases']}；已人工判定：{result['humanReviewedCases']}",
    ]
    for group, label in (
        ("system", "计算机系统正向案例"),
        ("sql", "SQL 正向案例"),
        ("missingEvidence", "缺依据案例"),
    ):
        counts = result["executionOutcomes"][group]
        md.append(f"- {label}运行状态：" + "、".join(f"`{status}` {count} 条" for status, count in counts.items()))
    md += [
        f"- 人工可用率（正向样本）：{show(result['humanUsability'])}",
        f"- 事实正确率（正向样本）：{show(result['factualCorrectness'])}",
        f"- 原文依据支持率（正向样本）：{show(result['sourceSupport'])}",
        f"- 目标覆盖率（正向样本）：{show(result['goalCoverage'])}",
        f"- 拒绝越界请求（第20例）：{show(result['correctRefusal'])}",
        f"- 有终态任务的客户端中位墙钟耗时：{result['medianTaskWallMs']/1000:.1f}秒" if result["medianTaskWallMs"] is not None else "- 中位耗时：无样本",
        "- 模型实际调用次数：当前HTTP响应未提供，不能推测。",
        "",
        "注意：未执行或未人工判定案例不计入人工质量分母；自动初筛通过不等于真实正确。",
    ]
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Reports written: {json_path}, {md_path}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ZH-06 reproducible, source-grounded quality evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="Print the 20 source-defined cases without running Qwen.")
    run = sub.add_parser("run", help="Explicitly execute against a LOOPBACK-only trial.")
    run.add_argument("--confirm-live", action="store_true")
    run.add_argument("--resume", action="store_true", help="Reuse original local session and submission receipts.")
    run.add_argument("--base-url", default="http://127.0.0.1:8095")
    run.add_argument("--cases", default="all", help="all or comma-separated IDs, e.g. 13,20")
    run.add_argument("--system-source", type=Path, help="Original computer-systems Word/PDF/TXT; required for cases 1-12")
    run.add_argument("--sql-source", type=Path, default=DEFAULT_SQL)
    run.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    run.add_argument("--timeout-seconds", type=int, default=900)
    run.add_argument("--poll-seconds", type=int, default=3)
    for name in ("review-template", "report"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        cases = load_cases()
        if args.command == "plan":
            for case in cases:
                print(f"{case['id']:02d} [{case['group']}/{case['kind']}] {case['label']}：{case['requirement']}")
        elif args.command == "run":
            run_live(args, cases)
        elif args.command == "review-template":
            review_template(args.output, cases)
        elif args.command == "report":
            report(args.output)
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError, OSError) as exc:
        print(f"ZH-06: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
