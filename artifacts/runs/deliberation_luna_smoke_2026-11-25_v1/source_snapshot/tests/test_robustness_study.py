from dataclasses import replace
import json
from pathlib import Path
import unittest

from src.experiment import Config, ACTION, make_agent, profiles, simulate
from src.models import TracedModel, BEGIN, END
from src.robustness_study import study_plan


def state_from(prompt):
    return json.loads(prompt.split(BEGIN,1)[1].split(END,1)[0])


class RobustnessStudyTests(unittest.TestCase):
    def test_plan_budget_and_matching_cells(self):
        plan=study_plan()
        self.assertEqual(len(plan),11)
        self.assertEqual(sum(c.rounds*c.population for c in plan),264)
        for seed in (22,33):
            configs=[c for c in plan if c.seed==seed]
            self.assertEqual(len(configs),4)
            self.assertTrue(all(profiles(c)==profiles(configs[0]) for c in configs))
        cells=[(c.memory_rounds,c.include_initial_opinion) for c in plan if c.seed==11]
        self.assertEqual(set(cells),{(4,True),(1,False),(4,False)})

    def test_default_context_matches_archived_prompt_after_round_one(self):
        archive=Path('artifacts/runs/live_pilot_2026-11-23_v1/combined.json')
        if not archive.exists():self.skipTest('Historical pilot is optional for a fresh checkout')
        previous=json.loads(archive.read_text(encoding='utf-8'))
        reference=next(c for c in previous['calls'] if c['agent']==0 and c['round']==2)
        state=state_from(reference['prompt'])
        config=Config()
        model=TracedModel()
        agent=make_agent(previous['profiles'][0],config,model)
        agent.get_component('decision').opinion=state['opinion']
        agent.observe(json.dumps({'kind':'tick','round':2}))
        for event in state['exposures']:agent.observe(json.dumps(event))
        agent.act(ACTION)
        self.assertEqual(model.calls[0]['prompt'],reference['prompt'])

    def test_anchor_toggle_preserves_current_opinion_and_exposures(self):
        config=Config(memory_rounds=4)
        model_a=TracedModel();model_b=TracedModel()
        a=make_agent(profiles(config)[0],config,model_a)
        b=make_agent(profiles(config)[0],replace(config,include_initial_opinion=False),model_b)
        for agent in (a,b):
            agent.get_component('decision').opinion=.23
            agent.observe(json.dumps({'kind':'tick','round':3}))
            agent.observe(json.dumps({'kind':'news','round':1,'value':.8,'message':'fixed event'}))
            agent.act(ACTION)
        state_a=state_from(model_a.calls[0]['prompt']);state_b=state_from(model_b.calls[0]['prompt'])
        self.assertEqual(state_b['opinion'],.23)
        self.assertNotIn('initial_opinion',state_b)
        del state_a['initial_opinion']
        self.assertEqual(state_a,state_b)

    def test_disabled_anchor_survives_state_round_trip(self):
        config=Config(include_initial_opinion=False)
        a=make_agent(profiles(config)[0],config,TracedModel())
        b=make_agent(profiles(config)[0],config,TracedModel())
        b.set_state(json.loads(json.dumps(a.get_state())))
        self.assertFalse(b.get_component('decision').include_initial_opinion)
        self.assertEqual(a.get_state(),b.get_state())

    def test_historical_state_defaults_to_enabled_anchor(self):
        config=Config()
        agent=make_agent(profiles(config)[0],config,TracedModel())
        state=agent.get_state()
        del state['context_components']['decision']['include_initial_opinion']
        agent.set_state(state)
        self.assertTrue(agent.get_component('decision').include_initial_opinion)


if __name__=='__main__':unittest.main()
