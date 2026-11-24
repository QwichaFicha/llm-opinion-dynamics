import json
import unittest
from src.experiment import Config, ACTION, make_agent, profiles
from src.models import BEGIN, END, TracedModel
from src.quality_checks import build_diagnostic, diagnostic_plan, objective_cases, VARIANTS


def parse_state(prompt):
    return json.loads(prompt.split(BEGIN,1)[1].split(END,1)[0])


class QualityProtocolTests(unittest.TestCase):
    def test_plan_count_and_pairs(self):
        plan=diagnostic_plan()
        self.assertEqual(len(plan),60)
        self.assertEqual(len({x['id'] for x in plan}),60)
        for variant in VARIANTS:
            self.assertEqual(sum(x.get('variant')==variant for x in plan),6)
        self.assertEqual(len(objective_cases()),12)

    def test_original_matches_production_prompt(self):
        profile=profiles(Config())[0]
        a_model=TracedModel();b_model=TracedModel()
        original=make_agent(profile,Config(),a_model)
        original.observe(json.dumps({'kind':'tick','round':1}))
        test=build_diagnostic(profile,'control_original',b_model)
        self.assertEqual(original.act(ACTION),test.act(ACTION))
        self.assertEqual(a_model.calls[0]['prompt'],b_model.calls[0]['prompt'])

    def test_omit_initial_preserves_other_state(self):
        profile=profiles(Config())[2]
        first=TracedModel();second=TracedModel()
        build_diagnostic(profile,'positive_original',first).act(ACTION)
        build_diagnostic(profile,'positive_without_initial',second).act(ACTION)
        a=parse_state(first.calls[0]['prompt']);b=parse_state(second.calls[0]['prompt'])
        del a['initial_opinion']
        self.assertEqual(a,b)

    def test_paraphrase_only_changes_news_text(self):
        profile=profiles(Config())[1]
        first=TracedModel();second=TracedModel()
        build_diagnostic(profile,'negative_original',first).act(ACTION)
        build_diagnostic(profile,'negative_paraphrase',second).act(ACTION)
        a=parse_state(first.calls[0]['prompt']);b=parse_state(second.calls[0]['prompt'])
        self.assertNotEqual(a['exposures'][0].pop('message'),b['exposures'][0].pop('message'))
        self.assertEqual(a,b)


if __name__=='__main__':
    unittest.main()
