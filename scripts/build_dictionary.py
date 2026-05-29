"""CLI: build dictionary.json from the master Extrato Anual xlsx.

Usage:
    python scripts/build_dictionary.py "Extrato AECO - Anual.xlsx" data/dictionary.json [feedback.jsonl]

The feedback file defaults to data/feedback.jsonl and is folded in when present,
so the contadora's corrections reinforce the rules on each rebuild.
"""
import sys
from pathlib import Path

# Make the project importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aeco import dictionary as dictmod


def main():
    if len(sys.argv) < 3:
        print("Usage: build_dictionary.py <master.xlsx> <output.json> [feedback.jsonl]", file=sys.stderr)
        sys.exit(1)
    master_path, out_path = sys.argv[1], sys.argv[2]
    feedback_path = sys.argv[3] if len(sys.argv) > 3 else "data/feedback.jsonl"
    fb_arg = feedback_path if Path(feedback_path).exists() else None
    print(f"Building dictionary from {master_path}"
          + (f" + feedback {feedback_path}" if fb_arg else " (sem feedback)") + "...")
    data = dictmod.build(master_path, feedback_path=fb_arg)
    dictmod.save(data, out_path)
    n = len(data["entries"])
    modes = {}
    for e in data["entries"].values():
        modes[e["mode"]] = modes.get(e["mode"], 0) + 1
    print(f"Saved {out_path}")
    print(f"  entries: {n} -> {modes}")
    print(f"  categories.fluxo_caixa: {len(data['categories']['fluxo_caixa'])}")
    print(f"  categories.empresa: {len(data['categories']['empresa'])}")
    print(f"  all_descricoes: {len(data['all_descricoes'])}")
    print(f"  all_observacoes: {len(data['all_observacoes'])}")


if __name__ == "__main__":
    main()
