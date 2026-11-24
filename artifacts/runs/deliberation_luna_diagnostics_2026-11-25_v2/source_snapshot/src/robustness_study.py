"""Preregistered multi-profile replication and memory-by-anchor comparison."""
from dataclasses import replace
from .experiment import Config, conditions


def study_plan():
    selected=[]
    for seed in (22,33):
        for name in ('control','news_only','peers_only','combined'):
            c=next(c for c in conditions() if c.name==name)
            selected.append(replace(c,seed=seed))
    selected += [
        Config(name='combined_memory4',seed=11,memory_rounds=4),
        Config(name='combined_no_initial',seed=11,include_initial_opinion=False),
        Config(name='combined_memory4_no_initial',seed=11,memory_rounds=4,include_initial_opinion=False),
    ]
    return selected
