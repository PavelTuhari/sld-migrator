-- =====================================================================
-- 04_freeze_jobs_and_cm.sql — НАЧАЛО ОКНА. Выполнять на PROD под MARKET
-- ПО ШАГАМ (не одним запуском): после каждого шага смотреть результат.
-- Порядок взят из скрипта, проверенного на тестовой базе
-- .
-- У MARKET на PROD есть привилегия ALTER SYSTEM (проверено 11.11.2026).
-- =====================================================================
set serveroutput on linesize 250 pagesize 500

-- ШАГ 1. Снимок заданий «до» (для контроля и отката). Удалить после приёмки.
create table mig_sld_jobs_backup as
select 'DBMS_JOB' kind, to_char(job) job_id, broken state, interval,
       last_date, next_date, substr(what,1,4000) what, sysdate saved_at
from user_jobs
union all
select 'SCHEDULER', job_name, enabled, repeat_interval,
       cast(last_start_date as date), cast(next_run_date as date), substr(job_action,1,4000), sysdate
from user_scheduler_jobs;

select name, value from v$parameter where name = 'job_queue_processes';   -- на 11.11.2026 = 1000, ЗАПИСАТЬ

-- ШАГ 2. Остановить планировщик целиком (DBMS_JOB и DBMS_SCHEDULER).
-- Задания не трогаем: их next_date сохраняется, после окна они стартуют сами.
alter system set job_queue_processes = 0;

-- ШАГ 3. Дождаться, пока уже запущенные задания закончатся (должно стать пусто).
-- Job 284 (process_sales) идёт каждые 5 минут — обычно ждать 1–5 минут.
-- (dba_jobs_running на PROD отвечает ~3 минуты, поэтому смотрим блокировки типа JQ)
select l.sid, l.id2 job, (select substr(j.what,1,80) from user_jobs j where j.job = l.id2) what
from v$lock l where l.type = 'JQ';
select job_name, session_id, elapsed_time from user_scheduler_running_jobs;

-- ШАГ 4. Кто держит открытые проводки (сначала ПОСМОТРЕТЬ, позвонить пользователю, если нужно)
select s.sid, s.terminal, s.osuser, s.machine, s.program, s.client_identifier nrdoc,
       round(l.last_convert/3600,1) hours, t.used_urec, s.last_call_et
from dba_dml_locks l, v$session s, v$transaction t
where l.name = 'TMDB_CM' and l.session_id = s.sid and s.taddr = t.addr
order by l.last_convert desc;

-- ШАГ 5. Закрыть эти сессии (несохранённые проводки в них теряются!)
begin
  for c in (select l.session_id
            from dba_dml_locks l, v$session s, v$transaction t
            where l.name = 'TMDB_CM' and l.session_id = s.sid and s.taddr = t.addr)
  loop
    un$adm.autokill(p_sid => c.session_id, p_force => true);
  end loop;
end;
/

-- ШАГ 6. Заблокировать изменение проводок на время пересчёта
alter session set ddl_lock_timeout = 300;
alter trigger tmdb_cm_restrict_dml_trg enable;

-- ШАГ 7. Контроль: RESTRICT = ENABLED, TSLD_TR = DISABLED, блокировок на TMDB_CM нет
select trigger_name, status from user_triggers
where trigger_name in ('TMDB_CM_RESTRICT_DML_TRG','TMDB_CM_TSLD_TR');
select count(*) cm_locks from dba_dml_locks where name = 'TMDB_CM';
