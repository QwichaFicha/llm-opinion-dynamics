from dataclasses import replace
import json
import unittest

from src.deliberation import (DiscussionConfig, EvidenceStub, BASE_FACTS, EVENTS, BEGIN, END,
    pair_schedule, schedule, simulate, diagnostic_plan, run_diagnostics)


class DiscussionTests(unittest.TestCase):
    def test_each_pair_meets_once_and_everyone_has_one_partner(self):
        pairs=[]
        for round_ in pair_schedule():
            self.assertEqual(sorted(i for pair in round_ for i in pair),list(range(6)))
            pairs.extend(round_)
        self.assertEqual(len(set(pairs)),15)
        self.assertEqual(set(pairs),{(i,j) for i in range(6) for j in range(i+1,6)})

    def test_fixed_control_has_identical_first_round(self):
        rotating=schedule(DiscussionConfig())
        fixed=schedule(DiscussionConfig(partner_mode='fixed'))
        self.assertEqual(rotating[0],fixed[0])
        self.assertEqual(fixed,[rotating[0]]*5)
        with self.assertRaises(ValueError):schedule(DiscussionConfig(rounds=6))

    def test_delivery_uses_new_partner_and_previous_round_snapshot(self):
        result=simulate(DiscussionConfig(),EvidenceStub())
        self.assertEqual(result['status'],'ok')
        peers=[e for e in result['events'] if e['kind']=='peer']
        self.assertEqual(len(peers),30)
        seen=set()
        for event in peers:
            key=(event['recipient'],event['source'])
            self.assertNotIn(key,seen);seen.add(key)
            t=event['round']
            self.assertEqual(event['message'],result['actions'][t-1][event['source']]['message'])
            self.assertIn(sorted(key),[list(pair) for pair in result['pair_schedule'][t-1]])
            self.assertNotIn('opinion',event)

    def test_own_history_is_real_previous_action_without_future_facts(self):
        model=EvidenceStub();simulate(DiscussionConfig(),model)
        for call in model.calls:
            state=json.loads(call['prompt'].split(BEGIN)[1].split(END)[0])
            self.assertEqual(len(state['own_statements']),call['round'])
            self.assertTrue(all(r['round']<=call['round'] for r in state['official_records']))
            self.assertTrue(all('updates' not in r for r in state['official_records']))
            self.assertTrue(all(r['round']<call['round'] for r in state['own_statements']))

    def test_history_ablation_preserves_current_opinion(self):
        model=EvidenceStub();simulate(DiscussionConfig(own_history=False),model)
        state=json.loads(model.calls[-1]['prompt'].split(BEGIN)[1].split(END)[0])
        self.assertNotIn('own_statements',state)
        self.assertIn('current_opinion',state)

    def test_snapshot_order_invariance(self):
        a=simulate(DiscussionConfig(),EvidenceStub())
        b=simulate(DiscussionConfig(),EvidenceStub(),reverse=True)
        self.assertEqual(a['trajectory'],b['trajectory'])

    def test_irrelevant_update_and_correction_have_known_fact_targets(self):
        cases={c['id']:c for c in diagnostic_plan()}
        self.assertEqual({c['round'] for c in cases.values()},{4})
        self.assertTrue(all(r['round']<=c['round'] for c in cases.values() for r in c['records']))
        self.assertEqual(cases['none_agent0']['expected_beliefs'],cases['irrelevant_agent0']['expected_beliefs'])
        self.assertTrue(cases['relevant_agent0']['expected_beliefs']['digital_offline'])
        self.assertEqual(cases['correction_agent0']['expected_beliefs']['digital_cost'],140)
        result=run_diagnostics(EvidenceStub())
        self.assertEqual(len(result['results']),24)
        self.assertTrue(all(r['beliefs_correct'] and not r['unknown_citations'] for r in result['results']))

    def test_budget_failure_keeps_partial_trace(self):
        result=simulate(DiscussionConfig(),EvidenceStub(max_calls=8))
        self.assertEqual(result['status'],'error')
        self.assertEqual(len(result['calls']),8)
        self.assertEqual(len(result['trajectory']),1)

    def test_numeric_ablation_only_adds_partner_opinion(self):
        result=simulate(DiscussionConfig(peer_numbers=True),EvidenceStub())
        peers=[e for e in result['events'] if e['kind']=='peer']
        for event in peers:
            self.assertEqual(event['opinion'],result['trajectory'][event['round']-1]['opinions'][event['source']])


if __name__=='__main__':unittest.main()
