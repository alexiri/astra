from __future__ import annotations

import uuid

from core.elections_meek import tally_meek


def main() -> None:
    candidates = [
        {"id": 10, "name": "A", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000010")},
        {"id": 11, "name": "B", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000011")},
        {"id": 12, "name": "C", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000012")},
        {"id": 13, "name": "D", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000013")},
    ]

    ballots = [
        {"weight": 1, "ranking": [10, 12]},
        {"weight": 1, "ranking": [11, 10]},
        {"weight": 1, "ranking": [12, 11]},
        {"weight": 1, "ranking": [11, 12, 10]},
        {"weight": 5, "ranking": [11, 10]},
        # {"weight": 2, "ranking": [12, 11, 10]},
        # {"weight": 5, "ranking": [10, 12, 11]},
    ]

    exclusions = [
        {"public_id": 1, "name": "Incompatibles", "max_elected": 1, "candidate_ids": [10, 11]},
    ]

    result = tally_meek(seats=2, ballots=ballots, candidates=candidates, exclusion_groups=exclusions)
    print("Rounds detail:")
    for round_detail in result["rounds"]:
        data = round_detail.copy()
        data.pop("audit_text", None)
        print(data)
        # print(round_detail['summary_text'])
        print(round_detail['audit_text'])
        print()
        # break

    print(f"Elected: {result['elected']}")
    print(f"Eliminated: {result['eliminated']}")
    print(f"Forced Excluded: {result['forced_excluded']}")
    print(f"Quota: {result['quota']:.2f}, Rounds: {len(result['rounds'])}")

if __name__ == "__main__":
    main()
