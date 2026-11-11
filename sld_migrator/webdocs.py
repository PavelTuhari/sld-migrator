# -*- coding: utf-8 -*-
"""Встроенные HTML-страницы SLD Migrator: карта бизнес-процесса и документация.

Страницы отдаёт встроенный веб-сервер утилиты (http://127.0.0.1:<порт>/process и /doc).
Состояние шагов берётся с /api/state каждые 2 секунды; при экспорте в файл
(python sld_migrator.py --export-html) снимок состояния вшивается вместо /*EMBED*/null.
"""

CSS = r"""
:root{--bg:#f4f6fa;--card:#fff;--ink:#0f172a;--mut:#64748b;--line:#dbe1ea;--blue:#1d4ed8;--green:#15803d;
--teal:#0f766e;--red:#b91c1c;--amber:#b45309;--gray:#94a3b8}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 "Segoe UI",Arial,sans-serif;background:var(--bg);color:var(--ink)}
header{background:#0f172a;color:#fff;padding:14px 24px;position:sticky;top:0;z-index:20}
header h1{margin:0;font-size:19px}
header .sub{color:#cbd5e1;font-size:13px;margin-top:2px}
header a{color:#93c5fd;margin-left:14px;font-size:13px}
.badges{margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.b{padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600;background:#334155;color:#fff;white-space:nowrap}
.b.dry{background:var(--teal)}.b.real{background:var(--red)}.b.ok{background:var(--green)}.b.off{background:#64748b}.b.warn{background:var(--amber)}
main{max-width:1500px;margin:0 auto;padding:18px 24px 60px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin-bottom:18px}
h2{margin:0 0 4px;font-size:17px}h3{font-size:15px;margin:16px 0 6px}
.lead{color:var(--mut);margin:0 0 12px}
.bar{height:10px;background:#e2e8f0;border-radius:99px;overflow:hidden}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,#15803d,#22c55e);transition:width .5s}
.here{font-size:15px;font-weight:600;margin:10px 0 2px}
.lane{border-left:5px solid #94a3b8;padding:8px 0 8px 14px;margin:14px 0}
.lane.E0{border-color:#64748b}.lane.E1{border-color:#0ea5e9}.lane.E2{border-color:#7c3aed}.lane.E3{border-color:#16a34a}.lane.RB{border-color:#dc2626}
.lane h3{margin:0}.lane .sub{color:var(--mut);font-size:13px;margin-bottom:8px}
.flow{display:flex;flex-wrap:wrap;gap:10px 0;align-items:stretch}
.arrow{align-self:center;color:#94a3b8;font-size:18px;padding:0 4px;user-select:none}
.step{width:205px;border:2px solid var(--line);border-radius:9px;padding:8px 10px;background:#fff;cursor:pointer;position:relative;
display:flex;flex-direction:column;gap:3px;transition:box-shadow .15s}
.step:hover{box-shadow:0 3px 12px rgba(15,23,42,.18)}
.step .id{font-weight:700;font-size:12px;color:var(--mut);display:flex;justify-content:space-between;gap:6px}
.step .t{font-weight:600;font-size:13px;line-height:1.3}
.step .m{font-size:11.5px;color:var(--mut)}
.k{font-size:10.5px;font-weight:700;padding:0 6px;border-radius:4px;text-transform:uppercase;letter-spacing:.3px}
.k.manual{background:#e2e8f0;color:#334155}.k.check{background:#dbeafe;color:#1e40af}.k.change{background:#fee2e2;color:#991b1b}.k.long{background:#7c3aed;color:#fff}
.chip{font-size:11.5px;font-weight:700;margin-top:auto}
.step.pending{background:#f8fafc}.step.pending .chip{color:var(--gray)}
.step.done{border-color:#22c55e;background:#f0fdf4}.step.done .chip{color:var(--green)}
.step.dry{border-color:#14b8a6;border-style:dashed;background:#f0fdfa}.step.dry .chip{color:var(--teal)}
.step.skipped{border-color:#f59e0b;background:#fffbeb}.step.skipped .chip{color:var(--amber)}
.step.failed{border-color:#ef4444;background:#fef2f2}.step.failed .chip{color:var(--red)}
.step.running{border-color:#3b82f6;background:#eff6ff;animation:pulse 1.2s infinite}.step.running .chip{color:var(--blue)}
.step.current{box-shadow:0 0 0 4px #fde047;border-color:#ca8a04}
.step.current::before{content:"ВЫ ЗДЕСЬ";position:absolute;top:-11px;left:10px;background:#ca8a04;color:#fff;font-size:10px;font-weight:700;padding:1px 7px;border-radius:4px}
.step.sel{outline:3px solid #0f172a}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(59,130,246,.6)}100%{box-shadow:0 0 0 12px rgba(59,130,246,0)}}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:var(--mut);margin-top:8px}
.legend i{display:inline-block;width:14px;height:14px;border-radius:4px;border:2px solid;vertical-align:-3px;margin-right:4px}
#detail{position:fixed;right:0;top:0;bottom:0;width:560px;max-width:100%;background:#fff;border-left:1px solid var(--line);
box-shadow:-8px 0 30px rgba(15,23,42,.2);z-index:30;padding:18px 20px;overflow:auto;transform:translateX(105%);transition:transform .2s}
#detail.open{transform:none}
#detail .x{position:absolute;right:14px;top:10px;font-size:22px;cursor:pointer;color:var(--mut)}
pre{background:#0f172a;color:#e2e8f0;padding:10px 12px;border-radius:8px;overflow:auto;font:12px/1.45 Consolas,monospace;white-space:pre}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
th{background:#f1f5f9}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:1000px){.grid2{grid-template-columns:1fr}}
.kv{display:grid;grid-template-columns:auto 1fr;gap:2px 14px;font-size:13px}
.kv b{color:var(--mut);font-weight:600}
.pb{height:14px;background:#e2e8f0;border-radius:4px;overflow:hidden;min-width:140px}
.pb>i{display:block;height:100%;background:#3b82f6}
.st-ok{color:var(--green);font-weight:700}.st-warn{color:var(--amber);font-weight:700}.st-fail{color:var(--red);font-weight:700}.st-info{color:var(--mut)}
.note{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:8px 12px;margin:10px 0}
.danger{background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:8px 12px;margin:10px 0}
.okbox{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:8px 12px;margin:10px 0}
nav.toc{columns:2;font-size:13.5px}nav.toc a{display:block;color:var(--blue);text-decoration:none;padding:1px 0}
code{background:#eef2f7;padding:1px 5px;border-radius:4px;font:12.5px Consolas,monospace}
img.shot{max-width:100%;border:1px solid var(--line);border-radius:8px;margin:6px 0 2px;box-shadow:0 2px 10px rgba(15,23,42,.12)}
figure{margin:14px 0}figcaption{font-size:12.5px;color:var(--mut)}
svg text{font-family:"Segoe UI",Arial,sans-serif}
"""

JS_COMMON = r"""
var EMBED = /*EMBED*/null;
var STATE = EMBED, LIVE = false;
var ST_RU = {pending:'ожидает',running:'выполняется',done:'выполнен',dry:'сухой прогон',failed:'ошибка',skipped:'отмечен вручную'};
var ST_IC = {pending:'○',running:'▶',done:'✔',dry:'◐',failed:'✖',skipped:'➜'};
var KIND_RU = {manual:'ручной',check:'проверка',change:'изменение',long:'длительное'};
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function load(cb){
  fetch('/api/state',{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){STATE=j;LIVE=true;cb()})
  .catch(function(){LIVE=false;if(STATE)cb()});
}
function badges(){
  var a=STATE.app,h='';
  h+='<span class="b '+(LIVE?'ok':'off')+'">'+(LIVE?'● утилита запущена, данные живые':'○ статичный снимок от '+esc(a.now))+'</span>';
  h+='<span class="b">профиль '+esc(a.profile)+(a.prod?' — PROD':' — тест')+'</span>';
  h+='<span class="b '+(a.connected?'ok':'off')+'">'+(a.connected?'подключено: '+esc(a.host):'не подключено')+'</span>';
  h+='<span class="b '+(a.dry?'dry':'real')+'">'+(a.dry?'сухой прогон':'БОЕВОЙ РЕЖИМ')+'</span>';
  return h;
}
"""

PROCESS_HTML = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Карта процесса — SLD Migrator</title><style>""" + CSS + r"""</style></head><body>
<header>
  <h1>Blocarea vinzarilor in minus — карта процесса миграции TEST → PROD
    <a href="/doc">Документация →</a></h1>
  <div class="sub">UNA.md back-office, схема MARKET</div>
  <div class="badges" id="badges"></div>
</header>
<main>

<section>
  <h2>Где мы сейчас</h2>
  <div class="here" id="here"></div>
  <div class="bar"><i id="pbar" style="width:0"></i></div>
  <div class="legend">
    <span><i style="border-color:#dbe1ea;background:#f8fafc"></i>ожидает</span>
    <span><i style="border-color:#3b82f6;background:#eff6ff"></i>выполняется</span>
    <span><i style="border-color:#22c55e;background:#f0fdf4"></i>выполнен</span>
    <span><i style="border-color:#14b8a6;border-style:dashed;background:#f0fdfa"></i>сухой прогон (база не менялась)</span>
    <span><i style="border-color:#f59e0b;background:#fffbeb"></i>отмечен вручную</span>
    <span><i style="border-color:#ef4444;background:#fef2f2"></i>ошибка</span>
    <span><i style="border-color:#ca8a04;box-shadow:0 0 0 3px #fde047"></i>текущий шаг</span>
  </div>
</section>

<section>
  <h2>1. Какую бизнес-задачу решает миграция</h2>
  <p class="lead">Касса не должна продавать товар, которого нет на остатке. Для этого остаток нужно узнавать за миллисекунды, а не считать по 2,2 млрд проводок.</p>
  <svg viewBox="0 0 1400 430" width="100%" role="img" aria-label="Схема: было и стало">
    <defs><marker id="ar" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9z" fill="#64748b"/></marker>
    <marker id="arg" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9z" fill="#15803d"/></marker>
    <marker id="arr" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9z" fill="#b91c1c"/></marker></defs>
    <rect x="0" y="0" width="1400" height="195" rx="10" fill="#fef2f2" stroke="#fecaca"/>
    <text x="16" y="24" font-size="14" font-weight="700" fill="#991b1b">БЫЛО (PROD сегодня): актуального сальдо нет</text>
    <g font-size="12.5" fill="#0f172a">
      <rect x="20" y="60" width="170" height="80" rx="8" fill="#fff" stroke="#94a3b8"/><text x="105" y="90" text-anchor="middle" font-weight="700">Касса (front-office)</text><text x="105" y="110" text-anchor="middle">продажа товара</text><text x="105" y="126" text-anchor="middle" fill="#64748b">чек</text>
      <rect x="250" y="60" width="190" height="80" rx="8" fill="#fff" stroke="#94a3b8"/><text x="345" y="90" text-anchor="middle" font-weight="700">Документ UNA.md</text><text x="345" y="110" text-anchor="middle">продажа / приход /</text><text x="345" y="126" text-anchor="middle">перемещение</text>
      <rect x="500" y="60" width="210" height="80" rx="8" fill="#fff" stroke="#94a3b8"/><text x="605" y="86" text-anchor="middle" font-weight="700">Проводки TMDB_CM</text><text x="605" y="106" text-anchor="middle">2,22 млрд строк</text><text x="605" y="124" text-anchor="middle" fill="#64748b">триггер TMDB_CM_TSLD_TR выключен</text>
      <rect x="770" y="60" width="250" height="80" rx="8" fill="#fff" stroke="#ef4444" stroke-dasharray="6 4"/><text x="895" y="86" text-anchor="middle" font-weight="700">Остаток = сумма проводок</text><text x="895" y="106" text-anchor="middle">считается минутами</text><text x="895" y="124" text-anchor="middle" fill="#64748b">TXSLD пустая, job 8 сломан с 2017</text>
      <rect x="1080" y="60" width="300" height="80" rx="8" fill="#fff" stroke="#ef4444"/><text x="1230" y="86" text-anchor="middle" font-weight="700" fill="#b91c1c">Касса не может спросить остаток</text><text x="1230" y="106" text-anchor="middle">товар продаётся «в минус»,</text><text x="1230" y="124" text-anchor="middle">отрицательные остатки, пересортица</text>
    </g>
    <g stroke="#64748b" stroke-width="2" marker-end="url(#ar)"><line x1="190" y1="100" x2="246" y2="100"/><line x1="440" y1="100" x2="496" y2="100"/><line x1="710" y1="100" x2="766" y2="100"/></g>
    <line x1="1020" y1="100" x2="1076" y2="100" stroke="#b91c1c" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#arr)"/>
    <text x="700" y="172" text-anchor="middle" font-size="12.5" fill="#991b1b">Итог: блокировку продаж в минус включить нельзя — нет быстрого и достоверного остатка</text>

    <rect x="0" y="215" width="1400" height="215" rx="10" fill="#f0fdf4" stroke="#bbf7d0"/>
    <text x="16" y="239" font-size="14" font-weight="700" fill="#166534">СТАНЕТ (после миграции): остаток поддерживается онлайн</text>
    <g font-size="12.5" fill="#0f172a">
      <rect x="20" y="265" width="170" height="80" rx="8" fill="#fff" stroke="#94a3b8"/><text x="105" y="295" text-anchor="middle" font-weight="700">Касса (front-office)</text><text x="105" y="315" text-anchor="middle">продажа товара</text><text x="105" y="331" text-anchor="middle" fill="#64748b">чек</text>
      <rect x="250" y="265" width="190" height="80" rx="8" fill="#fff" stroke="#94a3b8"/><text x="345" y="295" text-anchor="middle" font-weight="700">Документ UNA.md</text><text x="345" y="315" text-anchor="middle">продажа / приход /</text><text x="345" y="331" text-anchor="middle">перемещение</text>
      <rect x="500" y="265" width="210" height="80" rx="8" fill="#fff" stroke="#94a3b8"/><text x="605" y="291" text-anchor="middle" font-weight="700">Проводки TMDB_CM</text><text x="605" y="311" text-anchor="middle">каждая вставка / правка</text><text x="605" y="329" text-anchor="middle" fill="#15803d" font-weight="700">триггер TMDB_CM_TSLD_TR включён</text>
      <rect x="770" y="265" width="250" height="80" rx="8" fill="#fff" stroke="#22c55e" stroke-width="2"/><text x="895" y="291" text-anchor="middle" font-weight="700">TXSLD / TSLD</text><text x="895" y="311" text-anchor="middle">актуальное сальдо по счёту,</text><text x="895" y="329" text-anchor="middle">аналитике, подразделению</text>
      <rect x="1080" y="265" width="300" height="80" rx="8" fill="#fff" stroke="#22c55e" stroke-width="2"/><text x="1230" y="291" text-anchor="middle" font-weight="700" fill="#166534">Касса спрашивает остаток мгновенно</text><text x="1230" y="311" text-anchor="middle">остатка не хватает →</text><text x="1230" y="329" text-anchor="middle" font-weight="700">продажа блокируется</text>
      <rect x="770" y="372" width="250" height="44" rx="8" fill="#fff" stroke="#94a3b8"/><text x="895" y="391" text-anchor="middle" font-weight="700">Job 8, ежедневно 06:00</text><text x="895" y="407" text-anchor="middle" fill="#64748b">partial_compact_sld — сжатие по счетам</text>
      <rect x="250" y="372" width="460" height="44" rx="8" fill="#fff" stroke="#7c3aed"/><text x="480" y="391" text-anchor="middle" font-weight="700" fill="#5b21b6">Разовый полный пересчёт в окне (шаг W8, ≈4 часа)</text><text x="480" y="407" text-anchor="middle" fill="#64748b">заполняет TXSLD/TSLD из 2,22 млрд проводок</text>
    </g>
    <g stroke="#15803d" stroke-width="2" marker-end="url(#arg)"><line x1="190" y1="305" x2="246" y2="305"/><line x1="440" y1="305" x2="496" y2="305"/><line x1="710" y1="305" x2="766" y2="305"/><line x1="1020" y1="305" x2="1076" y2="305"/><line x1="895" y1="372" x2="895" y2="349"/><line x1="710" y1="394" x2="766" y2="340"/></g>
  </svg>
  <div class="grid2" style="margin-top:10px">
    <div><h3>Что переносится с TEST на PROD</h3>
      <table><tr><th>Объект</th><th>Изменение</th><th>Шаг</th></tr>
      <tr><td>PKG_SLD_UTIL (спецификация, тело)</td><td>v1.03: <code>partial_compact_sld</code>, <code>safe_truncate</code> стал функцией, параметр <code>sld_allow_rebuild_wo_truncate</code></td><td>P3, P4</td></tr>
      <tr><td>XSLD_COMPACT_STATS + индекс</td><td>новая таблица статистики сжатия</td><td>P2</td></tr>
      <tr><td>TSLD_CONT_DEP</td><td>новый индекс (cont, dep)</td><td>P2</td></tr>
      <tr><td>TMDB_CM_TSLD_TR</td><td>DISABLED → ENABLED</td><td>W10</td></tr>
      <tr><td>DBMS_JOB 8, 13</td><td>8 → partial_compact_sld 06:00; 13 удалить</td><td>W11</td></tr>
      <tr><td>TXSLD, TSLD</td><td>полный пересчёт</td><td>W8</td></tr></table></div>
    <div><h3>Что НЕ переносится</h3>
      <div class="danger">Около 45 других PL/SQL-объектов на TEST и PROD различаются, и на PROD они <b>новее</b>. Синхронизировать схему целиком нельзя — утилита меняет только объекты из таблицы слева.</div>
      <h3>Кто участвует</h3>
      <div class="kv"><b>Разработчик</b><span>выполняет шаги в утилите</span>
      <b>Админ БД</b><span>сервер, место, запуск пересчёта на сервере</span>
      <b>Тестировщик</b><span>front-office, тесты, связь с клиентом</span>
      <b>Менеджер проекта</b><span>согласование окна с клиентом</span>
      <b>Клиент</b><span>согласие, бэкап, пользователи, смена паролей</span></div></div>
  </div>
</section>

<section>
  <h2>2. Окно работ по часам</h2>
  <p class="lead">Старт 21:00, конец ≈02:00, запас до утренней нагрузки 4 часа. Красные отметки — точки решения об откате.</p>
  <div id="timeline"></div>
</section>

<section>
  <h2>3. Пошаговый процесс</h2>
  <p class="lead">Щёлкните по шагу — справа откроются описание, риск, точный SQL и ожидаемый результат. Статусы обновляются сами, пока утилита запущена.</p>
  <div id="lanes"></div>
</section>

<section>
  <h2>4. Что происходит прямо сейчас</h2>
  <div class="grid2">
    <div><h3>Процессы утилиты</h3><div id="procs"></div>
         <h3>Длительные операции в базе</h3><div id="longops"></div></div>
    <div><h3>Состояние базы (монитор)</h3><div id="mon"></div>
         <h3>Последние проверки</h3><div id="chk"></div></div>
  </div>
</section>
</main>
<aside id="detail"><span class="x" onclick="closeD()">×</span><div id="dbody"></div></aside>

<script>""" + JS_COMMON + r"""
var SEL=null;
function render(){
  var a=STATE.app, steps=STATE.steps;
  document.getElementById('badges').innerHTML=badges();
  var main=steps.filter(function(s){return s.phase!='RB'}), done=main.filter(function(s){return ['done','dry','skipped'].indexOf(s.status)>=0}).length;
  document.getElementById('pbar').style.width=(100*done/main.length)+'%';
  var cur=steps.filter(function(s){return s.id==STATE.current})[0];
  var run=steps.filter(function(s){return s.status=='running'})[0];
  document.getElementById('here').innerHTML='Пройдено '+done+' из '+main.length+' шагов. '+
    (run?'Сейчас выполняется: <b>'+esc(run.id+'. '+run.title)+'</b>':(cur?'Следующий шаг: <b>'+esc(cur.id+'. '+cur.title)+'</b> — '+esc(cur.who)+', '+esc(cur.when):'<b>Все шаги пройдены.</b>'));
  var h='';
  STATE.phases.forEach(function(p){
    var ss=steps.filter(function(s){return s.phase==p.id});
    var d=ss.filter(function(s){return ['done','dry','skipped'].indexOf(s.status)>=0}).length;
    h+='<div class="lane '+p.id+'"><h3>'+esc(p.title)+' <span style="font-weight:400;color:#64748b;font-size:13px">— '+d+' / '+ss.length+'</span></h3><div class="sub">'+esc(p.sub)+'</div><div class="flow">';
    ss.forEach(function(s,i){
      if(i)h+='<span class="arrow">→</span>';
      h+='<div class="step '+s.status+(s.id==STATE.current?' current':'')+(s.id==SEL?' sel':'')+'" onclick="openD(\''+s.id+'\')">'+
         '<div class="id"><span>'+esc(s.id)+'</span><span class="k '+s.kind+'">'+KIND_RU[s.kind]+'</span></div>'+
         '<div class="t">'+esc(s.title)+'</div><div class="m">'+esc(s.who)+'</div><div class="m">⏱ '+esc(s.when)+' • '+esc(s.dur)+'</div>'+
         '<div class="chip">'+ST_IC[s.status]+' '+ST_RU[s.status]+(s.at?' • '+esc(s.at.slice(11,16)):'')+'</div></div>';
    });
    h+='</div></div>';
  });
  document.getElementById('lanes').innerHTML=h;
  // процессы
  var pr=STATE.procs||[];
  document.getElementById('procs').innerHTML=pr.length?'<table><tr><th>#</th><th>Процесс</th><th>Тип</th><th>Статус</th><th>Длится</th></tr>'+
    pr.slice().reverse().slice(0,8).map(function(p){return '<tr><td>'+p.id+'</td><td>'+esc(p.title)+'</td><td>'+esc(p.kind)+'</td><td class="st-'+({ok:'ok',fail:'fail',running:'info',killed:'warn'}[p.status])+'">'+
      ({ok:'✔ готово',fail:'✖ ошибка',running:'▶ идёт',killed:'■ остановлен'}[p.status])+'</td><td>'+Math.floor(p.elapsed/60)+':'+('0'+p.elapsed%60).slice(-2)+'</td></tr>'}).join('')+'</table>'
    :'<p class="lead">Процессов ещё не было.</p>';
  var m=STATE.monitor||{}, s=m.state||{};
  document.getElementById('mon').innerHTML=m.at?'<div class="kv"><b>Опрос</b><span>'+esc(m.at)+' ('+m.took+' с)</span>'+
    '<b>Время сервера</b><span>'+esc(s.TIME)+'</span><b>Блокировка проводок</b><span>'+esc(s.RESTRICT)+'</span>'+
    '<b>Онлайн-сальдо (TSLD_TR)</b><span>'+esc(s.TSLD_TR)+'</span><b>job_queue_processes</b><span>'+esc(s.JQP)+'</span>'+
    '<b>Идёт заданий</b><span>'+esc(s.RUNJOBS)+'</span><b>Блокировок на TMDB_CM</b><span>'+esc(s.CMLOCKS)+'</span>'+
    '<b>TXSLD / TSLD</b><span>'+esc(s.TXSLD_MB)+' / '+esc(s.TSLD_MB)+' МБ</span><b>Свободно TBSUN4_TABLES</b><span>'+esc(s.FREE_MB)+' МБ</span>'+
    '<b>Сессий утилиты в базе</b><span>'+(m.sessions||[]).length+'</span></div>':'<p class="lead">Монитор ещё не опрашивал базу.</p>';
  var lo=m.longops||[];
  document.getElementById('longops').innerHTML=lo.length?'<table><tr><th>SID</th><th>Операция</th><th>Объект</th><th>Ход</th><th>Осталось, с</th></tr>'+
    lo.map(function(r){var pc=Math.round(100*r[3]/Math.max(r[4],1));return '<tr><td>'+esc(r[0])+'</td><td>'+esc(r[1])+'</td><td>'+esc(r[2])+'</td><td><div class="pb"><i style="width:'+pc+'%"></i></div>'+pc+'%</td><td>'+esc(r[6])+'</td></tr>'}).join('')+'</table>'
    :'<p class="lead">Длительных операций сейчас нет.</p>';
  var ch=STATE.checks||[];
  if(ch.length){var c={ok:0,warn:0,fail:0,info:0};ch.forEach(function(r){c[r.status]++});
    document.getElementById('chk').innerHTML='<p>Стадия «'+esc(STATE.checks_stage)+'»: <span class="st-ok">✔ '+c.ok+'</span> &nbsp; <span class="st-warn">! '+c.warn+'</span> &nbsp; <span class="st-fail">✖ '+c.fail+'</span> &nbsp; <span class="st-info">· '+c.info+' инфо</span></p>'+
      '<table><tr><th>№</th><th>Проверка</th><th>Значение</th><th>Итог</th></tr>'+ch.filter(function(r){return r.status!='info'&&r.status!='ok'}).concat(ch.filter(function(r){return r.status=='ok'}).slice(0,6)).map(function(r){
        return '<tr><td>'+r.id+'</td><td>'+esc(r.title)+'<br><span class="st-info">'+esc(r.msg)+'</span></td><td>'+esc(r.value)+'</td><td class="st-'+r.status+'">'+r.status.toUpperCase()+'</td></tr>'}).join('')+'</table>';
  } else document.getElementById('chk').innerHTML='<p class="lead">Проверки ещё не запускались.</p>';
  timeline();
  if(SEL)fillD();
}
function openD(id){SEL=id;fillD();document.getElementById('detail').classList.add('open');render()}
function closeD(){SEL=null;document.getElementById('detail').classList.remove('open');render()}
function fillD(){
  var s=STATE.steps.filter(function(x){return x.id==SEL})[0];if(!s)return;
  var exp=Object.keys(s.expect||{}).map(function(k){return '<code>'+esc(k)+' = '+esc(s.expect[k])+'</code>'}).join(' ');
  document.getElementById('dbody').innerHTML='<h2>'+esc(s.id+'. '+s.title)+'</h2>'+
   '<p><span class="k '+s.kind+'">'+KIND_RU[s.kind]+'</span> &nbsp; <b class="st-'+({done:'ok',failed:'fail',dry:'info',skipped:'warn',running:'info',pending:'info'}[s.status])+'">'+ST_IC[s.status]+' '+ST_RU[s.status]+'</b>'+(s.at?' — '+esc(s.at):'')+'</p>'+
   (s.note?'<div class="note">'+esc(s.note)+'</div>':'')+
   '<div class="kv"><b>Кто</b><span>'+esc(s.who)+'</span><b>Когда</b><span>'+esc(s.when)+'</span><b>Длительность</b><span>'+esc(s.dur)+'</span>'+
   (s.script?'<b>Скрипт-источник</b><span><code>scripts/'+esc(s.script)+'</code></span>':'')+'</div>'+
   '<h3>Что делает</h3><p>'+esc(s.desc)+'</p>'+
   (s.risk&&s.risk!='—'?'<h3>Риск</h3><div class="danger">'+esc(s.risk)+'</div>':'')+
   (s.sql?'<h3>SQL, меняющий базу</h3><pre>'+esc(s.sql)+'</pre>':'')+
   (s.info_sql?'<h3>Контрольный запрос (только чтение)</h3><pre>'+esc(s.info_sql)+'</pre>':'')+
   (exp?'<h3>Шаг считается выполненным, если</h3><p>'+exp+'</p>':'')+
   (s.kind=='manual'?'<div class="note">Ручной шаг: выполняется людьми, в утилите только отмечается с комментарием.</div>':'');
}
function timeline(){
  var W=1400,H=190,x0=40,x1=1380,t0=20,t1=31; // 20:00 .. 07:00 (+24)
  function X(h){return x0+(x1-x0)*(h-t0)/(t1-t0)}
  var seg=[[21,21.33,'#f59e0b','W1–W7 стоп заданий, блокировка'],[21.33,24.5,'#7c3aed','W8 пересчёт TXSLD ≈3 ч 05 мин'],[24.5,25.5,'#a855f7','W8 TSLD ≈55 мин'],
           [25.5,26,'#22c55e','W9–W16 включение, проверки'],[26,30,'#e2e8f0','запас до утренней нагрузки']];
  var h='<svg viewBox="0 0 '+W+' '+H+'" width="100%">';
  for(var t=t0;t<=t1;t++){h+='<line x1="'+X(t)+'" y1="50" x2="'+X(t)+'" y2="118" stroke="#e2e8f0"/><text x="'+X(t)+'" y="136" font-size="12" text-anchor="middle" fill="#64748b">'+('0'+(t%24)).slice(-2)+':00</text>'}
  seg.forEach(function(s){h+='<rect x="'+X(s[0])+'" y="62" width="'+(X(s[1])-X(s[0]))+'" height="44" fill="'+s[2]+'" rx="5"/>'});
  h+='<text x="'+X(21.02)+'" y="54" font-size="11.5" fill="#b45309">стоп заданий, блокировка</text>'+
     '<text x="'+X(22.9)+'" y="89" font-size="13" fill="#fff" text-anchor="middle" font-weight="700">W8: пересчёт TXSLD ≈ 3 ч 05 мин</text>'+
     '<text x="'+X(25)+'" y="89" font-size="12" fill="#fff" text-anchor="middle" font-weight="700">TSLD ≈ 55 мин</text>'+
     '<text x="'+X(25.75)+'" y="54" font-size="11.5" fill="#15803d" text-anchor="middle">включение, сверка</text>'+
     '<text x="'+X(28)+'" y="89" font-size="12.5" fill="#475569" text-anchor="middle">запас до утренней нагрузки</text>';
  [[27.5,'03:30 — TXSLD не досчитан → откат',32],[29,'05:00 — крайний срок отката',15]].forEach(function(d){
    h+='<line x1="'+X(d[0])+'" y1="'+(d[2]+6)+'" x2="'+X(d[0])+'" y2="118" stroke="#dc2626" stroke-width="2.5" stroke-dasharray="5 3"/><text x="'+X(d[0])+'" y="'+d[2]+'" font-size="11.5" fill="#b91c1c" text-anchor="middle" font-weight="700">'+d[1]+'</text>'});
  h+='<line x1="'+X(30)+'" y1="50" x2="'+X(30)+'" y2="118" stroke="#0f172a" stroke-width="2"/><text x="'+X(30)+'" y="158" font-size="11.5" text-anchor="middle" fill="#0f172a" font-weight="700">06:00 job 8, начало рабочего дня</text>';
  [[22,'22:00–23:30 вечерние задания сдвигаются за окно (E0.7)']].forEach(function(d){h+='<text x="'+X(d[0])+'" y="158" font-size="11.5" fill="#64748b">'+d[1]+'</text>'});
  var n=new Date(), hh=n.getHours()+n.getMinutes()/60; if(hh<8)hh+=24;
  if(LIVE&&hh>=t0&&hh<=t1){h+='<line x1="'+X(hh)+'" y1="44" x2="'+X(hh)+'" y2="124" stroke="#1d4ed8" stroke-width="3"/><circle cx="'+X(hh)+'" cy="44" r="5" fill="#1d4ed8"/><text x="'+X(hh)+'" y="178" font-size="12" fill="#1d4ed8" text-anchor="middle" font-weight="700">сейчас '+('0'+n.getHours()).slice(-2)+':'+('0'+n.getMinutes()).slice(-2)+'</text>'}
  document.getElementById('timeline').innerHTML=h+'</svg>';
}
load(function(){var m=/[?&]open=([\w.]+)/.exec(location.search);if(m){SEL=m[1];document.getElementById('detail').classList.add('open')}render()});
setInterval(function(){load(render)},2000);
</script></body></html>
"""

DOC_HTML = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Документация — SLD Migrator</title><style>""" + CSS + r"""
main{max-width:1100px} section p,section li{max-width:900px}</style></head><body>
<header>
  <h1>SLD Migrator — документация <a href="/process">Карта процесса →</a></h1>
  <div class="sub">Утилита переноса «Blocarea vinzarilor in minus» с тестовой базы на продуктивную. UNA.md back-office, схема MARKET.</div>
  <div class="badges" id="badges"></div>
</header>
<main>
<section><h2>Содержание</h2><nav class="toc">
<a href="#s1">1. Что это и зачем</a><a href="#s2">2. Что нужно для запуска</a><a href="#s3">3. Запуск и подключение</a>
<a href="#s4">4. Окно утилиты</a><a href="#s5">5. Режимы и защита PROD</a><a href="#s6">6. Порядок работ по шагам</a>
<a href="#s7">7. Проверки</a><a href="#s8">8. Мониторинг процессов</a><a href="#s9">9. Откат</a>
<a href="#s10">10. Как утилита проверялась на TEST</a><a href="#s11">11. Файлы, журналы, настройки</a>
<a href="#s12">12. Типичные ошибки</a><a href="#s13">13. Безопасность</a></nav></section>

<section id="s1"><h2>1. Что это и зачем</h2>
<p>Чтобы кассы могли блокировать продажу товара «в минус», back-office должен мгновенно отдавать актуальный остаток. Остаток хранится в таблицах <code>TXSLD</code> и <code>TSLD</code>; их заполняет триггер <code>TMDB_CM_TSLD_TR</code> при каждой проводке. На тестовой базе это настроено и проверено, на PROD — нет: триггер выключен, <code>TXSLD</code> пустая.</p>
<p>Утилита проводит перенос по шагам: ставит новый <code>PKG_SLD_UTIL</code> и три объекта, закрывает проводки, пересчитывает сальдо по 2,22 млрд проводок, включает онлайн-запись, перенастраивает задания и сверяет результат. На каждом шаге она показывает точный SQL, проверяет результат и не даёт перепрыгнуть через шаг.</p>
<div class="note">Утилита заменяет ручной запуск скриптов <code>00</code>–<code>08</code> и <code>99</code> из папки <code>scripts</code>. Порядок действий тот же, который проверен вручную на тестовой базе.</div></section>

<section id="s2"><h2>2. Что нужно для запуска</h2>
<table><tr><th>Что</th><th>Требование</th></tr>
<tr><td>Python</td><td>3.8 или новее для Windows. Дополнительные пакеты не нужны: окно построено на tkinter из стандартной поставки.</td></tr>
<tr><td>Oracle sqlplus</td><td>Любой клиент 11g–19c. Путь задаётся в <code>sld_migrator.ini</code>, параметр <code>sqlplus</code>.</td></tr>
<tr><td>Сеть</td><td>Доступ к базе по адресу из профиля .</td></tr>
<tr><td>Учётная запись</td><td><code>MARKET</code>. Нужны привилегии ALTER SYSTEM, SELECT ANY DICTIONARY, CREATE JOB — проверка D4.</td></tr>
<tr><td>Файлы</td><td>Папка <code>sld_migrator</code> должна лежать рядом с папками <code>scripts</code> и <code>backup_prod</code>.</td></tr></table></section>

<section id="s3"><h2>3. Запуск и подключение</h2>
<ol>
<li>Запустите <code>run.bat</code> (или <code>python sld_migrator.py</code> из папки <code>sld_migrator</code>).</li>
<li>Выберите профиль: <b>TEST</b> или <b>PROD</b>.</li>
<li>Нажмите «Подключиться» и введите пароль MARKET. Пароль хранится только в памяти до закрытия окна, в файлы и журналы не пишется.</li>
<li>Утилита проверит, что сервер базы совпадает с <code>expected_host</code> профиля. Если нет — подключение отклоняется: это защита от запуска «не на той базе».</li>
<li>После подключения метка станет зелёной (TEST) или красной (PROD), а монитор начнёт опрашивать базу.</li>
</ol>
<figure><img class="shot" src="/screenshots/01_start.png" alt="" onerror="this.parentNode.style.display='none'"><figcaption>Окно после запуска: слева шаги, справа описание выбранного шага.</figcaption></figure>
<figure><img class="shot" src="/screenshots/02_connected.png" alt="" onerror="this.parentNode.style.display='none'"><figcaption>Подключение к TEST выполнено.</figcaption></figure></section>

<section id="s4"><h2>4. Окно утилиты</h2>
<table><tr><th>Область</th><th>Что показывает</th></tr>
<tr><td>Верхняя строка</td><td>Профиль, подключение, флажок «Сухой прогон», флажок «Эксперт», кнопки «Документация» и «Карта процесса».</td></tr>
<tr><td>Цветная полоса</td><td>Текущий режим: зелёная — сухой прогон, оранжевая — боевой на TEST, красная — боевой на PROD.</td></tr>
<tr><td>Дерево шагов (слева)</td><td>Все шаги по этапам со статусом. Текущий шаг подсвечен жёлтым с пометкой «вы здесь».</td></tr>
<tr><td>Вкладка «Шаг»</td><td>Описание, исполнитель, время, риск, точный SQL и результат последнего запуска.</td></tr>
<tr><td>Вкладка «Проверки»</td><td>Набор проверок с итогом OK / ВНИМ. / СТОП.</td></tr>
<tr><td>Вкладка «Процессы»</td><td>Всё, что утилита запускала: PID, время, статус, вывод на лету, кнопка остановки.</td></tr>
<tr><td>Вкладка «Монитор БД»</td><td>Состояние базы, сессии утилиты, длительные операции, журнал пересчёта.</td></tr>
<tr><td>Вкладка «Журнал»</td><td>Хронология всех действий в утилите.</td></tr></table>
<p>Статусы шагов: ○ ожидает, ▶ выполняется, ✔ выполнен, ◐ сухой прогон, ➜ отмечен вручную, ✖ ошибка.</p></section>

<section id="s5"><h2>5. Режимы и защита PROD</h2>
<h3>Сухой прогон (включён по умолчанию)</h3>
<p>Шаги-проверки выполняются по-настоящему: они только читают. Шаги-изменения <b>не выполняются</b>: утилита показывает SQL, который был бы запущен, и выполняет только контрольный запрос. Шаг получает статус «сухой прогон». Вместо пересчёта (W8) идёт 40-секундная имитация, чтобы проверить мониторинг.</p>
<h3>Боевой режим</h3>
<p>Снимите флажок «Сухой прогон». На TEST нужно подтвердить вопрос, на PROD — ввести слово <code>PROD</code>. Затем каждый изменяющий шаг спрашивает подтверждение отдельно (на PROD — снова словом <code>PROD</code>).</p>
<h3>Защиты</h3>
<ul>
<li>Проверка сервера выполняется в самой базе перед каждым запуском. При несовпадении сеанс завершается до первого оператора шага.</li>
<li>Шаги идут строго по порядку. Обойти порядок можно только флажком «Эксперт».</li>
<li>Изменяющие шаги выполняются с <code>whenever sqlerror exit rollback</code>: первая ошибка останавливает шаг.</li>
<li>Установка пакета сначала сравнивает код в базе с файлом. Если совпадает, ничего не выполняется.</li>
<li>Установка пакета требует копии текущего кода (шаг P1) — иначе откатывать было бы нечем.</li>
<li>При смене профиля утилита возвращается в сухой прогон и требует нового подключения.</li>
</ul>
<div class="danger"><b>PROD меняется только при письменном согласии клиента и в назначенное окно.</b> До этого на PROD допустим только сухой прогон: он ничего не меняет.</div></section>

<section id="s6"><h2>6. Порядок работ по шагам</h2>
<p>Таблица строится из того же каталога, что и окно утилиты. Полная схема с SQL — на <a href="/process">карте процесса</a>.</p>
<div id="steps_tbl"></div>
<h3>Как выполнять</h3>
<ol>
<li>Выберите шаг с пометкой «вы здесь». Прочитайте описание и риск, посмотрите SQL.</li>
<li>Нажмите «Выполнить шаг». Ручной шаг отмечается с комментарием: кто выполнил и чем подтверждено.</li>
<li>Дождитесь статуса ✔. При ✖ прочитайте «Результат последнего запуска», устраните причину и повторите.</li>
<li>Шаг W3 повторяйте, пока идущие задания не закончатся.</li>
<li>Шаг W8 идёт около 4 часов. Окно утилиты закрывать нельзя: с закрытием прервётся сеанс и пересчёт откатится. Если пересчёт запущен на сервере через nohup, отметьте W8 вручную после успешного W9.</li>
</ol></section>

<section id="s7"><h2>7. Проверки</h2>
<p>Вкладка «Проверки» → «Запустить все проверки». Проверки только читают. Стадия задаёт ожидания: «до миграции», «окно», «после окна». В режиме «авто» стадия берётся из текущего шага.</p>
<p>Итог: <span class="st-ok">OK</span> — как ожидается; <span class="st-warn">ВНИМ.</span> — посмотреть глазами; <span class="st-fail">СТОП</span> — дальше идти нельзя; <span class="st-info">инфо</span> — значение для протокола.</p>
<div id="checks_tbl"></div>
<p>Кроме базы проверяется рабочее место: найден ли sqlplus, на месте ли файлы пакета, есть ли копия для отката, доступна ли папка журналов, сколько часов до 06:00.</p>
<p>Отдельные проверки встроены в шаги: W3 (идущие задания), W4 (открытые проводки), W9 (результат пересчёта), W14 (сверка сальдо двумя способами), A1 (первый прогон job 8).</p>
<figure><img class="shot" src="/screenshots/04_checks.png" alt="" onerror="this.parentNode.style.display='none'"><figcaption>Вкладка «Проверки» на TEST.</figcaption></figure></section>

<section id="s8"><h2>8. Мониторинг процессов</h2>
<p>Каждый запуск — отдельный процесс sqlplus в своём потоке. Окно не блокируется: можно смотреть другие шаги, проверки и монитор, пока идёт длительная операция.</p>
<h3>Вкладка «Процессы»</h3>
<p>Номер, название, тип (чтение / ИЗМЕНЕНИЕ), PID, время старта, длительность, статус и последняя строка вывода. Выберите строку — ниже появится вывод, он дополняется на лету. «Остановить выбранный» завершает клиент sqlplus; незавершённая транзакция в базе откатывается.</p>
<h3>Вкладка «Монитор БД»</h3>
<p>Отдельный лёгкий сеанс раз в 10 секунд (интервал настраивается) читает:</p>
<ul>
<li>состояние: триггеры, <code>job_queue_processes</code>, идущие задания, блокировки на <code>TMDB_CM</code>, размер <code>TXSLD</code>/<code>TSLD</code>, свободное место, объём UNDO в работе;</li>
<li>сессии утилиты в <code>v$session</code> (module = SLDMIG): SID, шаг, событие ожидания, SQL_ID, UNDO;</li>
<li><code>v$session_longops</code> — процент выполнения и оценка оставшегося времени;</li>
<li>журнал <code>XPROCESS_LOG</code> — сообщения пересчёта и сжатия сальдо.</li>
</ul>
<p>Во время W8 главные признаки хода: растёт размер TXSLD, в longops идут сканирования, в журнале появляются записи «Пересчёт актуального сальдо для TXSLD … завершён».</p>
<figure><img class="shot" src="/screenshots/06_monitor_longops.png" alt="" onerror="this.parentNode.style.display='none'"><figcaption>Монитор БД во время длительной операции.</figcaption></figure>
<figure><img class="shot" src="/screenshots/07_processes.png" alt="" onerror="this.parentNode.style.display='none'"><figcaption>Вкладка «Процессы».</figcaption></figure>
<p>То же самое видно в браузере: на <a href="/process">карте процесса</a>, раздел «Что происходит прямо сейчас». Страницу можно открыть на втором мониторе.</p></section>

<section id="s9"><h2>9. Откат</h2>
<p>Шаг «Откат» доступен в любой момент. Он выключает оба триггера, очищает <code>TXSLD</code> и <code>TSLD</code>, возвращает код пакета из копии шага P1, снова ломает job 8 (если он уже перенастроен) и запускает планировщик. Проводки не затрагиваются. Длительность — около 15 минут.</p>
<table><tr><th>Когда откатывать</th><th>Условие</th></tr>
<tr><td>в любой момент</td><td>ошибка места или ORA на шаге W8, не устранённая за 30 минут</td></tr>
<tr><td>03:30</td><td>TXSLD ещё не досчитан</td></tr>
<tr><td>05:00</td><td>крайний срок: работы не закончены</td></tr>
<tr><td>после W14</td><td>сверка сальдо показала расхождения, причина не найдена</td></tr></table>
<div class="note">Job 13 откат не восстанавливает: он был сломан и не использовался. Его определение сохранено в <code>MIG_SLD_JOBS_BACKUP</code>.</div></section>

<section id="s10"><h2>10. Как утилита проверялась на TEST</h2>
<p>Проверка выполнена 11.11.2026 на тестовой базе в режиме сухого прогона. На PROD утилита не запускалась.</p>
<table><tr><th>Что проверено</th><th>Как</th></tr>
<tr><td>Подключение и защита «не та база»</td><td>профиль TEST, имя сервера совпало с <code>expected_host</code></td></tr>
<tr><td>Все проверки</td><td>выполнены по-настоящему (только чтение)</td></tr>
<tr><td>Копия пакета, сравнение кода с файлами</td><td>выполнено по-настоящему (только чтение базы)</td></tr>
<tr><td>Изменяющие шаги</td><td>сухой прогон: SQL показан, выполнены только контрольные запросы</td></tr>
<tr><td>Мониторинг длительной операции</td><td>40-секундная имитация вместо пересчёта остатков</td></tr>
<tr><td>Сверка сальдо</td><td>по-настоящему на контрольную дату <b>31.12.2026</b> (декабрь 2026), счёт 2171, аналитика 2905; 75 строк сальдо, расхождений 0. Первый запуск занял 63 секунды, повторные — секунды</td></tr></table>
<div class="note">Не проверялось: реальное выполнение изменяющих шагов (остановка планировщика, закрытие сессий, очистка и пересчёт, переключение триггеров, перенастройка заданий, откат). На общей тестовой базе это остановило бы задания, закрыло чужие сессии и уничтожило сальдо, которое считалось 3,5 часа. SQL этих шагов повторяет скрипт, выполненный вручную на тестовой базе.</div>
<figure><img class="shot" src="/screenshots/09_balance_check.png" alt="" onerror="this.parentNode.style.display='none'"><figcaption>Сверка сальдо на 31.12.2026.</figcaption></figure>
<figure><img class="shot" src="/screenshots/10_all_steps.png" alt="" onerror="this.parentNode.style.display='none'"><figcaption>Все шаги пройдены в сухом прогоне.</figcaption></figure></section>

<section id="s11"><h2>11. Файлы, журналы, настройки</h2>
<table><tr><th>Файл / папка</th><th>Назначение</th></tr>
<tr><td><code>sld_migrator.py</code></td><td>окно, запуск процессов, монитор, встроенный веб-сервер</td></tr>
<tr><td><code>steps.py</code></td><td>каталог шагов и проверок с SQL — единственное место, где они описаны</td></tr>
<tr><td><code>webdocs.py</code></td><td>встроенные HTML-страницы: эта документация и карта процесса</td></tr>
<tr><td><code>sld_migrator.ini</code></td><td>путь к sqlplus, профили баз, пороги проверок. Паролей нет.</td></tr>
<tr><td><code>run.bat</code></td><td>запуск двойным щелчком</td></tr>
<tr><td><code>logs\&lt;профиль&gt;\</code></td><td>журнал каждого запуска: полный вывод sqlplus, время, статус. Прикладывать к тикету.</td></tr>
<tr><td><code>state\state_&lt;профиль&gt;.json</code></td><td>отметки шагов. Переживают перезапуск утилиты.</td></tr>
<tr><td><code>backups\</code></td><td>копии кода пакета, снятые шагом P1</td></tr>
<tr><td><code>docs\</code></td><td>эта документация и карта процесса отдельными файлами (<code>python sld_migrator.py --export-html</code>)</td></tr>
<tr><td><code>screenshots\</code></td><td>снимки экрана проверки на TEST</td></tr></table>
<h3>Параметры профиля</h3>
<table><tr><th>Параметр</th><th>Смысл</th></tr>
<tr><td><code>dsn</code>, <code>user</code></td><td>строка подключения и пользователь</td></tr>
<tr><td><code>expected_host</code></td><td>имя сервера базы; при несовпадении работа блокируется</td></tr>
<tr><td><code>kind</code></td><td><code>test</code> или <code>prod</code> — включает усиленные подтверждения</td></tr>
<tr><td><code>check_date</code>, <code>check_cont</code>, <code>check_sc</code></td><td>дата, счёт и аналитики для сверки сальдо (W14). Пустая дата = конец прошлого месяца.</td></tr>
<tr><td><code>need_tables_mb</code>, <code>need_ind_mb</code>, <code>need_undo_mb</code></td><td>пороги проверок места</td></tr>
<tr><td><code>jqp_default</code></td><td>значение job_queue_processes, если шаг W1 его не запомнил</td></tr></table>
<p>Кодировка: файлы SQL хранятся в UTF-8, утилита передаёт их в sqlplus в CP1251 (<code>NLS_LANG=AMERICAN_AMERICA.CL8MSWIN1251</code>). При ручном запуске этих файлов через sqlplus кириллица в сообщениях пакета исказится — используйте утилиту.</p></section>

<section id="s12"><h2>12. Типичные ошибки</h2>
<table><tr><th>Сообщение</th><th>Причина и действие</th></tr>
<tr><td>sqlplus не найден</td><td>Исправьте путь <code>sqlplus</code> в <code>sld_migrator.ini</code>.</td></tr>
<tr><td>ORA-01017</td><td>Неверный пароль.</td></tr>
<tr><td>ORA-12170, ORA-12541</td><td>Нет сети до базы или не тот порт в профиле.</td></tr>
<tr><td>«Это не та база»</td><td>Сервер не совпал с <code>expected_host</code>. Проверьте профиль и строку подключения.</td></tr>
<tr><td>«Сначала выполните шаг …»</td><td>Нарушен порядок. Выполните указанный шаг.</td></tr>
<tr><td>ORA-01653 на W8</td><td>Кончилось место в TBSUN4_TABLES. Добавить файл данных; если не успеть — откат.</td></tr>
<tr><td>ORA-30036 на W8</td><td>Кончился UNDO. Расширить UNDO, повторить W8; если не успеть — откат.</td></tr>
<tr><td>ORA-00054 на W6 или W10</td><td>Таблица занята. Утилита ждёт до 5 минут; затем повторите W4–W5.</td></tr>
<tr><td>ORA-03113, ORA-03135 на W8</td><td>Обрыв сети. Транзакция откатилась. Повторить W8 или запустить на сервере.</td></tr>
<tr><td>«контроль не прошёл»</td><td>Шаг выполнился, но состояние базы не то, что ожидалось. Читайте вывод шага.</td></tr></table></section>

<section id="s13"><h2>13. Безопасность</h2>
<ul>
<li>Пароль вводится при подключении, передаётся в sqlplus через стандартный ввод и не попадает в командную строку, файлы настроек и журналы.</li>
<li>Для автоматических прогонов пароль можно передать переменной окружения <code>SLDMIG_PWD_TEST</code> / <code>SLDMIG_PWD_PROD</code>.</li>
<li>Веб-страницы доступны только с этого компьютера (127.0.0.1) и только на чтение: из браузера ничего запустить нельзя.</li>
<li>После работ клиент меняет пароль учётной записи (шаг A4).</li>
</ul></section>
</main>
<script>""" + JS_COMMON + r"""
function render(){
  document.getElementById('badges').innerHTML=badges();
  var h='';
  STATE.phases.forEach(function(p){
    h+='<h3>'+esc(p.title)+' <span style="font-weight:400;color:#64748b">— '+esc(p.sub)+'</span></h3><table><tr><th style="width:52px">Шаг</th><th>Действие</th><th style="width:96px">Тип</th><th style="width:150px">Кто</th><th style="width:120px">Когда</th><th style="width:110px">Статус</th></tr>';
    STATE.steps.filter(function(s){return s.phase==p.id}).forEach(function(s){
      h+='<tr><td><b>'+esc(s.id)+'</b></td><td><b>'+esc(s.title)+'</b><br><span style="color:#475569">'+esc(s.desc)+'</span></td><td><span class="k '+s.kind+'">'+KIND_RU[s.kind]+'</span></td><td>'+esc(s.who)+'</td><td>'+esc(s.when)+'<br><span class="st-info">'+esc(s.dur)+'</span></td><td>'+ST_IC[s.status]+' '+ST_RU[s.status]+'</td></tr>'});
    h+='</table>';
  });
  document.getElementById('steps_tbl').innerHTML=h;
  var res={}; (STATE.checks||[]).forEach(function(r){res[r.id]=r});
  var c='<table><tr><th>№</th><th>Группа</th><th>Проверка</th><th>до</th><th>окно</th><th>после</th><th>Последнее значение</th></tr>';
  (STATE.checks_def||[]).forEach(function(d){var r=res[d.id];
    c+='<tr><td>'+d.id+'</td><td>'+esc(d.group)+'</td><td>'+esc(d.title)+'</td><td>'+(d.pre?'●':'')+'</td><td>'+(d.window?'●':'')+'</td><td>'+(d.post?'●':'')+'</td><td>'+(r?'<span class="st-'+r.status+'">'+esc(r.value)+'</span>':'')+'</td></tr>'});
  document.getElementById('checks_tbl').innerHTML=c+'</table><p class="st-info">● — на этой стадии значение контролируется; без точки — выводится для протокола.</p>';
}
load(render); setInterval(function(){load(render)},5000);
</script></body></html>
"""
