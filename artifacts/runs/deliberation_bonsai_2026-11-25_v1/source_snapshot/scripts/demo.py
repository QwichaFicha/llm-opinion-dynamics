"""Short offline demo: recorded real LLM results or a genuine Concordia stub run."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def recorded():
    read=lambda path:json.loads((ROOT/path).read_text(encoding='utf-8'))
    data=read('artifacts/runs/robustness_study_2026-11-23_v1/analysis.json')
    print('DEMO: записанные реальные ответы bonsai2-27b; новых API-запросов нет.\n')
    print('1. Агенты меняют силу предпочтений: цифровой доступ (+1) / печатные книги (-1).')
    print('   Шесть участников, кольцо контактов, четыре раунда.\n')
    print('2. Общение: итоговая дисперсия минус контроль с теми же профилями.')
    for row in data['paired_profile_contrasts']:
        if row['condition']=='peers_only':
            print(f"   seed={row['seed']}: {row['variance_minus_control']:+.4f}")
    print('   Направление эффекта меняется между наборами профилей.\n')
    print('3. Память и поле исходной позиции, seed=11:')
    for row in data['conditions']:
        if row['seed']==11 and row['condition'] in ('combined','combined_memory4','combined_no_initial','combined_memory4_no_initial'):
            print(f"   H={row['memory_rounds']}, initial_opinion={row['include_initial_opinion']}: "
                  f"дисперсия={row['variance']:.4f}; |сдвиг|={row['mean_abs_shift']:.4f}")
    print('\nВывод: стенд работает; выводы чувствительны к профилям и составу контекста.')
    print('Это проверка реализуемости, а не доказательство поведения людей.')
    print('\nДля показа откройте demo/replay.html. Для нового локального запуска:')
    print('  python scripts/demo.py --offline')


def offline():
    from src.experiment import Config,simulate
    result=simulate(Config(name='classroom_offline_demo',rounds=1),'stub',max_calls=6)
    print('DEMO: новый локальный запуск компонентов Concordia с численной заглушкой.')
    print('LLM API и ключ не используются. Это техническая проверка, не новый LLM-опыт.\n')
    for profile,initial,final in zip(result['profiles'],result['trajectory'][0]['opinions'],result['final_metrics']['opinions']):
        print(f"   Агент {profile['id']} ({profile['role']}): {initial:+.4f} -> {final:+.4f}")
    print(f"\nConcordia {result['versions']['concordia']}; status={result['status']}; "
          f"вызовов заглушки={len(result['calls'])}; внешних запросов=0")
    if result['status']!='ok':raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true',help='Run actual Concordia agents with a deterministic stub')
    args=parser.parse_args()
    offline() if args.offline else recorded()
