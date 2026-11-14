"""Optional local Ollama Agent/Skill pilot. Never writes to the production database."""
import argparse
import json
from pathlib import Path
from backend.agent_runtime import AgentRuntime

def main():
    parser = argparse.ArgumentParser(description="知学伴 Agent/Skill 试验版")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error("Source text file does not exist")
    result = AgentRuntime().run(args.source.read_text(encoding="utf-8"), args.goal, count=args.count)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
        print(f"Completed: {result['status']}; output: {args.output}")
    else:
        print(output)
    return 0 if result["status"] == "succeeded" else 1

if __name__ == "__main__":
    raise SystemExit(main())
