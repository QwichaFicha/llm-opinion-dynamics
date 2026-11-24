import copy
from dataclasses import replace
import json
import os
import unittest
from unittest.mock import patch

from src.experiment import (Config, make_agent, simulate, mathematical_baseline,
                            exposures, network, profiles, ACTION)
from src.models import TracedModel, LiveRequestGate
from src.policy import validate_action, metrics


class ExperimentTests(unittest.TestCase):
    def test_control_stays_fixed(self):
        result=simulate(Config(news=False,peers=False))
        self.assertEqual(result['status'],'ok')
        self.assertTrue(all(row['opinions']==result['trajectory'][0]['opinions'] for row in result['trajectory']))
        self.assertEqual(result['final_metrics']['mean_abs_shift'],0)

    def test_news_one_step_analytic(self):
        config=Config(rounds=1,peers=False)
        result=simulate(config)
        expected=[round(p['initial_opinion']+.25*p['trust']*(.8-p['initial_opinion']),6) for p in profiles(config)]
        self.assertEqual(result['trajectory'][1]['opinions'],expected)

    def test_snapshot_order_invariance(self):
        config=Config(memory_rounds=4)
        self.assertEqual(simulate(config)['trajectory'],simulate(config,reverse=True)['trajectory'])

    def test_repeatability(self):
        a=simulate(Config());b=simulate(Config())
        self.assertEqual(a['trajectory'],b['trajectory'])
        self.assertEqual([c['prompt_sha256'] for c in a['calls']],[c['prompt_sha256'] for c in b['calls']])

    def test_topology_limits_delivery(self):
        config=Config(topology='segregated')
        result=simulate(config)
        for event in result['events']:
            if event['kind']=='peer':
                self.assertEqual(event['source']//3,event['recipient']//3)
                self.assertNotEqual(event['source'],event['recipient'])
        # Every recorded peer event has one source and intended recipient.
        self.assertEqual(sum(e['kind']=='peer' for e in result['events']),48)

    def test_memory_changes_carryover_not_first_round(self):
        short=simulate(Config(memory_rounds=1,peers=False))
        long=simulate(Config(memory_rounds=4,peers=False))
        self.assertEqual(short['trajectory'][1],long['trajectory'][1])
        self.assertEqual(short['trajectory'][1]['opinions'],short['trajectory'][-1]['opinions'])
        self.assertNotEqual(short['trajectory'][-1]['opinions'],long['trajectory'][-1]['opinions'])

    def test_framework_vs_numeric_path(self):
        config=Config(topology='complete',memory_rounds=4)
        self.assertEqual([r['opinions'] for r in simulate(config)['trajectory']],mathematical_baseline(config))

    def test_state_restoration_continues_identically(self):
        config=Config(rounds=1)
        profile=profiles(config)[0]
        a=make_agent(profile,config,TracedModel())
        a.observe(json.dumps({'kind':'tick','round':1}))
        a.observe(json.dumps({'kind':'news','round':1,'value':.8,'message':'test news'}))
        a.act(ACTION)
        b=make_agent(profile,config,TracedModel())
        # Exercise saved-state JSON round trip before continuing.
        b.set_state(json.loads(json.dumps(a.get_state())))
        for agent in (a,b):
            agent.observe(json.dumps({'kind':'tick','round':2}))
            agent.observe(json.dumps({'kind':'peer','round':2,'source':1,'value':-.7,'message':'test observation'}))
        self.assertEqual(a.act(ACTION),b.act(ACTION))
        self.assertEqual(a.get_state(),b.get_state())

    def test_budget_failure_preserves_partial_trace(self):
        result=simulate(Config(),max_calls=3)
        self.assertEqual(result['status'],'error')
        self.assertEqual(len(result['calls']),3)
        self.assertEqual(len(result['trajectory']),1)
        self.assertEqual(result['error']['type'],'RuntimeError')

    def test_invalid_outputs_are_rejected(self):
        for raw in ('bad', '{"opinion":NaN,"message":"x"}',
                    '{"opinion":true,"message":"x"}', '{"opinion":2,"message":"x"}',
                    '{"opinion":0,"message":""}', '{"opinion":0,"message":"x","extra":0}'):
            with self.subTest(raw=raw),self.assertRaises((ValueError,TypeError)):
                validate_action(raw)

    def test_metrics_known_values(self):
        result=metrics([-1,1],[-.5,.5],[(0,1)])
        self.assertEqual(result['mean_opinion'],0)
        self.assertEqual(result['variance'],.25)
        self.assertEqual(result['mean_abs_shift'],.5)
        self.assertEqual(result['edge_disagreement'],1)


class AdapterContractTests(unittest.TestCase):
    ENV={'LLM_API_KEY':'test-only-placeholder','LLM_BASE_URL':'https://test.invalid/v1','LLM_MODEL':'fictional-test-model'}

    def setUp(self):
        self.env_loader=patch('src.models.load_env')
        self.env_loader.start()
        self.addCleanup(self.env_loader.stop)

    @patch.dict(os.environ,ENV,clear=True)
    def test_openai_wire_contract_with_fake_transport(self):
        seen=[]
        def fake(payload, timeout):
            seen.append(payload)
            return {'id':'test-response','model':'test-revision','choices':[{'message':{'content':'{"opinion":0.2,"message":"argument"}'}}],
                    'usage':{'prompt_tokens':8,'completion_tokens':5}}
        model=TracedModel('live',max_calls=1,transport=fake)
        self.assertEqual(validate_action(model.sample_text('fictional test prompt'))['opinion'],.2)
        self.assertEqual(seen[0]['model'],'fictional-test-model')
        self.assertNotIn('api_key',seen[0])
        self.assertNotIn('test-only-placeholder',json.dumps(model.calls))
        self.assertEqual(model.calls[0]['provider_model'],'test-revision')
        self.assertEqual(model.calls[0]['usage']['completion_tokens'],5)
        with self.assertRaises(RuntimeError):
            model.sample_text('second')

    @patch.dict(os.environ,ENV,clear=True)
    def test_adapter_records_failed_attempt_once(self):
        def fail(payload,timeout):
            raise TimeoutError('test')
        model=TracedModel('live',transport=fail)
        with self.assertRaises(TimeoutError):
            model.sample_text('test')
        self.assertEqual(len(model.calls),1)
        self.assertEqual(model.calls[0]['status'],'error')

    @patch.dict(os.environ,ENV,clear=True)
    def test_system_role_can_be_overridden_without_changing_user_prompt(self):
        seen=[]
        def fake(payload,timeout):
            seen.append(payload)
            return {'choices':[{'message':{'content':'{"opinion":-0.04,"message":"test"}'}}]}
        model=TracedModel('live',transport=fake,system_message='You are an accurate numerical assistant.')
        model.sample_text('unchanged input')
        self.assertEqual(seen[0]['messages'][0]['content'],'You are an accurate numerical assistant.')
        self.assertEqual(seen[0]['messages'][1]['content'],'unchanged input')
        self.assertEqual(model.calls[0]['system_message'],seen[0]['messages'][0]['content'])

    @patch.dict(os.environ,{'LLM_BASE_URL':'https://test.invalid'},clear=True)
    def test_missing_key_prevents_network(self):
        with self.assertRaises(ValueError):
            TracedModel('live')


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        self.now=0.0
        self.gate=LiveRequestGate(clock=lambda:self.now,sleep=self.advance)

    def advance(self,seconds):
        self.now += seconds

    def test_minimum_spacing(self):
        self.assertEqual(self.gate.wait(1000),0)
        self.assertAlmostEqual(self.gate.wait(1000),3.2)

    def test_rolling_request_limit(self):
        starts=[]
        for _ in range(45):
            self.gate.wait(1000)
            starts.append(self.now)
        for end in starts:
            self.assertLessEqual(sum(end-60 < start <= end for start in starts),20)

    def test_rolling_token_reservations(self):
        self.gate.wait(60000)
        self.assertGreaterEqual(self.gate.wait(60000),60)
        with self.assertRaises(ValueError):
            self.gate.wait(100001)


if __name__=='__main__':
    unittest.main()
