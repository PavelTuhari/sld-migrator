-- =====================================================================
-- 05_rebuild_sld.sql — полный пересчёт актуального сальдо TXSLD / TSLD.
-- Повторяет способ, проверенный на тестовой базе 18.06.2026
--   truncate ... drop storage  ->  set_env('sld_allow_rebuild_wo_truncate','true')
--   ->  pkg_sld_util.rebuild_sld_actual
--
-- ЗАПУСКАТЬ НА СЕРВЕРЕ БД (sqlplus локально, через nohup/screen),
-- а не по сети: при длинной транзакции соединение рвётся (опыт тестов).
--   nohup sqlplus user/***@localhost/SERVICE @05_rebuild_sld.sql > 05_rebuild.out 2>&1 &
-- Если запуск на сервере невозможен — вариант через DBMS_JOB, см. конец файла.
--
-- Длительность: TXSLD ~3:05, TSLD ~0:55 (тест: 2:52 / 0:50 на 2,08 млрд строк TMDB_CM;
-- PROD = 2,22 млрд строк, +7%).
-- Предусловие: 04_freeze_jobs_and_cm.sql выполнен, TMDB_CM_RESTRICT_DML_TRG = ENABLED,
-- новый PKG_SLD_UTIL (02, 03) установлен.
--
-- Про полночь: вне 00:00–06:00 safe_truncate ничего не делает и пересчёт идёт
-- благодаря параметру sld_allow_rebuild_wo_truncate. После 00:00 safe_truncate
-- сам берёт эксклюзивную блокировку и очищает таблицу (она и так пустая) —
-- результат тот же, но на тесте этот путь не проходили (там запуск был в 14:03).
-- =====================================================================
set serveroutput on timing on
whenever sqlerror exit failure rollback
spool 05_rebuild_sld.log

declare
  v_status varchar2(10);
begin
  select status into v_status from user_triggers where trigger_name = 'TMDB_CM_RESTRICT_DML_TRG';
  if v_status <> 'ENABLED' then
    raise_application_error(-20001, 'TMDB_CM_RESTRICT_DML_TRG не включён — остановка');
  end if;
end;
/

truncate table txsld drop storage;
truncate table tsld drop storage;

select to_char(sysdate,'dd.mm.yyyy hh24:mi:ss') rebuild_start from dual;

begin
  set_env('sld_allow_rebuild_wo_truncate','true');
  pkg_sld_util.rebuild_sld_actual;   -- p_table = null: TXSLD, затем TSLD; p_raise = true
end;
/

select to_char(sysdate,'dd.mm.yyyy hh24:mi:ss') rebuild_end from dual;
select 'TXSLD' t, count(*) cnt from txsld union all select 'TSLD', count(*) from tsld;

exec dbms_stats.gather_table_stats(user,'TXSLD',cascade=>true,degree=>4)
exec dbms_stats.gather_table_stats(user,'TSLD', cascade=>true)

spool off
exit

-- ---------------------------------------------------------------------
-- Вариант Б (как на тесте): запуск через DBMS_JOB, если нет доступа к ОС сервера.
-- Требует job_queue_processes = 1 и чтобы ВСЕ остальные задания были остановлены
-- (broken / disabled), иначе они тоже стартуют.
-- ---------------------------------------------------------------------
-- alter system set job_queue_processes = 1;
-- declare
--   l_job number;
-- begin
--   dbms_job.submit(
--     job       => l_job,
--     what      => 'begin set_env(''sld_allow_rebuild_wo_truncate'',''true''); pkg_sld_util.rebuild_sld_actual; end;',
--     next_date => sysdate + 5/1440,
--     interval  => null);
--   commit;
-- end;
-- /
-- Наблюдение: журнал un$process_log («SaldoRebuild»), v$session_longops.
