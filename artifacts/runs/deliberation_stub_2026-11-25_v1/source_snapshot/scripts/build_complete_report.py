"""Create a current overview and merge the four preserved stage reports."""
import json
from pathlib import Path
import sys
from pypdf import PdfReader,PdfWriter

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from report_utils import render_report


def main():
    reports=ROOT/'reports'
    read=lambda p:json.loads((ROOT/p).read_text(encoding='utf-8'))
    pilot=read('artifacts/runs/live_pilot_2026-11-23_v1/analysis.json')
    quality=read('artifacts/runs/quality_study_2026-11-23_v1/analysis.json')
    robust=read('artifacts/runs/robustness_study_2026-11-23_v1/analysis.json')
    if robust['status']!='ok':raise SystemExit('Finish the current study before creating an overview')
    calls=pilot['request_count']+quality['all_followup_requests']+robust['new_requests']
    tokens=pilot['total_tokens']+quality['all_followup_tokens']+robust['new_total_tokens']
    sections=[('Этап 1. Прототип и численный контроль','experiment_report.pdf'),
        ('Этап 2. Первый реальный LLM-пилот','live_pilot_report.pdf'),
        ('Этап 3. Проверка пригодности модели','model_quality_report.pdf'),
        ('Этап 4. Профили, память и исходное поле','robustness_report.pdf')]
    pages=[]
    first=[('h1','Коллективные предпочтения LLM-агентов: сводный отчёт'),
        ('p','Лабораторный прототип первой идеи. Период работы: 21-23 ноября 2026 года. Текущая сводка составлена 23.11.2026. Фреймворк Concordia 2.4.0; реальные генерации выполнены моделью bonsai2-27b через предоставленный шлюз.'),
        ('table',(['Что проверено','Подтверждённый объём'],[
            ['Численный этап','40 основных запусков и две длинные пробы памяти'],
            ['Внешняя LLM',f'{calls} генераций; {tokens} токенов по usage'],
            ['Готовность кода','27 автоматических тестов перед последней серией'],
            ['Повторяемость','Четыре полные траектории и 96 ответов повторились точно'],
            ['Чувствительность','Три набора численных профилей и факторный опыт окна памяти / исходного поля']],[.37,.63])),
        ('h2','Текущий вывод'),
        ('p','Минимальный прототип реализуем: агенты Concordia получают адресные наблюдения, используют историю, возвращают действия и сохраняют состояния. Модель пригодна для разработки стенда, но реалистичность социальных агентов не установлена. В короткой проверке явных правил было 11 правильных ответов из 12; вычислительная ошибка зависела от системной роли и исправлялась в проверенных нейтральных/reasoning-пробах. Точную арифметику и метрики выполняет код.'),
        ('p','Первоначальные социальные наблюдения оказались чувствительны к профилям. Парные результаты по трём наборам не дают основания считать направление эффектов универсальным. Это существенное уточнение первого пилота: воспроизводимость одной конфигурации не означает устойчивости вывода при изменении условий.'),
        ('p','Окно наблюдений и предъявление собственной исходной позиции взаимодействуют. На seed=11 длинная память без поля initial_opinion снизила разброс позиций сильнее, чем каждое изменение по отдельности. Это результат одного факторного опыта, который нужно повторять на других профилях.'),
        ('p','Документ объединяет четыре подробных отчёта. Ранние разделы являются историческими протоколами этапов: например, отсутствие LLM на первом этапе не описывает текущее состояние проекта. Актуальный итог и ограничения приведены в этой сводке и последнем этапе.')]
    pages.append(first)
    lengths={filename:len(PdfReader(reports/filename).pages) for _,filename in sections}
    starts=[];page_number=3
    for title,filename in sections:
        starts.append([title,str(page_number),str(lengths[filename])]);page_number+=lengths[filename]
    second=[('h1','Навигация, воспроизводимость и следующие шаги'),
        ('table',(['Раздел','Начало','Страниц'],starts,[.66,.17,.17])),
        ('p','Номера начала относятся к страницам этого объединённого PDF, а номера в нижних колонтитулах подробных этапов остаются локальными для каждого исходного отчёта. Для навигации в PDF добавлены закладки разделов.'),
        ('h2','Как устроен исследовательский стенд'),
        ('p','Используются настоящие EntityAgent, ObservationToMemory, ListMemory, ConcatActComponent и интерфейс LanguageModel. Сеть, расписание раундов, доставка событий и метрики реализованы в проекте. В основной серии шесть агентов, четыре раунда, кольцо связей, вымышленный выбор цифрового доступа или печатных книг. Собственная численная позиция, наблюдения и история взаимодействий логируются явно.'),
        ('p','Сохранены конфигурации, профили, графы, точные промпты и ответы, параметры запросов, usage, задержки, checkpoints и снимки кода. Каждый этап лежит в отдельной папке artifacts/runs. Исторические baseline-запуски не включаются повторно в число новых запросов. Локальный .env не входит в отчёты или Git.'),
        ('h2','Что ещё требуется для научных выводов'),
        ('p','Отделить роль агента от исходной позиции перестановкой ролей; проверить несколько заранее выбранных формулировок; сравнить текстовое общение с передачей численных позиций; добавить собственную историю аргументов отдельным фактором. Затем проверить ключевые эффекты на другой LLM и сопоставить с эмпирическими данными. Текущие три seed меняют только численные характеристики при фиксированных ролях и не представляют человеческое население.'),
        ('h2','Где находятся материалы'),
        ('p','Репозиторий: C:/Users/shuma/PycharmProjects/ЛабыПитон/llm-opinion-dynamics. README.md содержит актуальные команды запуска и карту файлов. reports/ содержит отдельные PDF/HTML этапов; artifacts/runs/ - исходные данные и сравнительные CSV. scripts/build_*_report.py строят отчёты офлайн, run_* запускают новые API-запросы с ограничением бюджета.'),
        ('p','Сложность реализации, ошибок установки, ограничителя запросов и экспериментального дизайна оценена отдельно в каждом этапе. Человеко-часы не измерялись; денежная стоимость неизвестна без тарифа шлюза. Токены и реальные длительности фиксируются по журналам.')]
    pages.append(second)
    render_report(pages,reports,'complete_overview','Сводка лабораторных экспериментов',
        'Коллективные предпочтения | Сводка | 23.11.2026')
    overview=PdfReader(reports/'complete_overview.pdf')
    if len(overview.pages)!=2:raise ValueError('Overview layout changed; update navigation before merging')
    writer=PdfWriter();writer.append(reports/'complete_overview.pdf',outline_item='Актуальная сводка и навигация')
    for title,filename in sections:writer.append(reports/filename,outline_item=title)
    writer.add_metadata({'/Title':'Коллективные предпочтения LLM-агентов: все эксперименты','/Subject':'Concordia, bonsai2-27b, 21-23.11.2026'})
    output=reports/'complete_lab_report.pdf'
    with output.open('wb') as f:writer.write(f)
    merged=PdfReader(output);expected=list(overview.pages)
    for _,filename in sections:expected.extend(PdfReader(reports/filename).pages)
    if len(merged.pages)!=len(expected):raise AssertionError('Missing pages after merge')
    for actual,reference in zip(merged.pages,expected):
        if actual.extract_text()!=reference.extract_text():raise AssertionError('Page text changed during merge')
    print(json.dumps({'pages':len(merged.pages),'live_requests':calls,'live_tokens':tokens,'sections':starts,'all_page_text_preserved':True},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
