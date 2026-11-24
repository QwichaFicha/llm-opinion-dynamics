"""Analyse the first live pilot and create a separate Russian PDF/HTML report."""
import argparse
import csv
from datetime import datetime
from html import escape
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'artifacts/setup/matplotlib-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image
from src.experiment import Config, mathematical_baseline
from src.policy import metrics, validate_action


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default='artifacts/runs/live_pilot_2026-11-23_v1')
    args=parser.parse_args();inp=Path(args.input)
    protocol=json.loads((inp/'protocol.json').read_text(encoding='utf-8'))
    execution=json.loads((inp/'execution.json').read_text(encoding='utf-8'))
    names=['smoke']+protocol['conditions']
    results={name:json.loads((inp/(name+'.json')).read_text(encoding='utf-8')) for name in names if (inp/(name+'.json')).exists()}
    main_runs={name:r for name,r in results.items() if name!='smoke'}
    calls=[c for r in results.values() for c in r['calls']]
    success=[c for c in calls if c['status']=='ok']
    valid=0;invalid=[]
    for c in success:
        try:validate_action(c['response']);valid+=1
        except Exception:invalid.append({'condition':next(n for n,r in results.items() if c in r['calls']), 'round':c['round'],'agent':c['agent']})
    def tokens(field):return sum((c.get('usage') or {}).get(field,0) or 0 for c in success)
    latencies=[c['network_seconds'] for c in calls if 'network_seconds' in c]
    percentile=lambda values,p:sorted(values)[round((len(values)-1)*p)] if values else None
    summary={'status':execution['status'],'model':protocol['model'],'provider_models':sorted({c.get('provider_model','unknown') for c in success}),
        'request_count':len(calls),'successful_responses':len(success),'valid_actions':valid,'invalid_actions':invalid,
        'prompt_tokens':tokens('prompt_tokens'),'completion_tokens':tokens('completion_tokens'),'total_tokens':tokens('total_tokens'),
        'cached_prompt_tokens':sum(((c.get('usage') or {}).get('prompt_tokens_details') or {}).get('cached_tokens',0) or 0 for c in success),
        'network_seconds_median':statistics.median(latencies) if latencies else None,'network_seconds_p95':percentile(latencies,.95),
        'network_seconds_max':max(latencies) if latencies else None,
        'rate_limit_wait_seconds':sum(c.get('rate_limit_wait_seconds',0) for c in calls),
        'simulation_seconds':sum(r['duration_seconds'] for r in results.values()),
        'http_errors':[c.get('http_status') for c in calls if c.get('http_status')],
        'runs':[]}
    rows=[]
    for name,r in main_runs.items():
        cfg=Config(**r['config']);base=mathematical_baseline(cfg)
        bmetrics=metrics(base[0],base[-1],r['edges'])
        row={'condition':name,'status':r['status'],'requests':len(r['calls']),
            'completed_rounds':len(r['trajectory'])-1,'seconds':r['duration_seconds'],
            'initial_mean':r['trajectory'][0]['mean_opinion'],
            **{k:v for k,v in r['final_metrics'].items() if k not in ('round','opinions')},
            'baseline_mean':bmetrics['mean_opinion'],'baseline_variance':bmetrics['variance'],
            'baseline_abs_shift':bmetrics['mean_abs_shift'],
            'prompt_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) for c in r['calls']),
            'completion_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) for c in r['calls'])}
        rows.append(row)
    summary['runs']=rows
    if set(main_runs)==set(protocol['conditions']) and all(r['status']=='ok' for r in main_runs.values()):
        f={n:r['final_metrics']['mean_opinion'] for n,r in main_runs.items()}
        summary['paired_mean_contrasts']={'news_minus_control':f['news_only']-f['control'],
            'peers_minus_control':f['peers_only']-f['control'],'combined_minus_control':f['combined']-f['control'],
            'interaction_combined_minus_news_minus_peers_plus_control':f['combined']-f['news_only']-f['peers_only']+f['control']}
    (inp/'analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    if rows:
        with (inp/'summary.csv').open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    reports=ROOT/'reports';figdir=reports/'figures';figdir.mkdir(exist_ok=True)
    labels={'control':'Без воздействий','news_only':'Только новости','peers_only':'Только общение','combined':'Новости и общение'}
    palette=['#728195','#ba7d31','#607bb0','#087e8b']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(10,3.6))
    for (name,r),color in zip(main_runs.items(),palette):
        for ax,key in zip(axes,['mean_opinion','variance']):
            ax.plot([t['round'] for t in r['trajectory']],[t[key] for t in r['trajectory']],label=labels[name],marker='o',markersize=3,color=color)
            ax.set_xlabel('Раунд');ax.set_xticks(range(5));ax.grid(alpha=.2)
    axes[0].set_title('Средняя позиция');axes[1].set_title('Дисперсия')
    axes[1].legend(fontsize=8);fig.suptitle('Реальная LLM: bonsai2-27b; seed=11; один прогон условия',fontsize=11)
    fig.tight_layout();fig.savefig(figdir/'live_dynamics.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(10,6),sharex=True,sharey=True)
    for ax,(name,r) in zip(axes.ravel(),main_runs.items()):
        for i in range(6):
            ax.plot([t['round'] for t in r['trajectory']],[t['opinions'][i] for t in r['trajectory']],marker='o',markersize=3,label=f'Агент {i}')
        ax.set(title=labels[name],ylim=(-1,1),xticks=range(5));ax.grid(alpha=.2)
    axes[0,0].legend(ncol=3,fontsize=7);fig.supxlabel('Раунд');fig.supylabel('Заявленная позиция');fig.tight_layout()
    fig.savefig(figdir/'live_individual.png',dpi=180);plt.close(fig)
    pages=[]
    def page(title):part=[('h1',title)];pages.append(part);return part
    def p(part,text):part.append(('p',text))
    def h(part,text):part.append(('h2',text))
    def table(part,headers,values,widths):part.append(('table',(headers,values,widths)))
    def image(part,name):part.append(('image',name))
    def code(part,text):part.append(('code',text))
    fmt=lambda x:f'{x:.4f}'
    s=page('Первый пилот с реальной LLM')
    p(s,'Дополнение к отчёту о прототипе коллективных предпочтений. 23 ноября 2026 года. Фреймворк: Concordia 2.4.0. Модель: bonsai2-27b. Исходная идея: формирование и изменение коллективных предпочтений под воздействием информации, общения и памяти.')
    h(s,'Статус выполненной серии')
    p(s,f"Проверка подключения и основная серия имеют статус: {summary['status']}. Выполнено {len(calls)} реальных запросов; успешных ответов {len(success)}, валидных действий {valid}. Запрошенный предел: 102 запроса. Набор включает smoke на шести агентах и четыре условия по четыре раунда. В отличие от первого этапа здесь действительно использовался внешний LLM API.")
    table(s,['Показатель','Фактическое значение'],[
        ['Шлюз',protocol['base_url']],['Модель в ответах',', '.join(summary['provider_models'])],
        ['Результат основной серии',f"{sum(r['status']=='ok' for r in main_runs.values())}/{len(main_runs)} условий завершены"],
        ['Входные / выходные токены',f"{summary['prompt_tokens']} / {summary['completion_tokens']}"],
        ['Всего токенов',str(summary['total_tokens'])],
        ['Длительность симуляций',f"{summary['simulation_seconds']:.1f} с"],
        ['Невалидные действия',str(len(invalid))],['HTTP-ошибки',str(summary['http_errors'])]],[.43,.57])
    p(s,'Денежная стоимость неизвестна: тариф шлюза не предоставлен. Числа токенов взяты из usage реальных ответов. Указанные кэшированные токены входят в prompt_tokens; они не прибавляются к общему числу повторно.')
    p(s,'Это инженерный пилот с одним начальным состоянием на условие. Он проверяет интеграцию и позволяет выявить проблемы протокола. Он не является статистическим подтверждением социальной гипотезы и не валидирует модель на поведении людей. Первоначальные результаты с численной заглушкой сохранены отдельно.')

    s=page('1. Подключение и ограничения шлюза')
    p(s,'В локальном .env был заполнен ключ, но остались стандартный OpenAI base URL и пустое имя модели. Адрес заменён на присланный пользователем шлюз, модель - на bonsai2-27b. Сам ключ не выводился в инструменты, не передавался в промпты и не включался в протокол или снимок исходного кода.')
    p(s,'Использован существующий адаптер Concordia LanguageModel с HTTP POST /chat/completions. Системное сообщение задаёт симуляцию вымышленного участника и JSON-ответ, пользовательское содержит сценарий, профиль, текущую позицию и разрешённые наблюдения. Реальные ответные объекты содержат имя модели, идентификатор ответа, finish_reason и usage, которые сохранены в журналах.')
    table(s,['Ограничение','Реализация'],[
        ['20 запросов / мин','Общий для процесса шлюз запросов: не менее 3.2 с между стартами и проверка скользящего окна 60.1 с'],
        ['100 000 токенов / мин','Предварительное консервативное резервирование: UTF-8 байты текста, бюджет ответа и запас на оформление сообщений'],
        ['Не больше двух одновременно','Пилот использует один одновременный запрос; общая блокировка на сетевой вызов'],
        ['Бюджет серии','Smoke 6 запросов, затем 4 × 24; автоматические повторы отсутствуют'],
        ['Параметры генерации',f"temperature={protocol['generation']['temperature']}, max_tokens={protocol['generation']['max_tokens']}; reasoning не включался явно"],
        ['Останов при ошибке','Серия прерывается после первого неуспешного условия; сырые ответы и частичный результат сохраняются']],[.3,.7])
    p(s,'Скорость ограничивается внутри одного процесса. Этот механизм не координирует одновременно запущенные независимые процессы или другие программы, использующие тот же личный ключ. Во время следующей серии следует запускать один исполнитель. Токенный лимит применяется к предварительной оценке; фактический расход отдельно сверяется по usage.')
    p(s,'Срок действия и остальные свойства шлюза взяты из сообщения пользователя. Картинки, bbox, tool calling, контекст 192K и режим reasoning в этом опыте не проверялись: для задачи использованы только короткие текстовые запросы.')

    s=page('2. Сценарий и план сравнения')
    p(s,'Шесть агентов выбирают развитие вымышленной библиотеки: +1 означает приоритет цифрового доступа, -1 - печатных книг. Роли: студент, родитель, библиотекарь, учитель, пенсионер и разработчик. У каждого фиксированы исходная позиция и доверие источнику. Все четыре условия используют одни и те же профили, seed=11 и начальные позиции.')
    initial=next(iter(results.values()))['trajectory'][0]['opinions']
    code(s,'Исходные позиции:\n'+json.dumps(initial)+'\nСеть: кольцо, по два соседа у агента.\nОкно извлечения памяти: один раунд.')
    table(s,['Условие','Отличие'],[[labels[n],{'control':'Нет ни новостей, ни сообщений соседей','news_only':'Один информационный импульс +0.8 в первом раунде; общения нет','peers_only':'Сообщения соседей из предыдущего раунда; новостей нет','combined':'Один информационный импульс и общение по кольцу'}[n]] for n in protocol['conditions']],[.31,.69])
    p(s,'Новость сообщает, что вымышленный опрос поддерживает цифровой доступ. Сообщения соседей передаются вместе с их явной численной позицией. Это проверка совместного влияния текста и самооценки позиции, а не чисто текстового убеждения. Все наблюдения раунда формируются по снимку предыдущего состояния до первого действия текущего раунда.')
    p(s,'Ответ должен быть JSON ровно с двумя полями: opinion - конечное число в [-1,1], message - строка от 1 до 800 символов. Модель может оставить или изменить позицию; закон численного обновления ей не навязывается. Действие проходит строгую проверку перед фиксацией. Собственные тексты прошлых действий не включаются в память автоматически: между раундами переносится текущая позиция, а память содержит внешние наблюдения.')
    p(s,'Для сравнения сохранён расчёт линейного правила первого этапа с теми же профилями, графом и условиями. Оно имеет коэффициенты 0.25 для доверия новости и 0.30 для соседей. Совпадение с ним не является целью LLM: это прозрачная точка отсчёта для характера и масштаба изменений.')

    s=page('3. Коллективные результаты')
    table(s,['Условие','Среднее LLM','Дисперсия','|Сдвиг|','Среднее правила'],[
        [labels[r['condition']],fmt(r['mean_opinion']),fmt(r['variance']),fmt(r['mean_abs_shift']),fmt(r['baseline_mean'])] for r in rows],[.29,.18,.17,.17,.19])
    p(s,'Все значения - финал четвёртого раунда одного прогона на условие. Средний модуль сдвига считается относительно индивидуальных исходных позиций. Дисперсия отражает разброс шести заявленных оценок. Она сама по себе не доказывает или опровергает поляризацию.')
    image(s,'live_dynamics.png')
    if 'paired_mean_contrasts' in summary:
        contrasts=summary['paired_mean_contrasts']
        p(s,f"Разности итоговых средних относительно контроля: новости {contrasts['news_minus_control']:+.4f}, общение {contrasts['peers_minus_control']:+.4f}, совместное условие {contrasts['combined_minus_control']:+.4f}. Контраст взаимодействия combined - news_only - peers_only + control равен {contrasts['interaction_combined_minus_news_minus_peers_plus_control']:+.4f}.")
    p(s,'Эти контрасты описывают данный прогон. Случайность генерации, особенности ролей и формулировок пока не отделены от эффектов условий. При одном прогоне нет оценки дисперсии между независимыми симуляциями и нет оснований сообщать статистическую значимость. Отдельные агенты внутри одной взаимодействующей сети не являются независимыми повторениями эксперимента.')

    s=page('4. Что показывают различия с численным правилом')
    if all(n in main_runs for n in protocol['conditions']):
        c=main_runs['control']['final_metrics'];n=main_runs['news_only']['final_metrics']
        peers=main_runs['peers_only']['final_metrics'];joint=main_runs['combined']['final_metrics']
        p(s,f"Без новых воздействий средний модуль сдвига равен {c['mean_abs_shift']:.6f}. Малые сдвиги в контроле связаны с изменением самооценки модели; в сохранённых траекториях видно округление исходных значений. Контроль не обязан быть строго неподвижным, как детерминированная заглушка, поэтому его необходимо запускать вместе с опытными условиями.")
        p(s,f"Новость дала среднюю итоговую позицию {n['mean_opinion']:.4f} против {c['mean_opinion']:.4f} в контроле. Индивидуальный средний модуль сдвига составил {n['mean_abs_shift']:.4f}. Это реакция на единственный информационный импульс в выбранном контексте, а не оценка универсальной восприимчивости к новостям.")
        start_var=main_runs['peers_only']['trajectory'][0]['variance']
        base_row=next(row for row in rows if row['condition']=='peers_only')
        p(s,f"При одном общении дисперсия изменилась с {start_var:.4f} до {peers['variance']:.4f}; у линейного контроля итоговая дисперсия {base_row['baseline_variance']:.4f}. В данном прогоне реальная LLM не воспроизвела усреднение, автоматически заложенное в численное правило. Следовательно, численное влияние соседей и текстовая реакция модели не взаимозаменяемы.")
        p(s,f"В совместном условии средняя позиция равна {joint['mean_opinion']:.4f}, дисперсия {joint['variance']:.4f}. Его отличие от отдельных каналов необходимо проверять повторениями, поскольку одна пара прогонов не отделяет взаимодействие факторов от вариативности генерации.")
        table(s,['Условие','A','B','Нейтральные','Прямые смены стороны'],[
            [labels[name],f"{r['final_metrics']['a_share']:.0%}",f"{r['final_metrics']['b_share']:.0%}",f"{r['final_metrics']['undecided_share']:.0%}",str(r['final_metrics']['switches'])] for name,r in main_runs.items()],[.32,.12,.12,.19,.25])
        p(s,'Границы категорий: A при x > 0.1, B при x < -0.1, остальные относятся к нейтральной зоне. Прямая смена стороны считается относительно исходного знака за этими порогами. Даже при сохранении всех исходных сторон могут меняться интенсивность предпочтений и тексты аргументов.')
    p(s,'Содержательная реализуемость подтверждена в узком смысле: модель возвращает разные состояния и аргументы под разными наблюдениями, а фреймворк позволяет их измерять. Интерпретировать найденные отличия как закономерности реального сообщества пока нельзя. Для этого нужны заранее заданные гипотезы, устойчивость к промптам и внешняя валидация.')

    s=page('5. Индивидуальные траектории и тексты')
    image(s,'live_individual.png')
    p(s,'Индивидуальные траектории позволяют отличать сохранение исходных сторон, переходы через нейтральную зону и небольшое округление чисел. При анализе нельзя считать любой ненулевой сдвиг результатом убеждения: в контроле возможны дрейф самооценки и приведение позиции к удобному числу.')
    h(s,'Примеры реальных ответов модели')
    for name in ('control','news_only','peers_only','combined'):
        if name in main_runs and main_runs[name]['calls']:
            raw=main_runs[name]['calls'][-6]['response'] if len(main_runs[name]['calls'])>=6 else main_runs[name]['calls'][0]['response']
            try:
                answer=validate_action(raw);text=answer['message']
                snippet=text[:260]+('…' if len(text)>260 else '')
                p(s,f"{labels[name]}, агент 0, последний завершённый раунд, opinion={answer['opinion']}: «{snippet}»")
            except Exception: p(s,f'{labels[name]}: пример невалиден; см. сырой журнал.')
    p(s,'Приведены сокращённые фрагменты сгенерированных ответов; полный английский текст сохранён в JSON. Они демонстрируют формат аргументации, но текстовое объяснение модели нельзя автоматически считать достоверным описанием причин изменения позиции.')

    s=page('6. Скорость, токены и воспроизводимость')
    table(s,['Условие','Запросы','Вход','Выход','Время, с'],[
        [labels[r['condition']],str(r['requests']),str(r['prompt_tokens']),str(r['completion_tokens']),f"{r['seconds']:.1f}"] for r in rows],[.32,.14,.18,.18,.18])
    if latencies:
        p(s,f"По всей серии со smoke медиана сетевого вызова {summary['network_seconds_median']:.2f} с, 95-й перцентиль по ближайшему рангу {summary['network_seconds_p95']:.2f} с, максимум {summary['network_seconds_max']:.2f} с. Ожидание ограничителя суммарно заняло {summary['rate_limit_wait_seconds']:.1f} с. Время симуляции включает эти паузы, сборку агентов и сохранение промежуточных результатов.")
    p(s,f"Шлюз сообщил о {summary['cached_prompt_tokens']} кэшированных входных токенах. Полный расход с проверкой подключения: {summary['total_tokens']} токенов. Поскольку тариф неизвестен, денежный эквивалент не рассчитывается. Скорость локальной заглушки из первого отчёта нельзя переносить на реальный API.")
    h(s,'Что сохранено')
    p(s,'protocol.json содержит план и SHA-256 исходного кода. Папка source_snapshot хранит использованные модули и исполнитель серии. Каждый результат содержит конфигурацию, профили, граф, события, позиции по раундам, точные промпты, системное сообщение, ответы, метаданные провайдера, usage, сетевое время и ожидание ограничителя. checkpoint-файлы обновлялись после каждого валидного ответа.')
    p(s,'Добавлены корректные started_utc и finished_utc для новых запусков. Исторические файлы первого этапа не исправлялись задним числом. Для новой серии не передавался provider seed: seed=11 управляет только профилями симуляции. В протоколе хранится запрошенное имя модели и имя из ответа; неизменность внутренней версии весов шлюзом отдельно не гарантирована.')
    p(s,'Перед запуском пройдены 17 тестов: прежние 14 и три проверки ограничителя на виртуальном времени. Проверены минимальный интервал, скользящий лимит запросов и резервирование токенов. Подставной транспорт в тестах не делает сетевых запросов и не расходует личный лимит.')

    s=page('7. Сложность и ограничения интерпретации')
    table(s,['Этап','Сложность','Наблюдение'],[
        ['Настройка провайдера','1/5','Потребовалось указать base URL и модель; существующий текстовый API-контракт подошёл'],
        ['Ограничения шлюза','3/5','Потребовались общий для процесса ограничитель, учёт скользящих окон и раздельное измерение ожидания/сети'],
        ['Формат ответов','2/5',f'Сохранено {valid} валидных действий из {len(success)} успешных ответов; формат проверяется строго'],
        ['Проведение серии','2/5','Последовательное исполнение, проверки после каждого ответа и останов при ошибке'],
        ['Научная интерпретация','4/5','Нужно отделить взаимодействие, знания самой модели, роли, округление и случайность генерации']],[.27,.16,.57])
    p(s,'Шкала сложности - инженерная оценка: 1 означает штатную настройку, 3 - специальную реализацию или диагностику, 5 - отдельный исследовательский этап. Человеко-часы не измерялись. Возможность получить правдоподобный текст быстро не снимает сложности проверки механизмов.')
    h(s,'Ограничения, выявленные или сохраняющиеся')
    p(s,'Профиль содержит исходную позицию на каждом шаге, поэтому модель видит постоянный численный якорь; собственная прошлая аргументация в контекст не возвращается. Роли могут включать стереотипы из знаний модели. Доверие передаётся числом, но его использование не навязано и не измерено отдельно. Новости представляют собой один короткий вымышленный опрос, а не сопоставимые по качеству реальные источники.')
    p(s,'Память равна одному раунду, сеть фиксирована, агенты не выбирают собеседников. Все используют одну LLM и один общий системный промпт. Четыре раунда и шесть участников не позволяют делать выводы о долгосрочной коллективной динамике. Численное заявление позиции не равно реальному выбору человека, а сгенерированное объяснение не является причинным свидетельством.')
    p(s,'Общий исходный seed делает условия сопоставимыми по профилям, но не устраняет недетерминированность LLM. Не проводились независимые повторы, перестановки ролей и имён, перефразирование новости, отрицательная новость, другие модели или сравнение с реальными данными. Эти проверки должны предшествовать сильным выводам об эффекте общения.')

    s=page('8. Что делать следующим')
    p(s,'Сначала оценить контроль: масштаб самопроизвольного дрейфа, округление и возможные переходы стороны без новых наблюдений. Затем сравнить покомпонентные разности с новостным и коммуникативным условиями, не ограничиваясь средним сообщества. Текущий стенд позволяет это делать по сохранённым траекториям без повторного обращения к API.')
    p(s,'Следующая содержательная серия: четыре базовых условия для seed 22, 33, 44, 55, затем независимые повторы генерации при фиксированном профиле. Перед ней определить критерии допустимого дрейфа, минимального интересующего эффекта, число повторов и токенный бюджет. Четыре дополнительных seed дают до 384 запросов; отдельные повторы увеличивают этот объём и должны учитываться заранее.')
    p(s,'После устойчивого базового сравнения проверить память и структуру сети: combined_memory4, complete и segregated. Отдельно убрать из наблюдений численные позиции соседей, чтобы сравнить текстовое влияние с численным якорем. Для памяти добавить передачу собственных прошлых аргументов и сравнить её с переносом только текущей позиции.')
    h(s,'Повторение технической серии')
    code(s,'.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v\n.\\.venv\\Scripts\\python.exe scripts/run_live_pilot.py --output artifacts/runs/live_pilot_repeat_01\n.\\.venv\\Scripts\\python.exe scripts/build_live_report.py --input artifacts/runs/live_pilot_repeat_01')
    p(s,'Повторный live-запуск снова расходует до 102 запросов. Для офлайн-анализа уже полученных данных достаточно команды build_live_report.py с текущим каталогом; она не обращается к шлюзу. По умолчанию имена отчётов фиксированы, поэтому перед отдельным исследовательским повтором сохранять новую версию отчёта.')
    table(s,['Путь','Содержание'],[
        [str(inp).replace('\\','/'),'Исходные результаты этой серии, checkpoints, protocol и снимок кода'],
        ['analysis.json; summary.csv','Сводные метрики и расход токенов в папке серии'],
        ['reports/live_pilot_report.pdf','Это дополнение к первоначальному отчёту'],
        ['reports/live_pilot_report.html','Редактируемая HTML-версия'],
        ['reports/experiment_report.pdf','Исторический отчёт о численном этапе, сохранён отдельно']],[.51,.49])
    p(s,'Фактические утверждения этого дополнения основаны на локальных ответах шлюза и журналах серии. Социальная постановка взята из первой идеи пользователя. Новые внешние публикации для этого технического теста не использовались.')

    pdfmetrics.registerFont(TTFont('LiveArial',r'C:\Windows\Fonts\arial.ttf'))
    pdfmetrics.registerFont(TTFont('LiveArialBold',r'C:\Windows\Fonts\arialbd.ttf'))
    styles={'h1':ParagraphStyle('lh1',fontName='LiveArialBold',fontSize=18,leading=23,textColor=colors.HexColor('#12314b'),spaceAfter=16),
        'h2':ParagraphStyle('lh2',fontName='LiveArialBold',fontSize=11.5,leading=16,textColor=colors.HexColor('#087e8b'),spaceBefore=9,spaceAfter=6),
        'p':ParagraphStyle('lp',fontName='LiveArial',fontSize=10,leading=14.4,spaceAfter=9),
        'cell':ParagraphStyle('lc',fontName='LiveArial',fontSize=8.8,leading=12),
        'th':ParagraphStyle('lth',fontName='LiveArialBold',fontSize=8.8,leading=12,textColor=colors.white),
        'code':ParagraphStyle('lcode',fontName='LiveArial',fontSize=8.2,leading=12,backColor=colors.HexColor('#eef3f7'),borderPadding=8,spaceAfter=12)}
    width=A4[0]-88;story=[];html=[]
    para=lambda text,style:Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
    for i,part in enumerate(pages):
        if i:story.append(PageBreak())
        html.append('<section>')
        for kind,value in part:
            if kind in ('h1','h2','p','code'):
                story.append(para(value,kind));tag='pre' if kind=='code' else kind
                html.append(f'<{tag}>{escape(value)}</{tag}>')
            elif kind=='image':
                from PIL import Image as PI
                with PI.open(figdir/value) as im:w,h_=im.size
                story.extend([Image(str(figdir/value),width=width,height=width*h_/w),Spacer(1,8)])
                html.append(f'<img src="figures/{value}" alt="Результаты LLM">')
            else:
                headers,values,widths=value
                contents=[[para(x,'th') for x in headers]]+[[para(x,'cell') for x in row] for row in values]
                t=Table(contents,colWidths=[width*w for w in widths],repeatRows=1)
                t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#12314b')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f0f5f7'),colors.white]),
                    ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
                story.extend([t,Spacer(1,11)])
                html.append('<table><tr>'+''.join('<th>'+escape(str(x))+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in values)+'</table>')
        html.append('</section>')
    def footer(canvas,doc):
        canvas.setFont('LiveArial',8);canvas.setFillColor(colors.HexColor('#526779'))
        canvas.drawString(44,26,'Concordia | bonsai2-27b | Реальный LLM-пилот | 23.11.2026')
        canvas.drawRightString(A4[0]-44,26,str(doc.page))
    pdf=reports/'live_pilot_report.pdf'
    SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=42,bottomMargin=53,
        title='Первый пилот коллективных предпочтений с bonsai2-27b').build(story,onFirstPage=footer,onLaterPages=footer)
    css='body{font-family:Arial,sans-serif;background:#eaf0f4;color:#172b3b;line-height:1.55}main{max-width:940px;margin:auto}section{background:white;padding:40px 50px;margin:20px 0}h1{color:#12314b;line-height:1.3}h2{color:#087e8b}table{border-collapse:collapse;width:100%;font-size:14px;margin:18px 0}th{background:#12314b;color:white;text-align:left}td,th{padding:9px;vertical-align:top;overflow-wrap:anywhere}tr:nth-child(even){background:#f0f5f7}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f7;padding:14px}img{width:100%}p{overflow-wrap:anywhere}@media print{section{break-before:page}section:first-child{break-before:auto}}'
    (reports/'live_pilot_report.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Первый LLM-пилот</title><style>'+css+'</style><main>'+''.join(html)+'</main></html>',encoding='utf-8')
    print(json.dumps({**summary,'pdf_pages':len(PdfReader(pdf).pages)},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
