-- =====================================================================
-- 01_ddl_objects.sql — новые объекты (источник: тестовая база, 2026-06-16/24)
-- Выполнять на PROD под MARKET. Идемпотентно: при повторном запуске
-- уже существующие объекты пропускаются.
-- =====================================================================
set serveroutput on
whenever sqlerror exit failure rollback

declare
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
  -- Статистика онлайн-компактирования сальдо (используется pkg_sld_util.partial_compact_sld)
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

  -- Индекс для хинта index(t(cont,dep)) в compact_int по TSLD
  -- (для TXSLD аналогичный индекс TXSLD_CONT_DEP_I на PROD уже есть)
  ddl('TSLD_CONT_DEP',
      'create index tsld_cont_dep on tsld (cont, dep) tablespace tbsun4_tables');
end;
/
