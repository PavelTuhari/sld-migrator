-- =====================================================================
-- 00_precheck.sql  — ТОЛЬКО ЧТЕНИЕ. Выполнять на PROD под MARKET за 1–2 дня
-- до окна и повторно непосредственно перед началом работ.
-- Результат сохранить (spool) и приложить к тикету.
-- =====================================================================
set linesize 300 pagesize 5000 trimspool on
spool 00_precheck_&_DATE..log

prompt === 1. База / версия
select sys_context('USERENV','DB_NAME') db, sys_context('USERENV','SERVER_HOST') host,
       sys_context('USERENV','CURRENT_SCHEMA') schema, to_char(sysdate,'dd.mm.yyyy hh24:mi:ss') now
from dual;

prompt === 2. Состояние переносимых объектов (ожидаем: PKG_SLD_UTIL от 2025-11-20/2026-02-13, XSLD_COMPACT_STATS и TSLD_CONT_DEP отсутствуют)
select object_type, object_name, status, to_char(last_ddl_time,'yyyy-mm-dd hh24:mi') last_ddl
from user_objects
where object_name in ('PKG_SLD_UTIL','TMDB_CM_TSLD_TR','TMDB_CM_RESTRICT_DML_TRG',
                      'XSLD_COMPACT_STATS','XSLD_COMPACT_STATS_UK','TSLD_CONT_DEP','TXSLD','TSLD')
order by object_name, object_type;

prompt === 3. Триггеры TMDB_CM (ожидаем TMDB_CM_TSLD_TR=DISABLED, TMDB_CM_RESTRICT_DML_TRG=DISABLED)
select trigger_name, status from user_triggers
where table_name = 'TMDB_CM' and trigger_name in ('TMDB_CM_TSLD_TR','TMDB_CM_RESTRICT_DML_TRG');

prompt === 4. Невалидные объекты (зафиксировать «до»)
select object_type, object_name from user_objects where status <> 'VALID' order by 1,2;

prompt === 5. Объём данных
select table_name, num_rows, to_char(last_analyzed,'yyyy-mm-dd') analyzed from user_tables
where table_name in ('TMDB_CM','TXSLD','TSLD');
select segment_name, round(sum(bytes)/1048576) mb from user_segments
where segment_name in ('TXSLD','TSLD','TXSLD_CONT_DEP_I','TXSLD_CONT_SC_I','TSLD_CONT_SC_DEP','TSLD_DEP','TSLD_SC')
group by segment_name order by 1;

prompt === 6. Свободное место (БЛОКЕР: TBSUN4_TABLES >= 16 GB, TBSUN4_IND >= 10 GB с учётом автоприроста)
select d.tablespace_name,
       round(sum(d.bytes)/1048576)                                         alloc_mb,
       round(sum(decode(d.autoextensible,'YES',d.maxbytes,d.bytes))/1048576) max_mb,
       (select round(sum(f.bytes)/1048576) from dba_free_space f where f.tablespace_name = d.tablespace_name) free_mb,
       round(sum(decode(d.autoextensible,'YES',d.maxbytes,d.bytes))/1048576 - sum(d.bytes)/1048576)
         + (select round(sum(f.bytes)/1048576) from dba_free_space f where f.tablespace_name = d.tablespace_name) available_mb
from dba_data_files d
where d.tablespace_name in ('TBSUN4_TABLES','TBSUN4_IND')
group by d.tablespace_name;

prompt === 7. Задания (снимок «до»)
select job, broken, interval, to_char(next_date,'yyyy-mm-dd hh24:mi') next_date, substr(what,1,100) what
from user_jobs order by job;
select job_name, enabled, state, repeat_interval from user_scheduler_jobs order by 1;
select name, value from v$parameter where name in ('job_queue_processes','undo_retention');

prompt === 8. Справочно: счета с актуальным сальдо (TMS_PDC.SLD_ACTUAL='1')
select cont from tms_pdc where cont1 = 0 and sld_actual = '1' order by cont;

spool off
