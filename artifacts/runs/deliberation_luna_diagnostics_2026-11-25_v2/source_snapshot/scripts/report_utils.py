"""Shared static report rendering; no API calls and no experiment mutations."""
from html import escape
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image


def render_report(pages,reports,stem,title,footer_text):
    reports=Path(reports);reports.mkdir(exist_ok=True)
    pdfmetrics.registerFont(TTFont('StudyArial',r'C:\Windows\Fonts\arial.ttf'))
    pdfmetrics.registerFont(TTFont('StudyArialBold',r'C:\Windows\Fonts\arialbd.ttf'))
    styles={'h1':ParagraphStyle('sh1',fontName='StudyArialBold',fontSize=18,leading=23,textColor=colors.HexColor('#12314b'),spaceAfter=16),
        'h2':ParagraphStyle('sh2',fontName='StudyArialBold',fontSize=11.5,leading=16,textColor=colors.HexColor('#087e8b'),spaceBefore=9,spaceAfter=6),
        'p':ParagraphStyle('sp',fontName='StudyArial',fontSize=10,leading=14.4,spaceAfter=9),
        'cell':ParagraphStyle('sc',fontName='StudyArial',fontSize=8.8,leading=12),
        'th':ParagraphStyle('sth',fontName='StudyArialBold',fontSize=8.8,leading=12,textColor=colors.white),
        'code':ParagraphStyle('scode',fontName='StudyArial',fontSize=8.3,leading=12,backColor=colors.HexColor('#eef3f7'),borderPadding=8,spaceAfter=12)}
    width=A4[0]-88;story=[];html=[]
    para=lambda text,style:Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
    for i,part in enumerate(pages):
        if i:story.append(PageBreak())
        html.append('<section>')
        for kind,value in part:
            if kind in ('h1','h2','p','code'):
                story.append(para(value,kind));tag='pre' if kind=='code' else kind
                html.append(f'<{tag}>{escape(str(value))}</{tag}>')
            elif kind=='image':
                from PIL import Image as PI
                with PI.open(reports/'figures'/value) as im:w,h=im.size
                story.extend([Image(str(reports/'figures'/value),width=width,height=width*h/w),Spacer(1,8)])
                html.append(f'<img src="figures/{value}" alt="Результаты эксперимента">')
            elif kind=='table':
                headers,values,widths=value
                contents=[[para(x,'th') for x in headers]]+[[para(x,'cell') for x in row] for row in values]
                t=Table(contents,colWidths=[width*w for w in widths],repeatRows=1)
                t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#12314b')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f0f5f7'),colors.white]),
                    ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
                story.extend([t,Spacer(1,11)])
                html.append('<table><tr>'+''.join('<th>'+escape(str(x))+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in values)+'</table>')
        html.append('</section>')
    def footer(canvas,doc):
        canvas.setFont('StudyArial',8);canvas.setFillColor(colors.HexColor('#526779'))
        canvas.drawString(44,26,footer_text);canvas.drawRightString(A4[0]-44,26,str(doc.page))
    SimpleDocTemplate(str(reports/(stem+'.pdf')),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=42,bottomMargin=53,
        title=title).build(story,onFirstPage=footer,onLaterPages=footer)
    css='body{font-family:Arial,sans-serif;background:#eaf0f4;color:#172b3b;line-height:1.55}main{max-width:940px;margin:auto}section{background:white;padding:40px 50px;margin:20px 0}h1{color:#12314b;line-height:1.3}h2{color:#087e8b}table{border-collapse:collapse;width:100%;font-size:14px;margin:18px 0}th{background:#12314b;color:white;text-align:left}td,th{padding:9px;vertical-align:top;overflow-wrap:anywhere}tr:nth-child(even){background:#f0f5f7}img{width:100%}p{overflow-wrap:anywhere}pre{background:#eef3f7;padding:14px;white-space:pre-wrap;overflow-wrap:anywhere}@media print{section{break-before:page}section:first-child{break-before:auto}}'
    (reports/(stem+'.html')).write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>'+escape(title)+'</title><style>'+css+'</style><main>'+''.join(html)+'</main></html>',encoding='utf-8')
