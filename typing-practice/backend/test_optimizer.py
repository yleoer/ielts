from datetime import datetime, timedelta, timezone
import unittest

from fsrs import Rating, ReviewLog, Scheduler

from optimize_fsrs import effective_count, evaluate, optimize


class OptimizerTest(unittest.TestCase):
    def test_short_steps_are_history_but_do_not_count_as_effective(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        logs = [ReviewLog(1, Rating.Good, now + timedelta(minutes=i), 7000) for i in range(60)]
        logs += [ReviewLog(1, Rating.Good, now + timedelta(days=2), 7000)]
        self.assertEqual(effective_count(logs), 1)
        self.assertFalse(optimize(logs)["accepted"])

    def test_time_split_does_not_leak_and_unchanged_parameters_are_rejected(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        logs = [ReviewLog(card, Rating.Again if (day + card) % 7 == 0 else Rating.Good,
                          now + timedelta(days=day * 2), 7000) for day in range(15) for card in range(100)]
        trained = []
        class SameParameters:
            def __init__(self, history):
                trained.extend(history)
            def compute_optimal_parameters(self):
                return list(Scheduler().parameters)
        result = optimize(logs, optimizer_factory=SameParameters)
        self.assertFalse(result["accepted"])
        self.assertTrue(all(log.review_datetime.isoformat().replace('+00:00', 'Z') < result['training_before'] for log in trained))
        self.assertEqual(result["candidate"], result["baseline"])
        self.assertEqual(result["candidate"]["reviews"], 300)

    def test_evaluation_predicts_before_reviewing_answer(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        correct = [ReviewLog(1, Rating.Good, now, 7000), ReviewLog(1, Rating.Good, now + timedelta(days=1), 7000)]
        wrong = [correct[0], ReviewLog(1, Rating.Again, correct[1].review_datetime, 7000)]
        self.assertLess(evaluate(correct, Scheduler().parameters, now)["log_loss"], evaluate(wrong, Scheduler().parameters, now)["log_loss"])
