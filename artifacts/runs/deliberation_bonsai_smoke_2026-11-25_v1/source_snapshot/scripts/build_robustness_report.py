"""Offline report for profile sensitivity and memory-by-anchor experiments."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'artifacts/setup/matplotlib-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pypdf import PdfReader
from src.study_analysis import analyze_study
from report_utils import render_report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default='artifacts/runs/robustness_study_2026-11-23_v1')
    args=parser.parse_args();out=Path(args.input)
    summary,runs,factorial=analyze_study(out,ROOT)
    if summary['status']!='ok' or len(runs)!=15 or len(factorial)!=4:
        raise SystemExit('Analysis saved; complete planned cells before building final report')
    reports=ROOT/'reports';figdir=reports/'figures';figdir.mkdir(exist_ok=True)
    labels={'control':'Контроль','news_only':'Новости','peers_only':'Общение','combined':'Новости + общение'}
    factor_labels={'m1_anchor':'Окно 1, якорь','m4_anchor':'Окно 4, якорь',
        'm1_no_anchor':'Окно 1, без якоря','m4_no_anchor':'Окно 4, без якоря'}
    colors=['#728195','#ba7d31','#607bb0','#087e8b']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(10,3.6))
    for name,color in zip(('news_only','peers_only','combined'),colors[1:]):
        rows=[r for r in summary['paired_profile_contrasts'] if r['condition']==name]
        axes[0].plot([r['seed'] for r in rows],[r['mean_minus_control'] for r in rows],marker='o',label=labels[name],color=color)
        axes[1].plot([r['seed'] for r in rows],[r['variance_minus_control'] for r in rows],marker='o',label=labels[name],color=color)
    for ax,title in zip(axes,['Средняя позиция: опыт минус контроль','Дисперсия: опыт минус контроль']):
        ax.set_title(title,fontsize=10);ax.set_xlabel('Seed профилей');ax.set_xticks((11,22,33));ax.axhline(0,color='#888',lw=.8);ax.grid(alpha=.2)
    axes[1].legend(fontsize=8);fig.tight_layout();fig.savefig(figdir/'robustness_profile_contrasts.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(10,3.4),sharey=True)
    for ax,seed in zip(axes,(11,22,33)):
        for name,color in zip(('control','news_only','peers_only','combined'),colors):
            r=runs[f'{name}_{seed}'];ax.plot(range(5),[t['mean_opinion'] for t in r['trajectory']],marker='o',markersize=3,color=color,label=labels[name])
        ax.set_title(f'Seed {seed}');ax.set_xlabel('Раунд');ax.set_xticks(range(5));ax.grid(alpha=.2)
    axes[0].set_ylabel('Средняя позиция');axes[-1].legend(fontsize=7);fig.tight_layout()
    fig.savefig(figdir/'robustness_profile_trajectories.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,3.5))
    for (key,r),color in zip(factorial.items(),colors):
        for ax,metric in zip(axes,['mean_opinion','variance']):
            ax.plot(range(5),[t[metric] for t in r['trajectory']],marker='o',markersize=3,label=factor_labels[key],color=color)
            ax.set_xlabel('Раунд');ax.set_xticks(range(5));ax.grid(alpha=.2)
    axes[0].set_title('Средняя позиция');axes[1].set_title('Дисперсия');axes[1].legend(fontsize=8)
    fig.tight_layout();fig.savefig(figdir/'robustness_memory_anchor.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(10,5.7),sharex=True,sharey=True)
    for ax,(key,r) in zip(axes.ravel(),factorial.items()):
        for i in range(6):
            ax.plot(range(5),[t['opinions'][i] for t in r['trajectory']],marker='o',markersize=3,label=f'Агент {i}')
        ax.set(title=factor_labels[key],ylim=(-1,1),xticks=range(5));ax.grid(alpha=.2)
    axes[0,0].legend(ncol=3,fontsize=7);fig.supxlabel('Раунд');fig.supylabel('Заявленная позиция');fig.tight_layout()
    fig.savefig(figdir/'robustness_memory_individual.png',dpi=180);plt.close(fig)
    pages=[]
    def page(title):s=[('h1',title)];pages.append(s);return s
    def p(s,text):s.append(('p',text))
    def h(s,text):s.append(('h2',text))
    def table(s,headers,rows,widths):s.append(('table',(headers,rows,widths)))
    def image(s,name):s.append(('image',name))
    def code(s,text):s.append(('code',text))
    s=page('Устойчивость предпочтений: профили, память и исходная позиция')
    p(s,'Третья содержательная серия с реальной LLM для первой идеи лабораторной. Concordia 2.4.0, bonsai2-27b, 23 ноября 2026 года. Проверяется переносимость первых наблюдений на другие численные профили, влияние окна памяти и постоянного напоминания исходной позиции.')
    table(s,['Показатель','Результат'],[
        ['Новые симуляции',f"{summary['new_runs']}; по 6 агентов и 4 раунда"],
        ['Новые запросы / успешные ответы',f"{summary['new_requests']} / {summary['successful_responses']}"],
        ['Исторические базовые условия','4 запуска seed=11 использованы повторно, без новых обращений к API'],
        ['Основные условия','4 условия × 3 набора профилей; 8 из 12 запусков новые'],
        ['Память × исходное поле','4 ячейки: окна 1/4 × поле есть/нет; seed=11'],
        ['Новые токены',str(summary['new_total_tokens'])],
        ['Время серии',f"{summary['wall_seconds']:.1f} с"],['HTTP-ошибки',str(summary['http_errors'])]],[.43,.57])
    p(s,'Первый пилот показал небольшое изменение позиций без смены исходных сторон. Проверка качества затем точно воспроизвела все четыре траектории, но выявила чувствительность к формулировке и дублирующему полю initial_opinion. Поэтому текущая серия меняет факторы по отдельности и заранее фиксирует сравнения, не подбирая промпт под желаемый результат.')
    p(s,'Это исследование чувствительности минимального стенда. Три набора параметров не представляют население, а четыре раунда не моделируют долгосрочную эволюцию сообщества. Результаты относятся к одной модели, одному предметному примеру и сохранённым формулировкам.')

    s=page('1. План серии и сопоставимость условий')
    p(s,'План сохранён до запросов в protocol.json. Для seed=22 и seed=33 выполнены control, news_only, peers_only и combined. Профили внутри каждого seed идентичны между условиями. Величина исходной позиции получает случайное отклонение до 0.05, доверие к источнику меняется в диапазоне [0.35,0.90]. Роли и их порядок фиксированы, исходно три агента отрицательны и три положительны.')
    p(s,'Для seed=11 добавлены combined_memory4, combined_no_initial и combined_memory4_no_initial. Четвёртая ячейка, combined с окном 1 и полем исходной позиции, взята из первого пилота. Её полное повторение с теми же параметрами ранее дало одинаковые тексты и траектории, поэтому повторно расходовать 24 запроса на неё не стали.')
    table(s,['Фактор','Уровни и постоянные параметры'],[
        ['Источник','Один вымышленный опрос в пользу цифрового доступа, значение +0.8, только в раунде 1'],
        ['Общение','Кольцо, два соседа; текст и численная позиция предыдущего раунда'],
        ['Память','В промпт извлекаются наблюдения последних 1 либо 4 раундов'],
        ['Исходная позиция','Собственное поле initial_opinion оставлено либо удалено из контекста'],
        ['Не менялись','Роли, текущая opinion, схема JSON, модель, temperature=0 и лимит ответа 300 токенов'],
        ['Порядок','11 новых запусков перемешаны фиксированным seed=2303']],[.28,.72])
    p(s,'Новые профили означают изменения численных параметров, а не новые биографии или другую структуру сообщества. При удалении initial_opinion текущая позиция остаётся в промпте. Начальные позиции соседей могут сохраняться как старые внешние сообщения при длинном окне. Поэтому это не удаление всей информации об исходном состоянии общества.')
    p(s,'Слово «якорь» в подписях таблиц означает только наличие поля initial_opinion. Оно не обозначает установленный психологический механизм. Аналогично «память» здесь - окно извлечения наблюдений, а не оценка способности модели помнить собственный жизненный опыт.')
    p(s,'Одна модель вызывается последовательно, с общим ограничителем 20 RPM и предварительным токенным резервированием. Автоматические повторы отсутствуют. Каждый ответ валидируется; частичный журнал сохраняется после каждого действия. Статистические тесты значимости для этой небольшой серии не планировались.')

    s=page('2. Базовые условия на трёх наборах профилей')
    table(s,['Seed','Условие','Ср. позиция','Дисперсия','|Сдвиг|'],[
        [str(seed),labels[name],f"{runs[f'{name}_{seed}']['final_metrics']['mean_opinion']:.4f}",
            f"{runs[f'{name}_{seed}']['final_metrics']['variance']:.4f}",f"{runs[f'{name}_{seed}']['final_metrics']['mean_abs_shift']:.4f}"]
        for seed in (11,22,33) for name in ('control','news_only','peers_only','combined')],[.10,.32,.20,.19,.19])
    image(s,'robustness_profile_trajectories.png')
    p(s,'Итоги четвёртого раунда. Seed=11 - исторический пилот; 22 и 33 - новые запуски. Сдвиг считается относительно собственной исходной позиции каждого агента. Для вывода о влиянии условий далее используются парные разности с контролем того же seed, а не разности между несопоставимыми наборами профилей.')

    s=page('3. Насколько эффекты переносятся между профилями')
    table(s,['Условие','Δ среднего: среднее [min; max]','Δ дисперсии: среднее [min; max]'],[
        [labels[r['condition']],f"{r['mean_minus_control']['mean']:+.4f} [{r['mean_minus_control']['min']:+.4f}; {r['mean_minus_control']['max']:+.4f}]",
            f"{r['variance_minus_control']['mean']:+.4f} [{r['variance_minus_control']['min']:+.4f}; {r['variance_minus_control']['max']:+.4f}]"]
        for r in summary['aggregated_profile_contrasts']],[.26,.37,.37])
    image(s,'robustness_profile_contrasts.png')
    p(s,'Δ означает итог опытного условия минус итог контроля с теми же профилями. Положительное Δ среднего означает относительный сдвиг к цифровому доступу. Положительное Δ дисперсии означает больший разброс заявленных позиций. Интервалы в таблице - минимум и максимум трёх наблюдений, не доверительные интервалы.')
    for row in summary['aggregated_profile_contrasts']:
        a=row['mean_minus_control']['values'];b=row['variance_minus_control']['values']
        p(s,f"{labels[row['condition']]}: Δ среднего положительно в {sum(x>0 for x in a)}/3 наборах, отрицательно в {sum(x<0 for x in a)}/3; Δ дисперсии положительно в {sum(x>0 for x in b)}/3, отрицательно в {sum(x<0 for x in b)}/3.")
    p(s,'Знак, совпавший в трёх близких наборах профилей, является результатом этого скрининга. Он не устанавливает универсальный эффект и не отделяет влияние фиксированных ролей от других механизмов. Три seed нельзя считать тремя независимыми человеческими сообществами, а шесть взаимодействующих агентов - независимыми повторениями.')

    # Remaining pages are appended below; generation is always offline.
    add_factorial_pages(pages,summary,runs,factorial,labels,factor_labels)
    render_report(pages,reports,'robustness_report','Профили, память и исходная позиция',
                  'Concordia | bonsai2-27b | Профили и память | 23.11.2026')
    print(json.dumps({**summary,'pdf_pages':len(PdfReader(reports/'robustness_report.pdf').pages)},ensure_ascii=False,indent=2))


def add_factorial_pages(pages,summary,runs,factorial,labels,factor_labels):
    def page(title):s=[('h1',title)];pages.append(s);return s
    def p(s,text):s.append(('p',text))
    def h(s,text):s.append(('h2',text))
    def table(s,headers,rows,widths):s.append(('table',(headers,rows,widths)))
    def image(s,name):s.append(('image',name))
    def code(s,text):s.append(('code',text))
    s=page('4. Память и напоминание исходной позиции')
    table(s,['Ячейка','Ср. позиция','Дисперсия','|Сдвиг|'],[
        [factor_labels[key],f"{r['final_metrics']['mean_opinion']:.4f}",f"{r['final_metrics']['variance']:.4f}",f"{r['final_metrics']['mean_abs_shift']:.4f}"]
        for key,r in factorial.items()],[.43,.19,.19,.19])
    image(s,'robustness_memory_anchor.png')
    p(s,'Все ячейки используют combined и профили seed=11. Окно меняет доступную внешнюю историю, а переключатель исходной позиции меняет только одно собственное поле. Текущая позиция всегда передаётся. Сравнение включает тексты, которые агенты сгенерировали в соответствующей ветви, поэтому различия могут накапливаться через взаимодействия.')
    p(s,f"Средний модуль сдвига при увеличении окна: с полем {factorial['m1_anchor']['final_metrics']['mean_abs_shift']:.4f} → {factorial['m4_anchor']['final_metrics']['mean_abs_shift']:.4f}, без поля {factorial['m1_no_anchor']['final_metrics']['mean_abs_shift']:.4f} → {factorial['m4_no_anchor']['final_metrics']['mean_abs_shift']:.4f}. Поэтому в этом прогоне эффект окна зависит от способа предъявления собственного состояния.")
    metric_labels={'mean_opinion':'Средняя позиция','variance':'Дисперсия','mean_abs_shift':'|Сдвиг|'}
    table(s,['Показатель','Память при якоре','Память без якоря','Убрать якорь, H1','Убрать якорь, H4','Взаимодействие'],[
        [metric_labels[metric]]+[f"{summary['factorial_contrasts'][metric][key]:+.4f}" for key in
            ('memory_effect_anchor','memory_effect_no_anchor','remove_anchor_memory1','remove_anchor_memory4','interaction')]
        for metric in metric_labels],[.20,.16,.16,.16,.16,.16])
    p(s,'Эффект памяти: окно 4 минус окно 1 при фиксированном состоянии поля. Эффект удаления: без поля минус с полем при фиксированном окне. Взаимодействие: разность двух эффектов памяти. Это контрасты одного набора профилей, без оценки случайной ошибки и без переноса на людей.')

    s=page('5. Индивидуальные траектории и пределы памяти')
    image(s,'robustness_memory_individual.png')
    p(s,'На рисунке показаны все шесть агентов в четырёх ячейках. Усреднённый результат не заменяет индивидуальные траектории: одинаковое среднее может скрывать разнонаправленные изменения. Прямые смены исходной стороны и размер изменений сохранены в таблицах и исходных JSON.')
    table(s,['Агент','Исходно','H1, якорь','H4, якорь','H1, без поля','H4, без поля'],[
        [str(i),f"{factorial['m1_anchor']['profiles'][i]['initial_opinion']:.3f}"]+
        [f"{factorial[key]['final_metrics']['opinions'][i]:.3f}" for key in ('m1_anchor','m4_anchor','m1_no_anchor','m4_no_anchor')]
        for i in range(6)],[.10,.16,.185,.185,.185,.185])
    changed=summary['factorial_changed_agents']
    p(s,'Относительно базовой ячейки изменились финальные позиции: '+
        '; '.join(f"{factor_labels[key]}: "+(', '.join(f"агент {a['agent']} ({a['role']}), Δ={a['difference']:+.3f}" for a in values) if values else 'нет различий')
            for key,values in changed.items() if key!='m1_anchor')+'.')
    p(s,'Длинное окно содержит старые новости и сообщения соседей. Собственная предыдущая аргументация в память автоматически не записывается; переносится собственная численная позиция. Поэтому опыт не доказывает эффект полноценной автобиографической памяти агента. Возврат старого текста соседей также может усиливать повторное присутствие одного аргумента, а не только полезное запоминание.')

    add_resource_pages(pages,summary,runs,factorial,factor_labels)


def add_resource_pages(pages,summary,runs,factorial,factor_labels):
    def page(title):s=[('h1',title)];pages.append(s);return s
    def p(s,text):s.append(('p',text))
    def h(s,text):s.append(('h2',text))
    def table(s,headers,rows,widths):s.append(('table',(headers,rows,widths)))
    def code(s,text):s.append(('code',text))
    s=page('6. Контекст, задержки и стоимость проведения')
    table(s,['Ячейка','Наблюдений в последнем промпте','Символов в последнем промпте','Входных токенов за запуск'],[
        [factor_labels[key],str(exposure_count(r)),
            f"{statistics.mean(len(c['prompt']) for c in r['calls'][-6:]):.0f}",
            str(sum(c['usage']['prompt_tokens'] for c in r['calls']))] for key,r in factorial.items()],[.31,.23,.23,.23])
    p(s,'В таблице среднее по шести последним вызовам; число входных токенов - сумма за все четыре раунда. Ячейка «окно 1, якорь» историческая: её токены приведены только для сравнения и не включены в расход новой серии. Окно памяти ограничивает извлечение событий, но не удаляет историю из ListMemory.')
    table(s,['Новая группа запусков','Запросы','Входные токены','Выходные токены'],resource_groups(summary),[.4,.16,.22,.22])
    p(s,f"Новая серия: {summary['new_requests']} запросов и {summary['new_total_tokens']} токенов. Из них вход {summary['new_prompt_tokens']}, выход {summary['new_completion_tokens']}. Общая длительность {summary['wall_seconds']:.1f} с; медиана сетевого вызова {summary['network_seconds_median']:.2f} с, 95-й перцентиль {summary['network_seconds_p95']:.2f} с. Суммарное ожидание ограничителя {summary['rate_wait_seconds']:.1f} с.")
    p(s,'Наблюдаемая длительность включает ожидание разрешённой частоты, обработку ответа и сохранение checkpoint. При длинном контексте консервативное резервирование токенов может дополнительно ограничивать частоту. Фактический расход взят из usage; резерв и реальные токены не складываются. Денежная стоимость не вычислялась, поскольку тариф шлюза не предоставлен.')
    p(s,'В памяти одного агента за четыре раунда сохраняются tick-события, доставленные новости и сообщения. В длинном окне снова предъявляются тексты, которые уже встречались ранее. Это увеличивает затраты и может менять поведение через повторное присутствие источника. Для будущей библиотеки нужны раздельные политики хранения, извлечения и ограничения токенного бюджета.')

    s=page('7. Реализация, сложности и ограничения вывода')
    table(s,['Решение / этап','Сложность','Что зафиксировано'],[
        ['Переключатель исходной позиции','2/5','Config.include_initial_opinion; по умолчанию прежнее поведение, удаляется только поле в промпте'],
        ['Совместимость состояний','3/5','Новый флаг сохраняется в checkpoint; старое состояние без него восстанавливается с включённым полем'],
        ['Сопоставимость промптов','3/5','Тест подтвердил точное совпадение обычного промпта второго раунда с историческим пилотом'],
        ['Серия и ограничитель','2/5','План, порядок, код, промежуточные ответы и версии сохранены; автоматических повторов нет'],
        ['Парный анализ','3/5','Каждое условие сравнивается с контролем того же seed; исторические запросы не включаются в новый расход'],
        ['Содержательные выводы','4/5','Три близких набора параметров; факторный опыт памяти только на одном из них']],[.31,.15,.54])
    p(s,'Шкала 1-5 является инженерной оценкой: 1 - штатный шаг, 3 - требовалась специальная проверка, 5 - отдельная исследовательская задача. Человеко-часы не измерялись. Перед API успешно прошли 27 тестов, включая пять новых: бюджет плана, сопоставимость входа, удаление одного поля и восстановление нового/старого состояния.')
    h(s,'Границы интерпретации')
    p(s,'Варьируются только численные характеристики, тогда как роли и их порядок, распределение исходных сторон и предметный пример фиксированы. Один и тот же библиотекарь всегда находится примерно в одной части шкалы. Поэтому влияние роли нельзя отделить от позиции, а найденные эффекты нельзя переносить на произвольные сообщества.')
    p(s,'Общение передаёт одновременно текст и явную численную самооценку соседей. Собственная история аргументов не возвращается. Сеть фиксирована; контакты и уход участников не моделируются. Длинная память может усиливать повторение сообщений. Прекращение изменения позиции за четыре раунда не означает достижения устойчивого равновесия.')
    p(s,'Ранее точные повторные запросы совпадали, но это не устраняет возможную смену серверной сборки или модели в будущем. Текущая серия фиксирует имя модели и ответы, а не хеш весов провайдера. Нет сравнения с другой LLM и с реальными людьми. Эмпирическая валидация исходной социальной гипотезы остаётся отдельным этапом.')

    s=page('8. Что переносить в библиотеку и делать дальше')
    p(s,'Экспериментальные параметры должны быть частью явной конфигурации: окно памяти, видимость полей профиля, выбор наблюдений и режим генерации. Значения по умолчанию нужно сохранять для старых опытов, а любое изменение контекста - отражать в метаданных. Иначе разницу поведения легко ошибочно приписать модели или социальному механизму.')
    p(s,'Нужен единый анализ парных условий: исходные состояния, траектории, вклад отдельных агентов и контрольный дрейф. В этой серии добавлены summary.csv, paired_contrasts.csv и individual_contrasts.csv. Сводные средние не должны скрывать, что эффект мог быть создан одним агентом с фиксированной ролью.')
    h(s,'Следующий исследовательский шаг')
    p(s,'Наиболее полезно отделить роль от исходной позиции: переставить роли между позициями и повторить заранее выбранные условия. Затем сравнить общение с явными численными позициями и только текстом. Для памяти добавить хранение собственной аргументации отдельным фактором. Формулировки новости и параметры генерации менять заранее заданными вариантами, а не исправлять после просмотра результата.')
    p(s,'Если эффекты изменились между seed, расширять наборы профилей и выяснять, какие индивидуальные изменения создают общий результат. Если эффекты памяти и исходного поля взаимодействуют, сначала проверить этот результат на других профилях, а уже затем строить объяснение механизма. Вторую LLM следует использовать для проверки зависимости выводов от модели при наличии доступа.')
    h(s,'Как повторить и проверить')
    code(s,'.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v\n# Только анализ сохранённых данных, без API:\n.\\.venv\\Scripts\\python.exe scripts/build_robustness_report.py\n# Новая такая же серия, до 264 запросов:\n.\\.venv\\Scripts\\python.exe scripts/run_robustness_study.py --output artifacts/runs/robustness_repeat_02')
    p(s,'Исходные данные: artifacts/runs/robustness_study_2026-11-23_v1. Протокол, снимок кода, все промпты и ответы, usage и checkpoints сохранены рядом. Отчёт: reports/robustness_report.pdf и HTML-версия. Предыдущие три отчёта и все исходные результаты сохранены отдельно.')
    p(s,'Численные утверждения и графики этого отчёта получены из локальных журналов. Новые внешние источники или свойства провайдера не использовались для объяснения результатов. Итог серии - измеренная чувствительность нашего прототипа, а не подтверждённая модель формирования мнений людей.')


def exposure_count(result):
    from src.models import BEGIN,END
    counts=[]
    for call in result['calls'][-6:]:
        data=json.loads(call['prompt'].split(BEGIN,1)[1].split(END,1)[0])
        counts.append(len(data['exposures']))
    return int(statistics.mean(counts))


def resource_groups(summary):
    rows=[]
    for label,predicate in [('Новые профили, seed 22/33',lambda r:r['seed'] in (22,33)),
        ('Память 4, seed 11',lambda r:r['seed']==11 and r['memory_rounds']==4),
        ('Окно 1 без поля, seed 11',lambda r:r['seed']==11 and r['memory_rounds']==1)]:
        selected=[r for r in summary['conditions'] if r['origin']=='new' and predicate(r)]
        rows.append([label,str(sum(r['requests'] for r in selected)),str(sum(r['prompt_tokens'] for r in selected)),str(sum(r['completion_tokens'] for r in selected))])
    return rows


if __name__=='__main__':main()
