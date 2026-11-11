-- =====================================================================
-- 07_restore_jobs.sql — перенастройка job 8 / 13 и запуск планировщика.
-- Выполнять ПО ШАГАМ после успешного 06_enable_online.sql.
-- =====================================================================
set serveroutput on linesize 250 pagesize 500
whenever sqlerror exit failure rollback

-- ШАГ 1. Job 8: вместо старого rebuild_sld_actual (broken с 2017) — ежедневное
-- онлайн-компактирование по счетам в 06:00, как на тесте.
-- Job 13 (un$sld.rebuild, broken) удаляется, чтобы его случайно не включили
-- и он не пересёкся с job 8 .
begin
  dbms_job.change(8,
    what      => 'begin -- rebuild partial pe conturi'||chr(10)||'pkg_sld_util.partial_compact_sld(p_raise => false);'||chr(10)||'end;',
    next_date => trunc(sysdate) + 1 + 6/24,
    interval  => 'TRUNC(SYSDATE) + 1 + 6/24');
  dbms_job.broken(8, false, trunc(sysdate) + 1 + 6/24);
  dbms_job.remove(13);
  commit;
end;
/
-- Если окно закончилось до 06:00 того же дня и первый прогон нужен уже сегодня —
-- заменить в обоих местах «trunc(sysdate) + 1 + 6/24» на «trunc(sysdate) + 6/24».

-- ШАГ 2. Какие задания пропустили своё время, пока планировщик стоял.
-- ВНИМАНИЕ: они стартуют сразу после шага 3. Если окно перешло через полночь,
-- задания с параметром trunc(sysdate) отработают уже «завтрашней» датой:
--   64  Yrgb_Docs.close_promo(trunc(sysdate))        — план 22:30
--   224 pkg_cards_unisim.sync_sales(1)               — план 22:45
--   284 pkg_sales_unisim.process_sales(trunc(sysdate)) — каждые 5 минут
-- Для них после шага 3 вручную выполнить вызов с датой прошедшего дня
-- (решение и точные вызовы — за Тестировщик, см. план работ, п. «Вечерние задания»).
select job, to_char(next_date,'dd.mm hh24:mi') planned, substr(what,1,100) what
from user_jobs where broken = 'N' and next_date < sysdate order by next_date;
select job_name, to_char(next_run_date,'dd.mm hh24:mi') planned
from user_scheduler_jobs where enabled = 'TRUE' and next_run_date < systimestamp order by next_run_date;

-- ШАГ 3. Запустить планировщик (значение из снимка шага 1 скрипта 04; на 11.11.2026 было 1000)
alter system set job_queue_processes = 1000;

-- ШАГ 4. Контроль: состав и статусы заданий те же, что до окна (+ job 8 активен, job 13 удалён)
select b.kind, b.job_id, b.state before_state,
       nvl((select j.broken from user_jobs j where to_char(j.job) = b.job_id and b.kind = 'DBMS_JOB'),
           (select s.enabled from user_scheduler_jobs s where s.job_name = b.job_id and b.kind = 'SCHEDULER')) now_state
from mig_sld_jobs_backup b
where b.state <> nvl((select j.broken from user_jobs j where to_char(j.job) = b.job_id and b.kind = 'DBMS_JOB'),
                 nvl((select s.enabled from user_scheduler_jobs s where s.job_name = b.job_id and b.kind = 'SCHEDULER'),'-'));
-- Ожидаем ровно 2 строки: job 8 (Y -> N) и job 13 (Y -> пусто).
select job, broken, interval, to_char(next_date,'yyyy-mm-dd hh24:mi') next_date, substr(what,1,80) what
from user_jobs where job in (8,13);
