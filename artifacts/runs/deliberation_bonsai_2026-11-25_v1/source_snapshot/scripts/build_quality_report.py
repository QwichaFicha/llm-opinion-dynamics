"""Compare the follow-up diagnostics with the preserved first live pilot."""
import argparse
import csv
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
from src.quality_checks import VARIANTS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default='artifacts/runs/quality_study_2026-11-23_v1')
    args=parser.parse_args();out=Path(args.input)
    previous=ROOT/'artifacts/runs/live_pilot_2026-11-23_v1'
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
    diagnostics=json.loads((out/'diagnostics.json').read_text(encoding='utf-8'))['results']
    objectives=[r for r in diagnostics if r['kind']=='objective']
    agent_results=[r for r in diagnostics if r['kind']=='agent']
    variants={v:sorted([r for r in agent_results if r['variant']==v],key=lambda r:r['agent']) for v in VARIANTS}
    initial={i:next(p['profile']['initial_opinion'] for p in protocol['plan'] if p['kind']=='agent' and p['profile']['id']==i) for i in range(6)}
    vector=lambda v:[r['action']['opinion'] for r in variants[v]]
    vrows=[]
    for v in VARIANTS:
        valid=[r for r in variants[v] if r['status']=='ok']
        xs=[r['action']['opinion'] for r in valid]
        vrows.append({'variant':v,'responses':len(variants[v]),'valid':len(valid),
            'mean_opinion':statistics.mean(xs) if xs else None,
            'mean_signed_shift':statistics.mean(r['action']['opinion']-initial[r['agent']] for r in valid) if xs else None,
            'mean_abs_shift':statistics.mean(abs(r['action']['opinion']-initial[r['agent']]) for r in valid) if xs else None})
    pairs=[]
    for first,second,tag in [('positive_original','negative_original','direction'),
            ('positive_original','positive_paraphrase','positive_paraphrase'),
            ('negative_original','negative_paraphrase','negative_paraphrase'),
            ('positive_original','positive_without_initial','positive_anchor_field'),
            ('negative_original','negative_without_initial','negative_anchor_field'),
            ('control_original','control_without_initial','control_anchor_field')]:
        if all(r['status']=='ok' for r in variants[first]+variants[second]):
            a,b=vector(first),vector(second)
            pairs.append({'comparison':tag,'first':first,'second':second,
                'mean_abs_difference':statistics.mean(abs(x-y) for x,y in zip(a,b)),
                'max_abs_difference':max(abs(x-y) for x,y in zip(a,b)),
                'equal_opinions':sum(abs(x-y)<=1e-9 for x,y in zip(a,b)),
                'first_minus_second_mean':statistics.mean(x-y for x,y in zip(a,b))})
    originals={}
    for v,n in [('control_original','control'),('positive_original','news_only')]:
        old=json.loads((previous/(n+'.json')).read_text(encoding='utf-8'))
        originals[v]={'same_prompts':sum(r['calls'][0]['prompt_sha256']==old['calls'][r['agent']]['prompt_sha256'] for r in variants[v]),
            'equal_opinions':sum(abs(r['action']['opinion']-json.loads(old['calls'][r['agent']]['response'])['opinion'])<=1e-9 for r in variants[v] if r['status']=='ok')}
    repeats=[];repeat_calls=[];repeat_data={}
    for name in protocol['repeat_conditions']:
        p=out/(name+'.json')
        if not p.exists():continue
        new=json.loads(p.read_text(encoding='utf-8'));old=json.loads((previous/(name+'.json')).read_text(encoding='utf-8'))
        repeat_data[name]=(old,new);repeat_calls.extend(new['calls'])
        comparable=list(zip(old['calls'],new['calls']))
        same_input=[(a,b) for a,b in comparable if a['prompt_sha256']==b['prompt_sha256'] and a.get('system_message')==b.get('system_message') and a.get('request_parameters')==b.get('request_parameters')]
        old_final=old['final_metrics'];new_final=new['final_metrics']
        repeats.append({'condition':name,'status':new['status'],'requests':len(new['calls']),
            'old_mean':old_final['mean_opinion'],'new_mean':new_final['mean_opinion'],
            'old_variance':old_final['variance'],'new_variance':new_final['variance'],
            'final_mean_abs_difference':statistics.mean(abs(a-b) for a,b in zip(old_final['opinions'],new_final['opinions'])),
            'identical_trajectory':old['trajectory']==new['trajectory'],
            'same_input_calls':len(same_input),
            'same_input_equal_response':sum(a['response']==b['response'] for a,b in same_input),
            'same_input_equal_opinion':sum(json.loads(a['response'])['opinion']==json.loads(b['response'])['opinion'] for a,b in same_input)})
    calls=[c for r in diagnostics for c in r['calls']]+repeat_calls
    successful=[c for c in calls if c['status']=='ok']
    usage=lambda k:sum((c.get('usage') or {}).get(k,0) or 0 for c in successful)
    summary={'request_count':len(calls),'successful_http_responses':len(successful),
        'diagnostics_count':len(diagnostics),'valid_diagnostic_actions':sum(r['status']=='ok' for r in diagnostics),
        'objective_total':len(objectives),'objective_passed':sum(r.get('passed',False) for r in objectives),
        'objective_failures':[r['id'] for r in objectives if not r.get('passed')],
        'prompt_tokens':usage('prompt_tokens'),'completion_tokens':usage('completion_tokens'),'total_tokens':usage('total_tokens'),
        'network_seconds_median':statistics.median(c['network_seconds'] for c in calls if 'network_seconds' in c),
        'diagnostic_variants':vrows,'paired_diagnostics':pairs,'first_step_repetition':originals,'trajectory_repeats':repeats,
        'gateway_models':json.loads((ROOT/'artifacts/setup/gateway_models_2026-11-23.json').read_text(encoding='utf-8'))['models'],
        'scope':'Engineering screening, not a broad benchmark or empirical human-behaviour validation',
        'public_sources':[{'url':'https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf','title':'Prism ML model card','accessed':'2026-11-23'},
            {'url':'https://prismml.com/news/bonsai-2-27b','title':'PrismML release announcement','accessed':'2026-11-23'}]}
    arithmetic_path=ROOT/'artifacts/runs/arithmetic_probe_2026-11-23_v1/results.json'
    arithmetic=json.loads(arithmetic_path.read_text(encoding='utf-8'))['results'] if arithmetic_path.exists() else []
    arithmetic_calls=[c for r in arithmetic for c in r['calls']]
    arithmetic_tokens=sum((c.get('usage') or {}).get('total_tokens',0) or 0 for c in arithmetic_calls)
    summary['arithmetic_probe']={'requests':len(arithmetic_calls),'total_tokens':arithmetic_tokens,
        'results':[{'mode':r['mode'],'mirrored':r.get('mirrored',False),'repeat':r['repeat'],
                    'passed':r['passed'],'opinion':r.get('action',{}).get('opinion'),'status':r['status']} for r in arithmetic]}
    summary['all_followup_requests']=len(calls)+len(arithmetic_calls)
    summary['all_followup_tokens']=summary['total_tokens']+arithmetic_tokens
    (out/'analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    for filename,rows in [('diagnostic_summary.csv',vrows),('repeat_summary.csv',repeats)]:
        if rows:
            with (out/filename).open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    reports=ROOT/'reports';figdir=reports/'figures';figdir.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    short={'control_original':'Контроль','positive_original':'+ новость','negative_original':'- новость',
        'positive_paraphrase':'+ перефраз','negative_paraphrase':'- перефраз',
        'positive_without_initial':'+ без initial','negative_without_initial':'- без initial','control_without_initial':'Контроль без initial'}
    fig,ax=plt.subplots(figsize=(10,3.7))
    ax.bar(range(len(vrows)),[r['mean_signed_shift'] or 0 for r in vrows],color=['#8593a4','#087e8b','#9d5e76','#087e8b','#9d5e76','#087e8b','#9d5e76','#8593a4'])
    ax.set_xticks(range(len(vrows)),[short[r['variant']] for r in vrows],rotation=20,ha='right')
    ax.set_ylabel('Средний знаковый сдвиг');ax.set_title('Одношаговые диагностические условия; 6 профилей на условие');ax.axhline(0,color='#555',lw=.7)
    fig.tight_layout();fig.savefig(figdir/'quality_diagnostics.png',dpi=180);plt.close(fig)
    if repeats:
        fig,axes=plt.subplots(1,2,figsize=(10,3.6));colors_=['#728195','#ba7d31','#607bb0','#087e8b']
        for (name,(old,new)),color in zip(repeat_data.items(),colors_):
            for ax,key in zip(axes,['mean_opinion','variance']):
                ax.plot([r['round'] for r in old['trajectory']],[r[key] for r in old['trajectory']],color=color,ls='--',alpha=.7)
                ax.plot([r['round'] for r in new['trajectory']],[r[key] for r in new['trajectory']],color=color,marker='o',markersize=3,label=name)
                ax.set_xlabel('Раунд');ax.set_xticks(range(5));ax.grid(alpha=.2)
        axes[0].set_title('Средняя позиция');axes[1].set_title('Дисперсия');axes[1].legend(fontsize=8)
        fig.suptitle('Первый запуск — пунктир; повтор — сплошная линия',fontsize=11)
        fig.tight_layout();fig.savefig(figdir/'quality_repeat.png',dpi=180);plt.close(fig)
    pages=[]
    def page(title):x=[('h1',title)];pages.append(x);return x
    def p(s,text):s.append(('p',text))
    def h(s,text):s.append(('h2',text))
    def table(s,headers,rows,widths):s.append(('table',(headers,rows,widths)))
    def image(s,name):s.append(('image',name))
    s=page('Оценка пригодности bonsai2-27b')
    p(s,'Продолжение экспериментов по формированию коллективных предпочтений. Concordia 2.4.0, шлюз ftii.llm.actcognitive.org, 23 ноября 2026 года. Этот отчёт отвечает на вопрос: есть ли основания менять модель до расширения исследования?')
    h(s,'Что именно проверено')
    table(s,['Проверка','Объём / результат'],[
        ['Формат и доступность',f"Новых запросов {len(calls)}, успешных ответов {len(successful)}"],
        ['Базовое понимание контекста',f"{summary['objective_passed']}/{len(objectives)} задач с заранее записанным численным ответом"],
        ['Знак новости и формулировки','8 одношаговых условий × 6 профилей = 48 ответов'],
        ['Повтор полных симуляций',f'{len(repeats)} условия по 24 запроса; профили и параметры сохранены'],
        ['Новые токены',str(summary['total_tokens'])],
        ['Доступные модели шлюза',', '.join(m['id'] for m in summary['gateway_models'])]],[.43,.57])
    p(s,'Задачи с эталоном проверяют копирование, извлечение, простую арифметику, порядок памяти, отсутствие выдуманных данных и игнорирование вложенной инструкции. Диагностика новостей не имеет «правильного человеческого мнения»; оцениваются различия при контролируемой смене входа.')
    p(s,f"После найденной ошибки выполнена дополнительная арифметическая отладка на {len(arithmetic_calls)} запросах. Общий объём продолжения: {summary['all_followup_requests']} генераций и {summary['all_followup_tokens']} токенов. Они учитываются отдельно от первого пилота на 102 запроса.")
    p(s,'Оценка пригодности должна разделять техническую исправность, выполнение явных инструкций, устойчивость симуляции и эмпирическую достоверность поведения. Ни формат JSON, ни высокие результаты общеязыковых тестов не доказывают реалистичность социальных агентов. Поэтому решение о смене модели здесь ограничено задачей прототипирования.')
    p(s,'Практическая рекомендация для текущей лабораторной: сохранить bonsai2-27b как рабочую модель прототипа, выполнять точные вычисления кодом и продолжить проверки устойчивости. Найденная арифметическая ошибка не скрывается за процентом успешных JSON. Для сильных научных выводов потребуется сравнение со второй независимо выбранной моделью, доступа к которой в этом шлюзе пока нет.')

    s=page('1. Протокол до начала запросов')
    p(s,'План зафиксирован в protocol.json до исполнения. Всего запланировано 156 генераций: 12 задач с эталоном, 48 одношаговых агентных проб и 96 запросов для повтора четырёх полных условий. Дополнительно выполнен один GET /models без генерации; он возвращает только bonsai2-27b. Поле owned_by в совместимом API не использовалось как доказательство происхождения весов.')
    p(s,'60 диагностик перемешаны фиксированным seed 20261123, чтобы не выполнять все варианты одного вида подряд. Каждый агент в такой пробе создаётся заново, получает одно и то же исходное состояние и один раунд. Пары отличаются только заранее выбранным элементом входа. Температура и бюджет ответа сохранены из первого пилота, reasoning явно не включался.')
    table(s,['Группа','Меняемый фактор'],[
        ['control_original','Нет новости; исходный промпт'],['positive / negative original','Опрос поддерживает цифровой доступ либо печатные книги; численный знак ±0.8'],
        ['positive / negative paraphrase','Перефразировано только предложение о результате опроса'],
        ['positive / negative without_initial','Убрано поле initial_opinion; текущая opinion сохранена'],
        ['control_without_initial','Убрано то же поле без новой информации']],[.43,.57])
    p(s,'Проверка удаления initial_opinion выполнена на первом шаге, когда начальная и текущая позиция совпадают. Это тест чувствительности к дублирующему полю, а не причинное доказательство закрепления позиции на длинной истории. Для последнего нужен отдельный многошаговый эксперимент.')
    p(s,'После диагностик разрешён переход к полным повторам только при не менее 9 правильных ответов из 12 на простых задачах. Это инженерный порог остановки расходов, не стандарт качества моделей. Ошибки провайдера останавливают серию; неправильный ответ задачи учитывается как результат и не перезапрашивается. Ограничитель запросов тот же: минимум 3.2 с, один запрос одновременно, без автоматических повторов.')

    s=page('2. Задачи с проверяемым ответом')
    table(s,['Задача','Эталон','Ответ','Итог'],[
        [r['id'],str(r.get('expected_opinion',next(c['expected_opinion'] for c in protocol['plan'] if c['id']==r['id']))),str(r.get('action',{}).get('opinion','ошибка')),'Да' if r.get('passed') else 'Нет'] for r in objectives],[.49,.17,.17,.17])
    p(s,f"Правильных ответов: {summary['objective_passed']} из {len(objectives)}. Сравнение с эталоном выполнено по численному значению с допуском 0.000001, а не по убедительности объяснения. Полный текст каждого задания и сырого ответа сохранён; ответы не исправлялись автоматически.")
    p(s,'Положительный результат означает, что в этих коротких запросах модель справляется с явно заданными простыми правилами и извлечением информации. Это не широкий benchmark: всего 12 лёгких задач, по одному ответу. Не проверены сложные рассуждения, длинный контекст, мультимодальность и инструменты. Ответ «данных нет» проверялся только по числу; содержание объяснения дополнительно требует ручной оценки.')
    p(s,'Задачи с заданной формулой намеренно отделены от свободной социальной симуляции. Если модель способна посчитать среднее, но агент не усредняет мнения соседей, это само по себе не ошибка арифметики модели: в социальном сценарии усреднение не предписано. Подменять исследование принуждением к ожидаемой формуле нельзя.')

    if arithmetic:
        s=page('Арифметическая ошибка: отдельная диагностика')
        p(s,'В исходной проверке weighted_update модель ответила 0.24 на выражение 0.7*(-0.4) + 0.3*0.8, правильный ответ -0.04. Формат ответа был валиден. Это реальная ошибка вычисления, а не сбой парсера или округление. Для её разбора после основной серии добавлен отдельный исследовательский протокол с пределом 12 вызовов.')
        grouped=[]
        for mode,mirrored in dict.fromkeys((r['mode'],r.get('mirrored',False)) for r in arithmetic):
            selected=[r for r in arithmetic if r['mode']==mode and r.get('mirrored',False)==mirrored]
            grouped.append([mode,'Да' if mirrored else 'Нет',
                '; '.join(str(r.get('action',{}).get('opinion','ошибка')) for r in selected),
                str(sum(r['passed'] for r in selected))+'/'+str(len(selected))])
        table(s,['Режим','Зеркало','Ответы двух повторов','Верных'],grouped,[.35,.15,.32,.18])
        p(s,'baseline: исходный запрос и системная инструкция симуляции; stepwise_prompt: добавлена просьба отдельно проверить два произведения перед суммированием; neutral_system: системная роль заменена на нейтрального точного помощника; thinking_medium: тот же исходный запрос, но enable_thinking=true и reasoning_effort=medium. В зеркальном примере знаки слагаемых обращены, правильный ответ +0.04.')
        p(s,'В thinking_medium бюджет ответа увеличен с 300 до 2048 токенов, чтобы не обрезать завершение. Поэтому сравнение этого режима одновременно меняет reasoning и допустимый объём генерации; приписывать эффект только одному переключателю нельзя. Температура сохранена равной нулю. Содержимое скрытых рассуждений не запрашивалось для анализа: оценивается конечный численный ответ и usage.')
        p(s,'В этих конкретных запросах нейтральная системная инструкция дала правильный ответ в двух повторах, а reasoning - правильные ответы в двух исходных и двух зеркальных пробах. Простая дополнительная просьба проверить слагаемые не исправила ошибку. Это указывает на зависимость результата от режима и контекста, но не доказывает, что такие изменения устранят все вычислительные ошибки модели.')
        p(s,f'Отдельная диагностика фактически использовала {len(arithmetic_calls)} запросов и {arithmetic_tokens} токенов. Она выбрана после обнаружения ошибки и потому является отладкой конкретного случая, а не независимым benchmark качества. Её результаты нельзя использовать, чтобы задним числом заменить исходные 11/12 на другой результат.')
        p(s,'Точные арифметические правила, проверку ограничений и метрики следует выполнять в Python. Убедительное текстовое объяснение с верным JSON не гарантирует правильного числа. В свободной симуляции модель нужна для выбора и аргументов, а вычислительная инфраструктура должна оставаться проверяемой.')

    s=page('3. Противоположные новости и перефразирование')
    table(s,['Условие','Ср. позиция','Знаковый сдвиг','|Сдвиг|'],[
        [short[r['variant']],f"{r['mean_opinion']:.4f}" if r['mean_opinion'] is not None else 'н/д',f"{r['mean_signed_shift']:+.4f}" if r['mean_signed_shift'] is not None else 'н/д',f"{r['mean_abs_shift']:.4f}" if r['mean_abs_shift'] is not None else 'н/д'] for r in vrows],[.43,.19,.19,.19])
    image(s,'quality_diagnostics.png')
    p(s,'Знаковый сдвиг - среднее новой позиции минус исходная. Средний модуль сдвига не показывает направление. Все значения относятся к одному шагу и шести фиксированным профилям, поэтому сравниваются попарно по агентам. Порядок вариантов был перемешан, но независимых повторов каждой пробы пока нет.')

    s=page('4. Насколько меняется ответ при малой правке')
    table(s,['Сравнение','Ср. |разница|','Макс. |разница|','Совпали'],[
        [r['comparison'],f"{r['mean_abs_difference']:.4f}",f"{r['max_abs_difference']:.4f}",f"{r['equal_opinions']}/6"] for r in pairs],[.43,.2,.2,.17])
    p(s,'Для direction сравниваются противоположные новости: различие здесь является возможной реакцией на разные наблюдения. Для paraphrase сравнивается одна и та же пропозиция в двух формулировках. Для anchor_field удалено только дублирующее поле исходной позиции; сведения о текущей позиции остались.')
    p(s,'Нельзя автоматически объявлять все различия от перефразирования ошибками: естественный язык не даёт гарантии полной эквивалентности интерпретаций, а генерация может быть недетерминированной. Но если такие различия сопоставимы с эффектом смены новости, модель и промпт требуют проверки на устойчивость до содержательных выводов.')
    h(s,'Повтор первой ступени исходного протокола')
    for name,value in originals.items():
        p(s,f"{name}: идентичных текстов промпта {value['same_prompts']}/6; совпавших численных ответов с первым пилотом {value['equal_opinions']}/6.")
    p(s,'Проверка точного промпта позволяет отличить чувствительность к входу от различия ответов на одинаковый текст. Здесь совпадение промпта не раскрывает состояние серверного исполнения; версия весов, шаблон сервинга и внутренняя недетерминированность провайдера не контролируются экспериментатором.')

    s=page('5. Повтор четырёх полных условий')
    table(s,['Условие','Среднее раньше','Среднее повтор','Разница позиций','Траектория'],[
        [r['condition'],f"{r['old_mean']:.4f}",f"{r['new_mean']:.4f}",f"{r['final_mean_abs_difference']:.4f}",'Совпала' if r['identical_trajectory'] else 'Различается'] for r in repeats],[.23,.18,.18,.21,.20])
    if repeats:image(s,'quality_repeat.png')
    p(s,'Разница позиций - средний модуль разности финальных позиций тех же агентов в двух исполнениях. «Траектория совпала» означает точное совпадение всех сохранённых численных траекторий и метрик. Сравнение не требует совпадения текстов сообщений; для общения разные тексты сами могут менять последующие входы.')
    p(s,'Один повтор с тем же seed проверяет воспроизводимость этой конфигурации. Он не создаёт достаточную выборку для доверительных интервалов и не заменяет вариацию исходных профилей. Даже полное совпадение при temperature=0 не доказывает неизменности будущих ответов шлюза или достоверности поведения людей.')

    s=page('6. Точная повторяемость и происхождение модели')
    table(s,['Условие','Одинаковые входы','Тот же текст ответа','Та же позиция'],[
        [r['condition'],f"{r['same_input_calls']}/24",str(r['same_input_equal_response']),str(r['same_input_equal_opinion'])] for r in repeats],[.28,.24,.24,.24])
    p(s,'«Одинаковые входы» требует совпадения SHA-256 пользовательского промпта, системного сообщения и реально отправленных параметров запроса. Совпадения текста и позиции считаются только внутри таких пар. Если тексты общения разошлись, последующие промпты тоже могут разойтись; этот случай не следует называть разными ответами на один вход.')
    h(s,'Что можно узнать из публичных материалов')
    p(s,'Официальная карточка Prism ML описывает Bonsai 2 27B как низкобитную производную Qwen3.8-27B и публикует данные по задачам языка, рассуждений и инструментов. Анонс производителя приводит результаты в thinking-режиме. Эти данные относятся к опубликованной конфигурации автора и не являются проверкой нашего шлюза или социальных симуляций. Источники: [1], [2].')
    p(s,'Имя bonsai2-27b и ответ /models не подтверждают точный файл весов, вариант упаковки, ревизию или шаблон сервинга. Поэтому переносить рекламируемые проценты качества на наш endpoint нельзя. Для строгого сравнения полезно запросить у администратора шлюза model ID исходных весов, revision, формат/квантизацию и фактические параметры генерации.')
    p(s,'В разделе Generation Parameters карточка автора рекомендует temperature=0.7 для non-thinking и 1.0 для thinking с отдельными параметрами сэмплирования [1]. Наши проверки при temperature=0 выбраны для воспроизводимости и не повторяют рекомендованную конфигурацию производителя. Сравнение параметров генерации должно быть отдельным условием; менять их незаметно между опытами нельзя.')
    p(s,'[1] Prism ML, официальная карточка: https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf . [2] PrismML, анонс от 17.09.2026: https://prismml.com/news/bonsai-2-27b . Материалы просмотрены 23.11.2026. Описание производителя не использовалось вместо собственных измерений.')

    s=page('7. Решение о замене и следующие эксперименты')
    p(s,'Смену модели следует связывать с наблюдаемым дефектом: систематическими ошибками в простом извлечении, нарушением формата, неспособностью различать информацию и инструкцию либо такой нестабильностью, при которой эффект воздействия тонет в шуме. Отсутствие переходов на другую сторону и расхождение с линейным усреднением сами по себе не являются такими дефектами.')
    p(s,'Если короткие задачи пройдены и точные повторы устойчивы, модель целесообразно оставить как основную для разработки. Следующее усилие направить на дизайн: независимые прогоны на других профилях, собственную историю аргументов, обоснованный выбор интенсивности новости и разделение текстовых сообщений и численных якорей. Вторая модель полезна как проверка устойчивости результата, а не как способ добиться заранее желаемого эффекта.')
    p(s,'После завершения запросов адаптер получил явный параметр system_message. По умолчанию сохранена прежняя роль симуляции; аналитические задачи теперь могут вызывать тот же адаптер с нейтральной инструкцией. Исторические запросы не пересчитывались и их снимки кода не изменялись. Проверка нового параметра выполняется без API на подставном транспорте.')
    p(s,'Если обнаружена чувствительность к перефразированию, зафиксировать несколько заранее подготовленных вариантов новости и усреднять эффекты по формулировкам. Не выбирать после просмотра только тот промпт, который даёт нужный знак. Если удаление поля initial_opinion меняет ответы, отдельно сравнить многошаговые протоколы с историческим якорем и без него.')
    h(s,'Стоимость и сложность этого этапа')
    p(s,f"Основная проверка потратила {summary['total_tokens']} токенов: вход {summary['prompt_tokens']}, выход {summary['completion_tokens']}. С арифметической отладкой: {summary['all_followup_requests']} запросов, {summary['all_followup_tokens']} токенов. Медиана сетевого вызова основной проверки {summary['network_seconds_median']:.2f} с. Тариф неизвестен. Лимит 20 RPM задаёт минимум примерно 8.3 минуты для 156 запросов; фактические задержки сохранены по вызовам.")
    p(s,'Инженерная сложность подготовки диагностик - 3/5: требовалось менять ровно один фактор, сохранять сопоставимость промптов и не смешивать тест с эталоном со свободной симуляцией. Интерпретация - 4/5: результаты сильно зависят от того, что именно считается качеством. Реальные человеко-часы не измерялись. Перед API выполнен 21 тест; новые проверки подтверждают план, неизменность прочих полей и соответствие исходному промпту.')
    p(s,'Все новые данные находятся в artifacts/runs/quality_study_2026-11-23_v1: protocol.json, diagnostics.json, четыре повтора, analysis.json, CSV и снимок кода. Исходные пилоты сохранены без изменений. Этот отчёт можно пересобрать офлайн через scripts/build_quality_report.py; повтор API выполняется только отдельным run_quality_study.py с новым каталогом вывода.')

    pdfmetrics.registerFont(TTFont('QAArial',r'C:\Windows\Fonts\arial.ttf'))
    pdfmetrics.registerFont(TTFont('QAArialBold',r'C:\Windows\Fonts\arialbd.ttf'))
    styles={'h1':ParagraphStyle('qh1',fontName='QAArialBold',fontSize=18,leading=23,textColor=colors.HexColor('#12314b'),spaceAfter=16),
        'h2':ParagraphStyle('qh2',fontName='QAArialBold',fontSize=11.5,leading=16,textColor=colors.HexColor('#087e8b'),spaceBefore=9,spaceAfter=6),
        'p':ParagraphStyle('qp',fontName='QAArial',fontSize=10,leading=14.4,spaceAfter=9),
        'cell':ParagraphStyle('qc',fontName='QAArial',fontSize=8.8,leading=12),
        'th':ParagraphStyle('qth',fontName='QAArialBold',fontSize=8.8,leading=12,textColor=colors.white)}
    width=A4[0]-88;story=[];html=[]
    para=lambda text,style:Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
    for i,part in enumerate(pages):
        if i:story.append(PageBreak())
        html.append('<section>')
        for kind,value in part:
            if kind in ('h1','h2','p'):
                story.append(para(value,kind));html.append(f'<{kind}>{escape(value)}</{kind}>')
            elif kind=='image':
                from PIL import Image as PI
                with PI.open(figdir/value) as im:w,h_=im.size
                story.extend([Image(str(figdir/value),width=width,height=width*h_/w),Spacer(1,8)])
                html.append(f'<img src="figures/{value}" alt="Диагностика качества модели">')
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
        canvas.setFont('QAArial',8);canvas.setFillColor(colors.HexColor('#526779'))
        canvas.drawString(44,26,'Concordia | bonsai2-27b | Проверка пригодности модели | 23.11.2026')
        canvas.drawRightString(A4[0]-44,26,str(doc.page))
    pdf=reports/'model_quality_report.pdf'
    SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=42,bottomMargin=53,
        title='Проверка пригодности bonsai2-27b').build(story,onFirstPage=footer,onLaterPages=footer)
    css='body{font-family:Arial,sans-serif;background:#eaf0f4;color:#172b3b;line-height:1.55}main{max-width:940px;margin:auto}section{background:white;padding:40px 50px;margin:20px 0}h1{color:#12314b;line-height:1.3}h2{color:#087e8b}table{border-collapse:collapse;width:100%;font-size:14px;margin:18px 0}th{background:#12314b;color:white;text-align:left}td,th{padding:9px;vertical-align:top;overflow-wrap:anywhere}tr:nth-child(even){background:#f0f5f7}img{width:100%}p{overflow-wrap:anywhere}@media print{section{break-before:page}section:first-child{break-before:auto}}'
    (reports/'model_quality_report.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Оценка модели</title><style>'+css+'</style><main>'+''.join(html)+'</main></html>',encoding='utf-8')
    print(json.dumps({**summary,'pdf_pages':len(PdfReader(pdf).pages)},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
