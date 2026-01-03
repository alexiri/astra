from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone


class STVTallyTests(TestCase):
    def test_meek_does_not_elect_more_than_seats_in_single_iteration(self) -> None:
        from core.elections_meek import tally_meek

        # With the Hagenbach-Bischoff quota (total/(seats+1)), it is possible for more
        # candidates to meet the quota than there are remaining seats. The tally must
        # deterministically elect at most the remaining number of seats.
        candidates = [
            {"id": 1, "name": "A", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000001")},
            {"id": 2, "name": "B", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000002")},
        ]
        ballots = [
            {"weight": 1, "ranking": [1]},
            {"weight": 1, "ranking": [2]},
        ]

        result = tally_meek(ballots=ballots, candidates=candidates, seats=1)
        rounds = list(result.get("rounds") or [])
        self.assertGreaterEqual(len(rounds), 1)

        r0 = rounds[0]
        self.assertIsNone(r0.get("eliminated"))
        self.assertIsInstance(r0.get("elected"), list)
        self.assertLessEqual(len(list(r0.get("elected") or [])), 1)
        self.assertEqual(len(result["elected"]), 1)

    def test_meek_numerical_convergence_does_not_imply_count_complete(self) -> None:
        from core.elections_meek import tally_meek

        # Construct a scenario where vote transfers immediately stabilize (numerical convergence)
        # but the outcome is not yet determined: 3 candidates, 1 seat, each has 1 first preference.
        # Quota is 3 / 2 = 1.5, so nobody reaches quota in the converged iteration.
        candidates = [
            {"id": 1, "name": "A", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000001")},
            {"id": 2, "name": "B", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000002")},
            {"id": 3, "name": "C", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000003")},
        ]
        ballots = [
            {"weight": 1, "ranking": [1]},
            {"weight": 1, "ranking": [2]},
            {"weight": 1, "ranking": [3]},
        ]

        result = tally_meek(ballots=ballots, candidates=candidates, seats=1)
        rounds = list(result.get("rounds") or [])
        self.assertGreaterEqual(len(rounds), 2)

        # Find the numerically converged iteration before an elimination occurs.
        converged_rounds = [
            r
            for r in rounds
            if isinstance(r, dict)
            and r.get("eliminated") is None
            and not list(r.get("elected") or [])
            and bool(r.get("numerically_converged"))
        ]
        self.assertGreaterEqual(len(converged_rounds), 1)

        r0 = converged_rounds[0]
        self.assertIn("count_complete", r0)
        self.assertFalse(bool(r0.get("count_complete")))

        # Guardrail: if count_complete is false, do not claim finality.
        audit_text = str(r0.get("audit_text") or "")
        summary_text = str(r0.get("summary_text") or "")
        self.assertNotIn("Final results", audit_text)
        self.assertNotIn("all available seats have been filled", audit_text)
        self.assertNotIn("Final results", summary_text)

    def test_meek_when_eligible_candidates_fill_remaining_seats_elects_them_immediately(self) -> None:
        from core.elections_meek import tally_meek

        # Scenario: 3 candidates, 2 seats.
        # A is elected by quota early; later an elimination occurs among B/C.
        # Once one of B/C is eliminated, the remaining eligible candidates exactly
        # fill the remaining seats, so the remaining candidate should be elected
        # in that same iteration.
        candidates = [
            {"id": 1, "name": "A", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000001")},
            {"id": 2, "name": "B", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000002")},
            {"id": 3, "name": "C", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000003")},
        ]
        ballots = [
            {"weight": 1, "ranking": [1]},
            {"weight": 1, "ranking": [1]},
            {"weight": 1, "ranking": [2]},
            {"weight": 1, "ranking": [3]},
        ]

        result = tally_meek(ballots=ballots, candidates=candidates, seats=2)
        self.assertIn(1, result["elected"])
        self.assertEqual(len(result["elected"]), 2)
        self.assertTrue(set(result["elected"]).issubset({1, 2, 3}))
        self.assertTrue(2 in result["elected"] or 3 in result["elected"])

        rounds = list(result.get("rounds") or [])
        self.assertGreaterEqual(len(rounds), 2)

        # Find the first elimination round and assert it also contains an election,
        # finishing the count in that same iteration.
        elimination_rounds = [r for r in rounds if isinstance(r, dict) and r.get("eliminated") is not None]
        self.assertGreaterEqual(len(elimination_rounds), 1)
        elim_round = elimination_rounds[0]

        self.assertTrue(bool(elim_round.get("count_complete")))
        self.assertIsInstance(elim_round.get("elected"), list)
        self.assertGreaterEqual(len(list(elim_round.get("elected") or [])), 1)

        audit_text = str(elim_round.get("audit_text") or "")
        self.assertIn("Final results", audit_text)

    def test_meek_fill_remaining_seats_explains_rule_election(self) -> None:
        from core.elections_meek import tally_meek

        # Seats=2, candidates=3. All ballots only rank A, so B and C have zero support.
        # Once one of B/C is eliminated (tie-break), the remaining candidate must be
        # elected to fill the remaining seat. The audit text must explain this rule.
        candidates = [
            {"id": 1, "name": "A", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000001")},
            {"id": 2, "name": "B", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000002")},
            {"id": 3, "name": "C", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000003")},
        ]
        ballots = [
            {"weight": 1, "ranking": [1]},
            {"weight": 1, "ranking": [1]},
        ]

        result = tally_meek(ballots=ballots, candidates=candidates, seats=2)
        rounds = list(result.get("rounds") or [])
        self.assertGreaterEqual(len(rounds), 1)

        elimination_rounds = [r for r in rounds if isinstance(r, dict) and r.get("eliminated") is not None]
        self.assertGreaterEqual(len(elimination_rounds), 1)
        r = elimination_rounds[0]

        self.assertTrue(bool(r.get("count_complete")))
        self.assertTrue(list(r.get("elected_to_fill_remaining_seats") or []))

        audit_text = str(r.get("audit_text") or "")
        self.assertIn("remaining eligible candidates exactly filled", audit_text)
        # Guardrail: do not imply every elected candidate had quota-reduction / surplus.
        self.assertNotIn("each elected candidate's retained vote total was reduced", audit_text)

    def test_two_seats_simple_elimination(self) -> None:
        from core.elections_meek import tally_meek

        candidates = [
            {"id": 1, "name": "A", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-0000000000aa")},
            {"id": 2, "name": "B", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-0000000000bb")},
            {"id": 3, "name": "C", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-0000000000cc")},
        ]
        ballots = [
            {"weight": 1, "ranking": [1, 2, 3]},
            {"weight": 1, "ranking": [1, 2, 3]},
            {"weight": 1, "ranking": [1, 2, 3]},
            {"weight": 1, "ranking": [2, 1, 3]},
            {"weight": 1, "ranking": [2, 1, 3]},
            {"weight": 1, "ranking": [3, 2, 1]},
        ]

        result = tally_meek(ballots=ballots, candidates=candidates, seats=2)

        self.assertEqual(result["quota"], Decimal("2"))
        self.assertEqual(result["elected"], [1, 2])
        self.assertNotIn(3, result["elected"])
        self.assertGreaterEqual(len(result["rounds"]), 1)

    def test_surplus_transfer_is_fractional_decimal(self) -> None:
        from core.elections_meek import tally_meek

        candidates = [
            {"id": 1, "name": "A", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000001")},
            {"id": 2, "name": "B", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000002")},
        ]
        ballots = [
            {"weight": 1, "ranking": [1, 2]},
            {"weight": 1, "ranking": [1, 2]},
            {"weight": 1, "ranking": [1, 2]},
            {"weight": 1, "ranking": [1, 2]},
            {"weight": 1, "ranking": [2, 1]},
        ]

        result = tally_meek(ballots=ballots, candidates=candidates, seats=2)

        expected_quota = (Decimal(5) / Decimal(3)).quantize(Decimal("1.00000000000000000000"))
        self.assertEqual(result["quota"].quantize(Decimal("1.00000000000000000000")), expected_quota)
        self.assertEqual(result["elected"], [1, 2])

        # Ensure at least one retention factor becomes fractional due to surplus.
        last_round = result["rounds"][-1]
        r = last_round["retention_factors"]
        self.assertLess(Decimal(str(r["1"])), Decimal("1"))

    def test_tie_break_uses_lowest_tiebreak_uuid(self) -> None:
        from core.elections_meek import tally_meek

        # A and B are tied for elimination; A has lower tiebreak UUID so should be eliminated.
        candidates = [
            {"id": 10, "name": "A", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000010")},
            {"id": 11, "name": "B", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000011")},
            {"id": 12, "name": "C", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000012")},
        ]
        ballots = [
            # Exhausted ballots (no subsequent preferences) force elimination among tied zero-support candidates.
            {"weight": 1, "ranking": [12]},
            {"weight": 1, "ranking": [12]},
        ]

        result = tally_meek(ballots=ballots, candidates=candidates, seats=1)

        self.assertEqual(result["elected"], [12])
        # The tie-break only matters if we have to eliminate; force it by requesting 2 seats.
        result2 = tally_meek(ballots=ballots, candidates=candidates, seats=2)
        self.assertIn(result2["eliminated"][0], {10, 11})
        self.assertEqual(result2["eliminated"][0], 10)

        elimination_rounds = [r for r in result2["rounds"] if r.get("eliminated") is not None]
        self.assertGreaterEqual(len(elimination_rounds), 1)
        audit_text = str(elimination_rounds[0].get("audit_text") or "")
        self.assertIn("Candidates A and B", audit_text)
        self.assertIn("predefined deterministic tie-breaking rules", audit_text)
        self.assertIn(
            "No distinction could be made based on prior round performance, cumulative support, or first-preference votes.",
            audit_text,
        )
        self.assertIn("fixed candidate ordering identifier", audit_text)
        self.assertIn("selected for elimination", audit_text)

    def test_exclusion_group_forces_exclusion_after_election(self) -> None:
        from core.elections_meek import tally_meek

        candidates = [
            {"id": 1, "name": "A", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000001")},
            {"id": 2, "name": "B", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000002")},
            {"id": 3, "name": "C", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000003")},
        ]
        ballots = [
            {"weight": 1, "ranking": [1, 2, 3]},
            {"weight": 1, "ranking": [1, 2, 3]},
            {"weight": 1, "ranking": [1, 2, 3]},
            {"weight": 1, "ranking": [2, 1, 3]},
            {"weight": 1, "ranking": [2, 1, 3]},
            {"weight": 1, "ranking": [2, 1, 3]},
        ]
        exclusion_groups = [
            {
                "public_id": "group-1",
                "max_elected": 1,
                "candidate_ids": [1, 2],
            }
        ]

        result = tally_meek(
            ballots=ballots,
            candidates=candidates,
            seats=2,
            exclusion_groups=exclusion_groups,
        )

        self.assertIn(result["elected"][0], {1, 2})
        self.assertEqual(len(result["elected"]), 2)
        self.assertIn(result["forced_excluded"][0], {1, 2})
        self.assertNotIn(result["forced_excluded"][0], result["elected"])

    def test_exclusion_group_quota_reached_explanation_is_not_confusing(self) -> None:
        from core.elections_meek import tally_meek

        # A and B both exceed quota immediately, but exclusion group allows only one of them.
        candidates = [
            {"id": 1, "name": "A", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000001")},
            {"id": 2, "name": "B", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000002")},
            {"id": 3, "name": "C", "tiebreak_uuid": uuid.UUID("00000000-0000-0000-0000-000000000003")},
        ]
        ballots = [
            {"weight": 1, "ranking": [1, 2, 3]},
            {"weight": 1, "ranking": [1, 2, 3]},
            {"weight": 1, "ranking": [1, 2, 3]},
            {"weight": 1, "ranking": [2, 1, 3]},
            {"weight": 1, "ranking": [2, 1, 3]},
            {"weight": 1, "ranking": [2, 1, 3]},
        ]
        exclusion_groups = [
            {
                "public_id": "incompat",
                "name": "Incompatibles",
                "max_elected": 1,
                "candidate_ids": [1, 2],
            }
        ]

        result = tally_meek(
            ballots=ballots,
            candidates=candidates,
            seats=2,
            exclusion_groups=exclusion_groups,
        )

        forced = set(result.get("forced_excluded") or [])
        self.assertEqual(forced & {1, 2}, forced)

        rounds = result.get("rounds") or []
        self.assertGreaterEqual(len(rounds), 1)
        first_round = rounds[0]

        audit_text = str(first_round.get("audit_text") or "")
        self.assertIn("reached the election quota", audit_text)
        self.assertIn("could not be elected despite reaching the quota", audit_text)
        self.assertIn('Incompatibles', audit_text)


class ElectionPrivacyFlowTests(TestCase):
    def test_ballot_hash_receipt_and_anonymization(self) -> None:
        from core.models import Candidate, Election, Membership, MembershipType

        now = timezone.now()
        election = Election.objects.create(
            name="Board election",
            description="",
            start_datetime=now - datetime.timedelta(days=1),
            end_datetime=now + datetime.timedelta(days=1),
            number_of_seats=1,
            status=Election.Status.open,
        )
        Candidate.objects.create(
            election=election,
            freeipa_username="alice",
            nominated_by="nominator",
            description="",
        )

        mt = MembershipType.objects.create(code="voter", name="Voter", votes=1, isIndividual=True)
        Membership.objects.create(
            target_username="reviewer",
            membership_type=mt,
            created_at=now - datetime.timedelta(days=200),
            expires_at=None,
        )

        # This test will be expanded once vote submission view exists.
        # For now: ensure models exist and can be created.
        self.assertEqual(election.candidates.count(), 1)
