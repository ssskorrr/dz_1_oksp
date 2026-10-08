import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

s=json.loads(Path('evidence/small.json').read_text(encoding='utf-8'))
w=json.loads(Path('evidence/work.json').read_text(encoding='utf-8'))
labels=['Услуги','Специалисты','Список записей','Карточка','Свободные слоты','Сводка','Бронирование','Отмена']
fig,ax=plt.subplots(figsize=(9,4.7))
x=list(range(8)); ax.bar([i-.18 for i in x],[r['p50'] for r in s['operations']],.36,label='300 записей');ax.bar([i+.18 for i in x],[r['p50'] for r in w['operations']],.36,label='50 000 записей')
ax.set_xticks(x,labels,rotation=25,ha='right');ax.set_ylabel('p50 HTTP, мс');ax.legend();ax.grid(axis='y',alpha=.25);fig.tight_layout();fig.savefig('evidence/times.png',dpi=180);plt.close(fig)
fig,ax=plt.subplots(figsize=(8.8,4.4)); rows=w['operations'];ax.barh(labels,[r['db_ms'] for r in rows],label='Обращения к БД');ax.barh(labels,[r['server_ms']-r['db_ms'] for r in rows],left=[r['db_ms'] for r in rows],label='Остальное время сервера');ax.set_xlabel('Среднее время, мс');ax.legend();fig.tight_layout();fig.savefig('evidence/breakdown.png',dpi=180)
