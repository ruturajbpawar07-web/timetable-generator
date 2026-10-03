"""Run the engine on a standardized JSON problem, no DB/API needed:

    python -m scheduler data/sample_problem.json > result.json
"""
import json
import sys
from dataclasses import asdict

from .model import Problem
from .solver import solve

r = solve(Problem.from_dict(json.load(open(sys.argv[1]))))
r["entries"] = [asdict(e) for e in r["entries"]]
json.dump(r, sys.stdout, indent=1, default=str)
