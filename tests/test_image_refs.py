import json
import sys
from pathlib import Path

sys.path.insert(0, "backend")

from app.engine.image_refs import canonical_image_name, resolve_image_name


CASES = json.loads(Path("tests/image_ref_cases.json").read_text(encoding="utf-8"))


def test_image_reference_matching_contract_matches_shared_vectors():
    for case in CASES:
        assert canonical_image_name(case["reference"]) == case["canonical"]
        assert resolve_image_name(case["reference"], case["names"]) == case["match"]
