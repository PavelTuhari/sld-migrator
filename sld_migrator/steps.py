# -*- coding: utf-8 -*-
"""Каталог шагов и проверок миграции «Blocarea vinzarilor in minus» (TEST -> PROD).

Единственный источник правды: из этого файла строятся дерево шагов в GUI,
HTML-карта процесса и раздел документации «Порядок работ».
SQL повторяет скрипты 00–08 и 99 из папки ../scripts (проверенный на тестовой базе порядок).
"""

PHASES = [
    ("E0", "Этап 0. Условия старта", "до назначения даты окна"),
    ("E1", "Этап 1. Подготовка", "днём в день окна, без простоя, ≈1 час"),
    ("E2", "Этап 2. Окно", "21:00 → ≈02:00, проводки закрыты"),
    ("E3", "Этап 3. После окна", "утро и следующие дни"),
    ("RB", "Откат", "только при сбое, ≈15 минут"),
]


def mark(key, expr, frm="dual"):
    """SQL, печатающий служебную строку @@KEY|значение — её разбирает утилита."""
    return ("set heading off feedback off\n"
            "select '@@%s|'||(%s) from %s;\n"
            "set heading on feedback on\n" % (key, expr, frm))


TRG_INFO = (
    "select trigger_name, status from user_triggers\n"
    "where trigger_name in ('TMDB_CM_RESTRICT_DML_TRG','TMDB_CM_TSLD_TR') order by 1;\n"
    + mark("RESTRICT", "select status from user_triggers where trigger_name='TMDB_CM_RESTRICT_DML_TRG'")
    + mark("TSLD_TR", "select status from user_triggers where trigger_name='TMDB_CM_TSLD_TR'")
)
JQP_MARK = mark("JQP", "select value from v$parameter where name='job_queue_processes'")

CM_SESSIONS = """select s.sid, s.osuser, s.machine, s.program, s.client_identifier nrdoc,
       round(l.last_convert/3600,1) hours, t.used_urec, s.last_call_et
from dba_dml_locks l, v$session s, v$transaction t
where l.name = 'TMDB_CM' and l.session_id = s.sid and s.taddr = t.addr
order by l.last_convert desc;
""" + mark("CM_TX", "select count(*) from dba_dml_locks l, v$session s, v$transaction t "
                    "where l.name='TMDB_CM' and l.session_id=s.sid and s.taddr=t.addr")

RUNNING_JOBS = """select l.sid, l.id2 job, (select substr(j.what,1,80) from user_jobs j where j.job = l.id2) what
from v$lock l where l.type = 'JQ';
select job_name, session_id, elapsed_time from user_scheduler_running_jobs;
""" + mark("RUN_JOBS", "(select count(*) from v$lock where type='JQ') + (select count(*) from user_scheduler_running_jobs)")

DEMO_LONGOP = """-- ИМИТАЦИЯ (сухой прогон): 40 секунд «пересчёта», видимых в v$session_longops.
-- Данные не читаются и не меняются.
declare
  r binary_integer := dbms_application_info.set_session_longops_nohint;
  s binary_integer;
  n constant pls_integer := 40;
begin
  for i in 1..n loop
    dbms_application_info.set_session_longops(r, s, 'SLDMIG demo rebuild', 0, 0, i, n,
        case when i <= 30 then 'TXSLD (imitation)' else 'TSLD (imitation)' end, 'steps');
    if mod(i,10) = 0 then dbms_output.put_line('demo progress '||i||'/'||n); end if;
    dbms_lock.sleep(1);
  end loop;
end;
/
"""

STEPS = [
    # ------------------------------------------------------------------ Этап 0
    dict(id="E0.1", phase="E0", kind="manual", title="Место в TBSUN4_TABLES: +16–20 ГБ",
         who="Админ БД", when="до окна", dur="—",
         desc="Свежая TXSLD после пересчёта на тесте 12.11.2026 — 7,5 ГБ и ещё 4,6 ГБ индексов. Первое же сжатие в 06:00 увеличило таблицу до 11,1 ГБ, "
              "а индексы до 7,3 ГБ: сжатие каждый день целиком переписывает самый крупный счёт. Поэтому всё место нужно уже к первому утру после окна. "
              "На PROD при обследовании было доступно 3,4 ГБ — это блокер. "
              "После добавления файлов данных запустите вкладку «Проверки»: строка «TBSUN4_TABLES» должна стать зелёной.",
         risk="Без места пересчёт упадёт с ORA-01653 через 1–2 часа работы. Если места хватит только на пересчёт, его не хватит первому сжатию."),
    dict(id="E0.2", phase="E0", kind="manual", title="UNDO: проверить запас UNDOTBS",
         who="Админ БД", when="до окна", dur="—",
         desc="Вставка в TXSLD идёт одной транзакцией. На тесте 12.11.2026 она заняла 15,5 ГБ UNDO (около 2,1 МБ на 1 МБ таблицы); "
              "на PROD проводок на 7 % больше — нужно не меньше 20 ГБ свободного UNDO. UNDOTBS2 на PROD расти не может "
              "(автоприрост исчерпан), но 11.11.2026 в нём было свободно 239 ГБ.",
         risk="ORA-30036 в середине пересчёта → откат транзакции и потеря 2–3 часов."),
    dict(id="E0.3", phase="E0", kind="manual", title="Письменное согласие клиента",
         who="Менеджер проекта", when="до окна", dur="—",
         desc="Дата окна, старт 21:00, запрет проводок до ≈02:00, ответственный со стороны клиента на связи. "
              "",
         risk="Работы на PROD без согласия клиента не начинаются."),
    dict(id="E0.4", phase="E0", kind="manual", title="Решение по сальдо 2025",
         who="Тестировщик → клиент", when="до окна", dur="—",
         desc="Фиксировать сальдо 2025 до миграции или принять, что после фиксации потребуется повторный пересчёт.",
         risk="Повторное окно на 4–5 часов позже."),
    dict(id="E0.5", phase="E0", kind="manual", title="Запрет параллельных работ на PROD",
         who="Менеджер проекта → клиент", when="за сутки до окна", dur="—",
         desc="Другие подрядчики не ведут работ на PROD за сутки до окна и до приёмки.",
         risk="Чужие изменения во время пересчёта делают результат непроверяемым."),
    dict(id="E0.6", phase="E0", kind="manual", title="Способ запуска пересчёта",
         who="Админ БД", when="до окна", dur="—",
         desc="Вариант А — запуск из этой утилиты по сети. Утилита удерживает соединение пробами TCP keepalive (параметр профиля "
              "keepalive): без них сетевое оборудование рвёт молчащее соединение. На тесте 12.11.2026 попытка без удержания "
              "оборвалась на 120-й минуте, попытка с удержанием прошла за 2 ч 35 мин. При настоящем обрыве связи транзакция "
              "откатится, пересчёт повторяется. "
              "Вариант Б — запуск 05_rebuild_sld.sql на сервере БД через nohup; тогда утилита только наблюдает, "
              "а шаг W8 отмечается вручную после проверки W9.",
         risk="Обрыв сети на 2-м часу = откат (на тесте он шёл 75 минут) и повтор пересчёта с нуля."),
    dict(id="E0.7", phase="E0", kind="manual", title="Решение по вечерним заданиям",
         who="Тестировщик", when="до окна", dur="—",
         desc="Задания 284, 304, 64, 224 принимают trunc(sysdate). После окна они стартуют уже с датой следующего дня. "
              "Нужно решить: дозапускать вручную с датой прошедшего дня или они сами подберут необработанное.",
         risk="Продажи/промо последнего вечера останутся необработанными."),

    # ------------------------------------------------------------------ Этап 1
    dict(id="P0", phase="E1", kind="check", action="checks", stage="pre",
         title="Предпроверка базы (все проверки)",
         who="Разработчик", when="10:00", dur="1–2 мин",
         desc="Запускает полный набор проверок вкладки «Проверки» в режиме «до миграции»: та ли база, привилегии, "
              "объекты, триггеры, задания, место, UNDO, блокировки. Красная строка = стоп.",
         risk="—"),
    dict(id="P1", phase="E1", kind="check", action="backup_pkg",
         title="Копия текущего PKG_SLD_UTIL (для отката)",
         who="Разработчик", when="10:20", dur="10 сек",
         desc="Читает исходный код спецификации и тела пакета из базы и сохраняет в папку backups. "
              "Именно эти файлы использует шаг «Откат».",
         risk="Без копии шаги P3/P4 не разблокируются."),
    dict(id="P2", phase="E1", kind="change", title="Новые объекты: таблица и 2 индекса",
         who="Разработчик", when="10:30", dur="1–3 мин", script="01_ddl_objects.sql",
         desc="XSLD_COMPACT_STATS (статистика онлайн-сжатия), индекс XSLD_COMPACT_STATS_UK и индекс TSLD_CONT_DEP. "
              "Идемпотентно: существующие объекты пропускаются.",
         risk="Нет. Объекты ни на что не влияют, пока не установлен новый пакет.",
         sql="""declare
  procedure ddl(p_name varchar2, p_sql varchar2) is
    v_cnt int;
  begin
    select count(*) into v_cnt from user_objects where object_name = p_name;
    if v_cnt = 0 then
      execute immediate p_sql;
      dbms_output.put_line('CREATED  '||p_name);
    else
      dbms_output.put_line('EXISTS   '||p_name||' (skip)');
    end if;
  end;
begin
  ddl('XSLD_COMPACT_STATS', q'[
    create table xsld_compact_stats (
      account              number(*,0)  not null,
      rows_before          number(*,0),
      rows_locked          number(*,0),
      rows_after           number(*,0),
      start_time           date,
      update_time          date,
      insert_groupped_time date,
      delete_time          date,
      dep                  number(*,0),
      source_name          varchar2(32) not null
    ) tablespace tbsun4_tables]');
  ddl('XSLD_COMPACT_STATS_UK',
      'create index xsld_compact_stats_uk on xsld_compact_stats (source_name, account, dep) tablespace tbsun4_tables');
  ddl('TSLD_CONT_DEP',
      'create index tsld_cont_dep on tsld (cont, dep) tablespace tbsun4_tables');
end;
/
""",
         info_sql="select object_type, object_name, status from user_objects\n"
                  "where object_name in ('XSLD_COMPACT_STATS','XSLD_COMPACT_STATS_UK','TSLD_CONT_DEP') order by 2;\n"
                  + mark("NEW_OBJ", "select count(*) from user_objects where object_name in "
                                    "('XSLD_COMPACT_STATS','XSLD_COMPACT_STATS_UK','TSLD_CONT_DEP') and status='VALID'"),
         expect={"NEW_OBJ": "3"}),
    dict(id="P3", phase="E1", kind="change", action="install_pkg", pkg_type="PACKAGE",
         script="02_pkg_sld_util_spec.sql", title="PKG_SLD_UTIL — спецификация v1.03",
         who="Разработчик", when="10:40", dur="10 сек",
         desc="Сначала утилита сравнивает код в базе с файлом. Если совпадает — шаг пропускается. "
              "Иначе выполняется CREATE OR REPLACE и проверяется статус VALID.",
         risk="Днём безопасно: триггер онлайн-сальдо на PROD выключен, job 8 сломан, других вызовов пакета нет.",
         info_sql=mark("PKG_SPEC", "select status from user_objects where object_name='PKG_SLD_UTIL' and object_type='PACKAGE'"),
         expect={"PKG_SPEC": "VALID"}),
    dict(id="P4", phase="E1", kind="change", action="install_pkg", pkg_type="PACKAGE BODY",
         script="03_pkg_sld_util_body.sql", title="PKG_SLD_UTIL — тело v1.03",
         who="Разработчик", when="10:45", dur="10 сек",
         desc="То же для тела пакета: сравнение, установка, проверка VALID. Файл хранится в UTF-8, "
              "утилита сама перекодирует его в CP1251 (кириллица в сообщениях журнала).",
         risk="Ошибка компиляции → пакет INVALID. Откат: шаг «Откат» вернёт код из копии P1.",
         info_sql=mark("PKG_BODY", "select status from user_objects where object_name='PKG_SLD_UTIL' and object_type='PACKAGE BODY'")
                  + mark("HAS_PARTIAL", "select count(*) from user_source where name='PKG_SLD_UTIL' and type='PACKAGE' "
                                        "and lower(text) like '%partial_compact_sld%'"),
         expect={"PKG_BODY": "VALID"}),
    dict(id="P5", phase="E1", kind="manual", title="Подтверждён бэкап PROD",
         who="админ клиента", when="до 18:00", dur="—",
         desc="Клиент подтверждает, что есть свежая резервная копия базы.", risk="Откат утилиты не восстанавливает проводки — только сальдо и код."),
    dict(id="P6", phase="E1", kind="manual", title="Напоминание пользователям: с 21:00 проводки закрыты",
         who="Тестировщик", when="18:00", dur="—",
         desc="Пользователи back-office сохраняют и закрывают документы до 21:00.",
         risk="Несохранённые проводки в открытых сессиях будут потеряны на шаге W5."),

    # ------------------------------------------------------------------ Этап 2
    dict(id="W1", phase="E2", kind="change", title="Снимок заданий «до»",
         who="Разработчик", when="21:00", dur="5 сек", script="04, шаг 1",
         desc="Создаёт таблицу MIG_SLD_JOBS_BACKUP со списком DBMS_JOB и DBMS_SCHEDULER и запоминает "
              "текущее значение job_queue_processes — им шаг W13 запустит планировщик обратно.",
         risk="Нет.",
         sql="""declare n int;
begin
  select count(*) into n from user_tables where table_name = 'MIG_SLD_JOBS_BACKUP';
  if n = 0 then
    execute immediate q'[create table mig_sld_jobs_backup as
      select 'DBMS_JOB' kind, to_char(job) job_id, broken state, interval,
             last_date, next_date, substr(what,1,4000) what, sysdate saved_at
      from user_jobs
      union all
      select 'SCHEDULER', job_name, enabled, repeat_interval,
             cast(last_start_date as date), cast(next_run_date as date), substr(job_action,1,4000), sysdate
      from user_scheduler_jobs]';
    dbms_output.put_line('CREATED  MIG_SLD_JOBS_BACKUP');
  else
    dbms_output.put_line('EXISTS   MIG_SLD_JOBS_BACKUP (skip)');
  end if;
end;
/
""",
         info_sql="select count(*) dbms_jobs, sum(decode(broken,'N',1,0)) active from user_jobs;\n"
                  "select count(*) scheduler_jobs, sum(decode(enabled,'TRUE',1,0)) enabled from user_scheduler_jobs;\n"
                  + JQP_MARK + mark("SNAP", "select count(*) from user_tables where table_name='MIG_SLD_JOBS_BACKUP'"),
         expect={"SNAP": "1"}),
    dict(id="W2", phase="E2", kind="change", title="Остановить планировщик (job_queue_processes = 0)",
         who="Разработчик", when="21:02", dur="1 сек", script="04, шаг 2",
         desc="Останавливает запуск всех заданий DBMS_JOB и DBMS_SCHEDULER целиком. Сами задания не трогаются: "
              "их расписание сохраняется, после окна они стартуют сами.",
         risk="Вечерние задания (22:00–23:30) сдвигаются за окно — см. условие E0.7.",
         sql="alter system set job_queue_processes = 0;\n", info_sql=JQP_MARK, expect={"JQP": "0"}),
    dict(id="W3", phase="E2", kind="check", title="Дождаться завершения идущих заданий",
         who="Разработчик", when="21:03–21:10", dur="1–5 мин (повторять)", script="04, шаг 3",
         desc="Уже запущенные задания доработают сами. Повторяйте шаг, пока список не станет пустым. "
              "Job 284 (process_sales) идёт каждые 5 минут — обычно ждать 1–5 минут.",
         risk="Если начать пересчёт при работающем задании, оно упадёт на блокировке проводок.",
         info_sql=RUNNING_JOBS, expect={"RUN_JOBS": "0"}),
    dict(id="W4", phase="E2", kind="check", title="Кто держит открытые проводки",
         who="Разработчик", when="21:10", dur="5 сек", script="04, шаг 4",
         desc="Список сессий с незавершёнными транзакциями по TMDB_CM. Сначала посмотреть и при необходимости "
              "позвонить пользователю — на следующем шаге эти сессии будут закрыты.",
         risk="—", info_sql=CM_SESSIONS),
    dict(id="W5", phase="E2", kind="change", title="Закрыть сессии с открытыми проводками",
         who="Разработчик", when="21:12", dur="10 сек", script="04, шаг 5",
         desc="un$adm.autokill(p_force => true) для каждой сессии из списка W4.",
         risk="Несохранённые проводки в этих сессиях теряются.",
         sql="""begin
  for c in (select l.session_id
            from dba_dml_locks l, v$session s, v$transaction t
            where l.name = 'TMDB_CM' and l.session_id = s.sid and s.taddr = t.addr)
  loop
    un$adm.autokill(p_sid => c.session_id, p_force => true);
    dbms_output.put_line('killed sid '||c.session_id);
  end loop;
end;
/
""", info_sql=CM_SESSIONS, expect={"CM_TX": "0"}),
    dict(id="W6", phase="E2", kind="change", title="Включить блокировку проводок",
         who="Разработчик", when="21:15", dur="до 5 мин", script="04, шаг 6",
         desc="Включает триггер TMDB_CM_RESTRICT_DML_TRG: любые изменения проводок запрещены до конца пересчёта.",
         risk="С этого момента пользователи back-office не могут проводить документы.",
         sql="alter session set ddl_lock_timeout = 300;\nalter trigger tmdb_cm_restrict_dml_trg enable;\n",
         info_sql=TRG_INFO, expect={"RESTRICT": "ENABLED"}),
    dict(id="W7", phase="E2", kind="check", action="checks", stage="window",
         title="Контроль перед пересчётом (все проверки)",
         who="Разработчик", when="21:18", dur="1–2 мин", script="04, шаг 7",
         desc="Полный набор проверок в режиме «окно»: блокировка включена, планировщик стоит, блокировок на TMDB_CM нет, "
              "места и UNDO хватает. Последняя точка, где можно остановиться без последствий.",
         risk="—"),
    dict(id="W8", phase="E2", kind="long", title="Очистка и пересчёт TXSLD → TSLD",
         who="Админ БД / разработчик", when="21:20 → ≈01:30", dur="≈4 часа", script="05_rebuild_sld.sql",
         desc="truncate обеих таблиц, затем set_env('sld_allow_rebuild_wo_truncate','true') и "
              "pkg_sld_util.rebuild_sld_actual, затем сбор статистики. На тесте: 18.06.2026 вручную — TXSLD 2 ч 52 мин, TSLD 50 мин; "
              "12.11.2026 этим шагом — TXSLD 1 ч 47 мин, TSLD 47 мин. "
              "Ход виден на вкладке «Монитор БД»: longops, рост сегмента TXSLD, журнал SaldoRebuild. "
              "В сухом прогоне вместо пересчёта выполняется 40-секундная имитация.",
         risk="Нет места / UNDO / обрыв сети (после обрыва база откатывает посчитанное, на тесте — 75 минут). Точки решения об откате: 03:30 (TXSLD не досчитан) и 05:00 (крайний срок).",
         sql="""declare
  v_status varchar2(10);
begin
  select status into v_status from user_triggers where trigger_name = 'TMDB_CM_RESTRICT_DML_TRG';
  if v_status <> 'ENABLED' then
    raise_application_error(-20001, 'TMDB_CM_RESTRICT_DML_TRG is not ENABLED - stop');
  end if;
end;
/
truncate table txsld drop storage;
truncate table tsld drop storage;
select to_char(sysdate,'dd.mm.yyyy hh24:mi:ss') rebuild_start from dual;
begin
  set_env('sld_allow_rebuild_wo_truncate','true');
  pkg_sld_util.rebuild_sld_actual;   -- p_table = null: TXSLD, then TSLD; p_raise = true
end;
/
select to_char(sysdate,'dd.mm.yyyy hh24:mi:ss') rebuild_end from dual;
exec dbms_stats.gather_table_stats(user,'TXSLD',cascade=>true,degree=>4)
exec dbms_stats.gather_table_stats(user,'TSLD', cascade=>true)
""", demo_sql=DEMO_LONGOP),
    dict(id="W9", phase="E2", kind="check", title="Контроль результата пересчёта",
         who="Разработчик", when="≈01:30", dur="10 сек",
         desc="TXSLD и TSLD не пустые, в журнале SaldoRebuild есть запись о завершении без ошибок.",
         risk="Пустая таблица или ошибка в журнале → откат.",
         info_sql="select segment_name, round(sum(bytes)/1048576) mb from user_segments\n"
                  "where segment_name in ('TXSLD','TSLD') group by segment_name order by 1;\n"
                  "select to_char(log_date,'dd.mm hh24:mi:ss') at, message_type t, substr(message,1,110) message from (\n"
                  "  select * from xprocess_log where id > (select max(id) - 20000 from xprocess_log)\n"
                  "  and (message like '%TXSLD%' or message like '%TSLD%' or lower(message) like '%сальдо%')\n"
                  "  order by id desc) where rownum <= 8;\n"
                  + mark("TXSLD_ROWS", "select count(*) from txsld where rownum <= 1")
                  + mark("TSLD_ROWS", "select count(*) from tsld where rownum <= 1"),
         expect={"TXSLD_ROWS": "1", "TSLD_ROWS": "1"}),
    dict(id="W10", phase="E2", kind="change", title="Включить онлайн-сальдо, снять блокировку проводок",
         who="Разработчик", when="01:35", dur="до 5 мин", script="06_enable_online.sql",
         desc="Порядок важен: сначала включается TMDB_CM_TSLD_TR (проводки пишут в TXSLD/TSLD), "
              "затем выключается TMDB_CM_RESTRICT_DML_TRG (пользователи снова могут проводить).",
         risk="Если поменять порядок, проводки пройдут мимо сальдо.",
         sql="alter session set ddl_lock_timeout = 300;\nalter trigger tmdb_cm_tsld_tr enable;\n"
             "alter trigger tmdb_cm_restrict_dml_trg disable;\n",
         info_sql=TRG_INFO, expect={"TSLD_TR": "ENABLED", "RESTRICT": "DISABLED"}),
    dict(id="W11", phase="E2", kind="change", title="Job 8 → partial_compact_sld 06:00, удалить job 13",
         who="Разработчик", when="01:40", dur="5 сек", script="07, шаг 1",
         desc="Job 8 вместо сломанного с 2017 года rebuild_sld_actual запускает ежедневное онлайн-сжатие по счетам в 06:00. "
              "Job 13 (un$sld.rebuild) удаляется, чтобы его случайно не включили. "
              "Первый запуск — в ближайшие 06:00, и он идёт дольше обычного: на тесте 12.11.2026 за 3 ч 46 мин не закончился "
              "(обычно 2 ч 20–35 мин), ошибок не было. За это утро TXSLD выросла с 7,5 до 11,1 ГБ.",
         risk="Первое сжатие после пересчёта идёт в рабочие часы и сразу увеличивает TXSLD: место должно быть заранее (E0.1), "
              "ночь окна выбирают с учётом этого.",
         sql="""declare
  -- ближайшие 06:00: если окно закончилось после полуночи, первый запуск будет этим же утром
  v_next date := case when sysdate < trunc(sysdate) + 6/24 then trunc(sysdate) + 6/24 else trunc(sysdate) + 1 + 6/24 end;
begin
  dbms_job.change(8,
    what      => 'begin -- rebuild partial pe conturi'||chr(10)||'pkg_sld_util.partial_compact_sld(p_raise => false);'||chr(10)||'end;',
    next_date => v_next,
    interval  => 'TRUNC(SYSDATE) + 1 + 6/24');
  dbms_job.broken(8, false, v_next);
  for j in (select job from user_jobs where job = 13) loop
    dbms_job.remove(13);
  end loop;
  commit;
end;
/
""",
         info_sql="select job, broken, interval, to_char(next_date,'yyyy-mm-dd hh24:mi') next_date, substr(what,1,90) what\n"
                  "from user_jobs where job in (8,13);\n"
                  + mark("JOB8", "select nvl(max(broken||':'||case when lower(what) like '%partial_compact_sld%' then 'partial' else 'old' end),'absent') from user_jobs where job=8")
                  + mark("JOB13", "select count(*) from user_jobs where job=13"),
         expect={"JOB8": "N:partial", "JOB13": "0"}),
    dict(id="W12", phase="E2", kind="check", title="Какие задания пропустили своё время",
         who="Разработчик", when="01:42", dur="5 сек", script="07, шаг 2",
         desc="Эти задания стартуют сразу после W13. Задания с trunc(sysdate) отработают уже «завтрашней» датой — "
              "действовать по решению E0.7.",
         risk="—",
         info_sql="select job, to_char(next_date,'dd.mm hh24:mi') planned, substr(what,1,100) what\n"
                  "from user_jobs where broken = 'N' and next_date < sysdate order by next_date;\n"
                  "select job_name, to_char(next_run_date,'dd.mm hh24:mi') planned\n"
                  "from user_scheduler_jobs where enabled = 'TRUE' and next_run_date < systimestamp order by next_run_date;\n"),
    dict(id="W13", phase="E2", kind="change", title="Запустить планировщик",
         who="Разработчик", when="01:43", dur="1 сек", script="07, шаг 3",
         desc="Возвращает job_queue_processes к значению, запомненному на шаге W1 (на PROD было 1000).",
         risk="Просроченные задания стартуют все сразу.",
         sql="alter system set job_queue_processes = {JQP_SAVED};\n", info_sql=JQP_MARK,
         expect={"JQP": "{JQP_SAVED}"}),
    dict(id="W14", phase="E2", kind="check", action="balance", title="Сверка сальдо: быстрое против классического",
         who="Разработчик, тестировщик", when="01:45", dur="1–5 мин", script="08_postcheck.sql",
         desc="un$sld.make считает сальдо на контрольную дату двумя способами: по TXSLD (быстрый) и по проводкам "
              "(pOldMethod => true). Результаты сравниваются построчно, расхождений должно быть 0. "
              "Дата, счёт и аналитики задаются в профиле (check_date, check_cont, check_sc).",
         risk="Расхождение → не открывать блокировку продаж на кассах, разбираться.",
         expect={"DIFF": "0"}),
    dict(id="W15", phase="E2", kind="check", action="checks", stage="post",
         title="Итоговые проверки после окна",
         who="Разработчик", when="01:55", dur="1–2 мин",
         desc="Полный набор проверок в режиме «после»: онлайн-сальдо включено, блокировка снята, планировщик работает, "
              "job 8 настроен, job 13 удалён, пакет VALID.",
         risk="—"),
    dict(id="W16", phase="E2", kind="manual", title="Дозапуск вечерних заданий, сообщение клиенту",
         who="Тестировщик", when="02:00", dur="—",
         desc="По решению E0.7. Клиенту: окно закрыто, проводки открыты.", risk="—"),

    # ------------------------------------------------------------------ Этап 3
    dict(id="A1", phase="E3", kind="check", title="Первый прогон job 8 (06:00)",
         who="Разработчик", when="с 06:00", dur="обычно 2,5 ч; первый раз дольше",
         desc="В XSLD_COMPACT_STATS у всех сегодняшних строк должно быть заполнено delete_time; "
              "в журнале SldCompactOnline нет ошибок. "
              "Первый прогон после пересчёта идёт дольше обычного: на тесте 12.11.2026 за 3 ч 46 мин обработано 627 счетов TXSLD из 1 646, "
              "ошибок не было; до конца прогон не наблюдался. Пока он идёт, у части строк delete_time пуст — это не ошибка. "
              "Признак проблемы: в журнале есть сообщения с типом, отличным от I, или у задания 8 failures больше 0.",
         risk="Пока первое сжатие не закончилось, шаг покажет незавершённые счета. Повторите его позже.",
         info_sql="select source_name, count(*) accounts, count(delete_time) finished,\n"
                  "       to_char(min(start_time),'dd.mm hh24:mi') first_start, to_char(max(delete_time),'dd.mm hh24:mi') last_end\n"
                  "from xsld_compact_stats group by source_name;\n"
                  "select job, broken, to_char(last_date,'dd.mm hh24:mi') last_run, to_char(next_date,'dd.mm hh24:mi') next_run, failures\n"
                  "from user_jobs where job = 8;\n"
                  + mark("COMPACT_OPEN", "select count(*) from xsld_compact_stats where delete_time is null")),
    dict(id="A2", phase="E3", kind="manual", title="Проведение документов пользователями",
         who="Тестировщик, клиент", when="утро", dur="—",
         desc="Провести, изменить и удалить тестовый документ; отчёт Universal; остатки сходятся.", risk="—"),
    dict(id="A3", phase="E3", kind="change", title="Удалить MIG_SLD_JOBS_BACKUP",
         who="Разработчик", when="+3–5 дней", dur="1 сек",
         desc="Снимок заданий больше не нужен после приёмки.", risk="Нет.",
         sql="drop table mig_sld_jobs_backup purge;\n",
         info_sql=mark("SNAP", "select count(*) from user_tables where table_name='MIG_SLD_JOBS_BACKUP'"),
         expect={"SNAP": "0"}),
    dict(id="A4", phase="E3", kind="manual", title="Клиент меняет пароли MARKET",
         who="клиент", when="после работ", dur="—",
         desc="После работ пароли учётной записи меняются.", risk="—"),
    dict(id="A5", phase="E3", kind="manual", title="Front-office: кассы и тест блокировки продаж",
         who="Тестировщик", when="отдельно", dur="—",
         desc="Связь касс с PROD back-office, обновление касс, проверка, что продажа в минус блокируется. "
              "Вне этой утилиты.", risk="—"),

    # ------------------------------------------------------------------ Откат
    dict(id="RB", phase="RB", kind="change", action="rollback", title="Откат к состоянию до миграции",
         who="Разработчик", when="при сбое; крайний срок 05:00", dur="≈15 мин", script="99_rollback.sql",
         desc="Выключает оба триггера, очищает TXSLD и TSLD, возвращает код PKG_SLD_UTIL из копии шага P1, "
              "снова ломает job 8 (если он уже перенастроен) и запускает планировщик. Проводки не затрагиваются.",
         risk="После отката база работает как до миграции: онлайн-сальдо нет.",
         sql="""alter session set ddl_lock_timeout = 300;
alter trigger tmdb_cm_tsld_tr disable;
alter trigger tmdb_cm_restrict_dml_trg disable;
truncate table txsld;
truncate table tsld;
{PKG_BACKUP}
begin
  for j in (select job from user_jobs where job = 8 and lower(what) like '%partial_compact_sld%') loop
    dbms_job.broken(8, true);
  end loop;
  commit;
end;
/
alter system set job_queue_processes = {JQP_SAVED};
""",
         info_sql=TRG_INFO + JQP_MARK
                  + mark("PKG_BODY", "select status from user_objects where object_name='PKG_SLD_UTIL' and object_type='PACKAGE BODY'"),
         expect={"TSLD_TR": "DISABLED", "RESTRICT": "DISABLED", "PKG_BODY": "VALID"}),
]

# ---------------------------------------------------------------------------
# Проверки. rule: словарь {стадия: ожидаемое значение | функция} или функция.
# Стадии: pre (до миграции), window (окно, перед пересчётом), post (после окна).
# Функция получает (значение, cfg) и возвращает (статус, сообщение); статус: ok | warn | fail | info.
# ---------------------------------------------------------------------------

def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return None


def _ge(need_key, default, unit="МБ", fail=True):
    def f(v, cfg):
        need = float(cfg.get(need_key, default))
        n = _num(v)
        if n is None:
            return "warn", "нет значения"
        if n >= need:
            return "ok", "%.0f %s, нужно ≥ %.0f" % (n, unit, need)
        return ("fail" if fail else "warn"), "%.0f %s, нужно ≥ %.0f" % (n, unit, need)
    return f


def _eq(exp, bad="fail"):
    def f(v, cfg):
        return ("ok", "как ожидается") if str(v) == exp else (bad, "ожидается %s" % exp)
    return f


def _info(v, cfg):
    return "info", ""


def _host(v, cfg):
    exp = cfg.get("expected_host", "")
    if not exp:
        return "warn", "expected_host не задан в профиле"
    return ("ok", "это база профиля") if str(v).lower() == exp.lower() else ("fail", "ожидался сервер %s — НЕ ТА БАЗА" % exp)


def _undo(v, cfg):
    # значение: "свободно_МБ/может_расти_МБ"
    try:
        free, grow = [float(x) for x in str(v).split("/")]
    except Exception:
        return "warn", "не удалось разобрать"
    need = float(cfg.get("need_undo_mb", 20000))
    tot = free + grow
    return ("ok" if tot >= need else "warn"), "свободно %.0f + рост %.0f МБ; ориентир ≥ %.0f" % (free, grow, need)


def _zero_ok(bad="warn", msg="должно быть 0"):
    def f(v, cfg):
        return ("ok", "") if str(v) == "0" else (bad, msg)
    return f


CHECKS = [
    # --- соединение и права
    dict(id="D1", group="База", title="Сервер базы совпадает с профилем",
         sql="sys_context('USERENV','SERVER_HOST')", rule=_host),
    dict(id="D2", group="База", title="Версия Oracle",
         sql="select max(version) from v$instance", rule=_info),
    dict(id="D3", group="База", title="Схема и время сервера",
         sql="sys_context('USERENV','CURRENT_SCHEMA')||' '||to_char(sysdate,'dd.mm.yyyy hh24:mi:ss')", rule=_info),
    dict(id="D4", group="Права", title="ALTER SYSTEM, SELECT ANY DICTIONARY, CREATE JOB",
         sql="select count(*) from session_privs where privilege in ('ALTER SYSTEM','SELECT ANY DICTIONARY','CREATE JOB')",
         rule=_eq("3")),
    dict(id="D5", group="Права", title="Доступны UN$ADM, SET_ENV, DBMS_LOCK, UN$SLD",
         sql="select count(distinct object_name) from all_objects where object_name in ('UN$ADM','SET_ENV','DBMS_LOCK','UN$SLD')",
         rule=_eq("4")),
    # --- объекты
    dict(id="O1", group="Объекты", title="PKG_SLD_UTIL: спецификация",
         sql="select nvl(max(status),'ABSENT') from user_objects where object_name='PKG_SLD_UTIL' and object_type='PACKAGE'",
         rule=_eq("VALID")),
    dict(id="O2", group="Объекты", title="PKG_SLD_UTIL: тело",
         sql="select nvl(max(status),'ABSENT') from user_objects where object_name='PKG_SLD_UTIL' and object_type='PACKAGE BODY'",
         rule=_eq("VALID")),
    dict(id="O3", group="Объекты", title="Версия пакета содержит partial_compact_sld (v1.03)",
         sql="select decode(count(*),0,'нет','да') from user_source where name='PKG_SLD_UTIL' and type='PACKAGE' and lower(text) like '%partial_compact_sld%'",
         rule={"pre": _info, "window": _eq("да"), "post": _eq("да")}),
    dict(id="O4", group="Объекты", title="Новые объекты (таблица + 2 индекса) созданы",
         sql="select count(*) from user_objects where object_name in ('XSLD_COMPACT_STATS','XSLD_COMPACT_STATS_UK','TSLD_CONT_DEP')",
         rule={"pre": _info, "window": _eq("3"), "post": _eq("3")}),
    dict(id="O5", group="Объекты", title="Невалидные объекты схемы",
         sql="select count(*) from user_objects where status <> 'VALID'", rule=_info),
    dict(id="O6", group="Объекты", title="Последнее изменение PKG_SLD_UTIL (тело)",
         sql="select to_char(max(last_ddl_time),'yyyy-mm-dd hh24:mi') from user_objects where object_name='PKG_SLD_UTIL' and object_type='PACKAGE BODY'",
         rule=_info),
    # --- триггеры
    dict(id="T1", group="Триггеры", title="TMDB_CM_RESTRICT_DML_TRG (блокировка проводок)",
         sql="select status from user_triggers where trigger_name='TMDB_CM_RESTRICT_DML_TRG'",
         rule={"pre": _eq("DISABLED"), "window": _eq("ENABLED"), "post": _eq("DISABLED")}),
    dict(id="T2", group="Триггеры", title="TMDB_CM_TSLD_TR (онлайн-сальдо)",
         sql="select status from user_triggers where trigger_name='TMDB_CM_TSLD_TR'",
         rule={"pre": _info, "window": _info, "post": _eq("ENABLED")}),
    # --- задания
    dict(id="J1", group="Задания", title="job_queue_processes",
         sql="select value from v$parameter where name='job_queue_processes'",
         rule={"pre": lambda v, c: ("ok", "планировщик работает") if v != "0" else ("warn", "планировщик остановлен"),
               "window": _eq("0"),
               "post": lambda v, c: ("ok", "планировщик работает") if v != "0" else ("fail", "планировщик остановлен")}),
    dict(id="J2", group="Задания", title="Job 8 (состояние : версия)",
         sql="select nvl(max(decode(broken,'Y','сломан','активен')||' : '||case when lower(what) like '%partial_compact_sld%' then 'partial_compact_sld' else 'старый вызов' end),'нет') from user_jobs where job=8",
         rule={"pre": _info, "window": _info, "post": _eq("активен : partial_compact_sld")}),
    dict(id="J3", group="Задания", title="Job 13 (un$sld.rebuild) удалён",
         sql="select decode(count(*),0,'удалён','есть') from user_jobs where job=13",
         rule={"pre": _info, "window": _info, "post": _eq("удалён")}),
    dict(id="J4", group="Задания", title="Сейчас выполняется заданий",
         sql="(select count(*) from v$lock where type='JQ') + (select count(*) from user_scheduler_running_jobs)",
         rule={"pre": _info, "window": _zero_ok("fail", "дождаться завершения (шаг W3)"), "post": _info}),
    dict(id="J5", group="Задания", title="Активных DBMS_JOB / включённых SCHEDULER",
         sql="(select count(*) from user_jobs where broken='N')||' / '||(select count(*) from user_scheduler_jobs where enabled='TRUE')",
         rule=_info),
    dict(id="J6", group="Задания", title="Снимок заданий MIG_SLD_JOBS_BACKUP",
         sql="select decode(count(*),0,'нет','есть') from user_tables where table_name='MIG_SLD_JOBS_BACKUP'",
         rule={"pre": _info, "window": _eq("есть"), "post": _info}),
    # --- место
    dict(id="S1", group="Место", title="TBSUN4_TABLES: доступно с учётом автоприроста, МБ",
         sql="""(select nvl(round(sum(decode(d.autoextensible,'YES',greatest(d.maxbytes,d.bytes),d.bytes) - d.bytes)/1048576),0)
        from dba_data_files d where d.tablespace_name='TBSUN4_TABLES')
       + nvl((select round(sum(f.bytes)/1048576) from dba_free_space f where f.tablespace_name='TBSUN4_TABLES'),0)""",
         rule={"pre": _ge("need_tables_mb", 12500), "window": _ge("need_tables_mb", 12500), "post": _info}),
    dict(id="S2", group="Место", title="TBSUN4_IND: доступно с учётом автоприроста, МБ",
         sql="""(select nvl(round(sum(decode(d.autoextensible,'YES',greatest(d.maxbytes,d.bytes),d.bytes) - d.bytes)/1048576),0)
        from dba_data_files d where d.tablespace_name='TBSUN4_IND')
       + nvl((select round(sum(f.bytes)/1048576) from dba_free_space f where f.tablespace_name='TBSUN4_IND'),0)""",
         rule={"pre": _ge("need_ind_mb", 10000), "window": _ge("need_ind_mb", 10000), "post": _info}),
    dict(id="S3", group="Место", title="UNDO: свободно / может вырасти, МБ",
         sql="""select (select nvl(round(sum(f.bytes)/1048576),0) from dba_free_space f, dba_tablespaces t
        where t.contents='UNDO' and f.tablespace_name=t.tablespace_name
          and t.tablespace_name=(select upper(value) from v$parameter where name='undo_tablespace'))
       ||'/'||
       (select nvl(round(sum(decode(d.autoextensible,'YES',greatest(d.maxbytes,d.bytes),d.bytes)-d.bytes)/1048576),0)
        from dba_data_files d where d.tablespace_name=(select upper(value) from v$parameter where name='undo_tablespace'))
from dual""",
         rule={"pre": _undo, "window": _undo, "post": _info}),
    dict(id="S4", group="Место", title="Размер TXSLD / TSLD, МБ",
         sql="(select nvl(round(sum(bytes)/1048576),0) from user_segments where segment_name='TXSLD')||' / '||(select nvl(round(sum(bytes)/1048576),0) from user_segments where segment_name='TSLD')",
         rule=_info),
    # --- блокировки
    dict(id="K1", group="Блокировки", title="Блокировок на TMDB_CM",
         sql="select count(*) from dba_dml_locks where name='TMDB_CM'",
         rule={"pre": _info, "window": _zero_ok("fail", "закрыть сессии (шаги W4–W5)"), "post": _info}),
    dict(id="K2", group="Блокировки", title="Сессий с открытыми проводками",
         sql="select count(*) from dba_dml_locks l, v$session s, v$transaction t where l.name='TMDB_CM' and l.session_id=s.sid and s.taddr=t.addr",
         rule={"pre": _info, "window": _zero_ok("fail", "закрыть сессии (шаги W4–W5)"), "post": _info}),
    dict(id="K3", group="Блокировки", title="Других сессий утилиты (module SLDMIG)",
         sql="select count(*) from v$session where module='SLDMIG' and sid <> sys_context('USERENV','SID')",
         rule=_zero_ok("warn", "запущена ещё одна сессия утилиты")),
    # --- данные сальдо
    dict(id="B1", group="Сальдо", title="TXSLD содержит строки",
         sql="select decode(count(*),0,'пусто','есть') from txsld where rownum<=1",
         rule={"pre": _info, "window": _info, "post": _eq("есть")}),
    dict(id="B2", group="Сальдо", title="TSLD содержит строки",
         sql="select decode(count(*),0,'пусто','есть') from tsld where rownum<=1",
         rule={"pre": _info, "window": _info, "post": _eq("есть")}),
    dict(id="B3", group="Сальдо", title="Счетов с актуальным сальдо (TMS_PDC.SLD_ACTUAL='1')",
         sql="select count(*) from tms_pdc where cont1=0 and sld_actual='1'", rule=_info),
    dict(id="B4", group="Сальдо", title="Незавершённых строк в XSLD_COMPACT_STATS",
         sql="select decode((select count(*) from user_tables where table_name='XSLD_COMPACT_STATS'),0,'таблицы нет','см. шаг A1') from dual",
         rule=_info),
]


def step_by_id(sid):
    for s in STEPS:
        if s["id"] == sid:
            return s
    raise KeyError(sid)


def public_steps():
    """Каталог без функций — для JSON / HTML."""
    out = []
    for s in STEPS:
        d = {k: v for k, v in s.items() if k in
             ("id", "phase", "kind", "title", "who", "when", "dur", "desc", "risk", "script", "action")}
        d["sql"] = s.get("sql", "")
        d["info_sql"] = "\n".join(l for l in s.get("info_sql", "").splitlines()
                                  if not l.startswith("set heading") and "'@@" not in l)
        d["expect"] = {k: str(v) for k, v in s.get("expect", {}).items()}
        out.append(d)
    return out


def public_checks():
    def exp(rule, st):
        r = rule.get(st) if isinstance(rule, dict) else rule
        return "" if r is _info else "контроль"
    return [dict(id=c["id"], group=c["group"], title=c["title"],
                 pre=exp(c["rule"], "pre"), window=exp(c["rule"], "window"), post=exp(c["rule"], "post"))
            for c in CHECKS]
