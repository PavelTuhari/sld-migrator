CREATE OR REPLACE
package body pkg_sld_util is
----------------------------------------------------------------------------------------------------
procedure check_table_name(p_table varchar2) is
begin
  pkg_docs_util.assert(upper(p_table) in ('TSLD','TXSLD'),
  'Недопустимое имя таблицы ('||p_table||')!');
end;
----------------------------------------------------------------------------------------------------
function get_locks(p_table varchar2) return varchar2 is
v_msg long;
cr varchar2(1) := chr(10);
--------------------------------------------------
procedure add(p_str varchar2) is
v_max_len int := 32760;
begin
  if p_str is not null then
    if v_msg is null then
      v_msg := 'Table '||p_table||' is locked: '||cr;
    end if;
    --
    if length(v_msg) + length(p_str) + 1 < v_max_len then
      v_msg := v_msg || p_str || cr;
    end if;
  end if;
end;
--------------------------------------------------
begin
  for c in
  (
    select l.object_name, l.username, l.osuser, l.machine, l.terminal
         , l.program, l.module, l.action, l.client_info
         , l.sid, l.status, l.mode_held, l.last_convert, l.last_call_et
    from unv$lock l
    where object_name = upper(p_table)
  )
  loop
    add('object_name: '||c.object_name);
    add('username: '||c.username);
    add('osuser: '||c.osuser);
    add('machine: '||c.machine);
    add('terminal: '||c.terminal);
    add('program: '||c.program);
    add('module: '||c.module);
    add('action: '||c.action);
    add('client_info: '||c.client_info);
    add('sid: '||c.sid);
    add('status: '||c.status);
    add('mode_held: '||c.mode_held);
    add('last_convert: '||c.last_convert);
    add('last_call_et: '||c.last_call_et);
  end loop;

  return v_msg;
end;
----------------------------------------------------------------------------------------------------
procedure check_locks(p_table varchar2) is
 v_msg long;
begin
  v_msg := get_locks(p_table);
  --
  if v_msg is not null then
    msg(v_msg);
  end if;
end;
----------------------------------------------------------------------------------------------------
procedure lock_exclusive(p_table varchar2) is
begin
  execute immediate 'lock table '||p_table||' in exclusive mode nowait';
end;
----------------------------------------------------------------------------------------------------
procedure do_compact is
  v_id int := un$process_log.get_id('SaldoCompact');
begin

  begin
    un$process_log.log(v_id,'Сжатие актуального сальдо для TXSLD');
    un$sld.compact('TXSLD');
    un$process_log.log(v_id,'Сжатие актуального сальдо для TXSLD завершён');
  exception when others then
    un$process_log.log_exception(v_id);
  end;

  begin
    un$process_log.log(v_id,'Сжатие актуального сальдо для TSLD');
    un$sld.compact('TSLD');
    un$process_log.log(v_id,'Сжатие актуального сальдо для TSLD завершён');
  exception when others then
    un$process_log.log_exception(v_id);
  end;

end;
----------------------------------------------------------------------------------------------------
procedure lock_table(p_table varchar2, p_process_id int) is
 v_msg long;
 v_spin_count int := 3600*2;
begin
  for i in 1 .. v_spin_count loop
    v_msg := get_locks(p_table);
    --
    if v_msg is not null then
      if mod(i,100) = 0 then
        un$process_log.log(p_process_id,v_msg);
      end if;
      --
      if i = v_spin_count then
        msg(v_msg);
      end if;
      --
      dbms_lock.sleep(1);
    else
      lock_exclusive(p_table);
        exit;   /* adaugat 29.05.2026*/
      -- return; /* comentat 29.05.2026*/
    end if;
  end loop;
  /* 29.05.2026 Comentat deoarece se implimenteaza rebuild pe conturi, pt transzactii mai mici*/
--   do_compact;  --Если до 6 часов мы не смогли автоматически пересчитать сальдо, то вызываем do_compact
end;
----------------------------------------------------------------------------------------------------
function safe_truncate(p_table varchar2, p_process_id int) return boolean is
begin
  if (sysdate - trunc(sysdate))*24 between 0 and 6 then
    check_table_name(p_table);
    --
    lock_table(p_table, p_process_id);
    execute immediate 'truncate table '||p_table||' drop storage';
    if p_process_id is not null then
      un$process_log.log(p_process_id,p_table||' truncated');
    end if;
    return true;
  end if;

  return false;
end;
----------------------------------------------------------------------------------------------------
procedure do_rebuild(p_table varchar2) is
v_id int := un$process_log.get_id('SaldoRebuild');
begin
  un$process_log.log(v_id,'Пересчёт актуального сальдо для '||p_table);
  check_table_name(p_table);
  if safe_truncate(p_table,v_id) or get_env('sld_allow_rebuild_wo_truncate') = 'true' then
  un$sld.rebuild(p_table);
  un$process_log.log(v_id,'Пересчёт актуального сальдо для '||p_table||' завершён');
  else
    un$process_log.log(v_id,'Пересчёт актуального сальдо для '||p_table||' пропущен');
  end if;
end;
----------------------------------------------------------------------------------------------------
procedure rebuild_sld_actual(p_table varchar2, p_raise boolean) is
v_id int := un$process_log.get_id('SaldoRebuild');
v_mutex varchar2(128);
begin
  un$process_log.log(v_id,'Начало процедуры пересчёта актуального сальдо');
  dbms_application_info.set_module('pkg_sld_util','rebuild_sld_actual');
  -- Для исключения одновременного запуска
  v_mutex := pkg_docs_util.create_mutex(user||'_SaldoRebuild');
  if p_table is null then
    do_rebuild('TXSLD');
    do_rebuild('TSLD');
  else
    do_rebuild(p_table);
  end if;
  say(dbms_lock.release(v_mutex));
  un$process_log.log(v_id,'Процедура пересчёта актуального сальдо завершена');
exception when others then
  un$process_log.log_exception(v_id);
  if v_mutex is not null then
    say(dbms_lock.release(v_mutex));
  end if;
  if p_raise then
    raise;
  end if;
end;
----------------------------------------------------------------------------------------------------
procedure make_rebuild_job(p_hours int) is
v_job int;
begin
  pkg_docs_util.not_null(p_hours,'Укажите время запуска (в часах)!');
  pkg_docs_util.assertw(p_hours between 0 and 6,
    'Рекомендуемое время пересчёта сальдо - между 0 и 6 часами!');
  dbms_job.submit
  (
    job => v_job,
    what => 'pkg_sld_util.rebuild_sld_actual(p_raise => false);',
    next_date => trunc(sysdate) + 1 + p_hours/24,
    interval => 'trunc(sysdate) + 1 + '||p_hours||'/24'
  );
  say('Job number: '||v_job);
  commit;
end;
-------------------------------------------------------------------------------------
function get_prc_sld_online return int is
begin
 return un$process_log.get_id('SldCompactOnline');
end;
----------------------------------------------------------------------------------------------------
procedure compact_int(p_table varchar2, p_cont int, p_dep int) is
 --e942 exception;
 --pragma exception_init(e942,-942);
 v_rows int;
 v_msg varchar2(1000) := 'Tabel '||p_table||', Cont ' || p_cont || case when p_dep is not null then ' dep '||p_dep end||' ';
----------------------------------------------------------------
procedure upd_stats(p_cont int, p_dep int, p_name_col_date varchar2, p_add_name_col varchar2 := '', p_add_val_col varchar2:= '') is
 pragma autonomous_transaction;
 v_cols varchar2(500);
 v_sql long;
begin
  if p_add_name_col is not null then
    v_cols := p_add_name_col ||' = '|| p_add_val_col;
  end if;

  if p_name_col_date is not null then
    v_cols := v_cols || case when v_cols is not null then ', ' else ' ' end || p_name_col_date||' = SYSDATE ';
  end if;

  v_sql :=  'update xsld_compact_stats set '||v_cols||'
    where source_name = :p_table and
    account = :p_cont and decode(dep, :p_dep, ''='') = ''=''';

  execute immediate v_sql using p_table, p_cont, p_dep;
  commit;
end;
----------------------------------------------------------------
begin

  un$process_log.log(get_prc_sld_online, v_msg || 'Initiere Update');
  upd_stats(p_cont, p_dep, 'start_time');

  execute immediate
  'UPDATE /*+ index(t(cont,dep)) */ '||p_table||' t SET ISLOCKED=''1'' WHERE cont = :p_cont and ' ||case when p_dep is not null then ' dep = :p_dep '  else  ' :dep is null ' end
  using p_cont, p_dep;

  v_rows := sql%rowcount;
  un$process_log.log(get_prc_sld_online, v_msg || 'Finisare Update rows: '||v_rows);
  upd_stats(p_cont, p_dep, 'update_time', 'rows_locked', v_rows );

  un$process_log.log(get_prc_sld_online, v_msg || 'Initiere Insert');
  execute immediate
  'INSERT INTO '||p_table||
   '(COD,CONT,CONT1,SC,DEP,SC1,NRDOC,STRSC,NRCM,DATA,DIV,VALUTA,F,M'||
   ',SUMA,CANT,PRICE,SUMAVAL,SUMAGAAP,CANT1)'||
   ' SELECT /*+ index(t(cont,dep)) */ '||
   ' COD,CONT,CONT1,SC,DEP,SC1,NRDOC,STRSC,NRCM,DATA,DIV,VALUTA,F,M'||
   ',SUM(SUMA),SUM(CANT),CASE WHEN SUM(CANT)<>0 THEN SUM(SUMA)/SUM(CANT)END'||
   ',SUM(SUMAVAL),SUM(SUMAGAAP),SUM(CANT1)'||
   ' FROM '||p_table||' t
    WHERE ISLOCKED=''1'' and cont = :p_cont and ' ||case when p_dep is not null then ' dep = :p_dep '  else  ' :dep is null ' end ||
   ' GROUP BY COD,CONT,CONT1,SC,DEP,SC1,NRDOC,STRSC,NRCM,DATA,DIV,VALUTA,F,M' using p_cont, p_dep;

  v_rows := sql%rowcount;
  un$process_log.log(get_prc_sld_online, v_msg || 'Finisare Insert rows: '||v_rows);
  upd_stats(p_cont, p_dep, 'insert_groupped_time', 'rows_after', v_rows );

  un$process_log.log(get_prc_sld_online, v_msg|| 'Initiere Delete');
  execute immediate
  'delete /*+ index(t(cont,dep)) */ from '||p_table||' t where islocked=''1'' and cont = :p_cont and ' ||case when p_dep is not null then ' dep = :p_dep '  else  ' :dep is null ' end
   using p_cont, p_dep;

  v_rows := sql%rowcount;
  un$process_log.log(get_prc_sld_online, v_msg || 'Finisare Delete rows: '||v_rows);
  upd_stats(p_cont, p_dep, 'delete_time');

--exception when e942 then
--  null;
end;
--------------------------------------------------------------------------------
procedure partial_compact(p_table varchar2) is
 v_msg varchar2(1000);
 v_module varchar2(128) := lower(sys_context('userenv','module'));
 v_Sql long;

procedure fill_stats(p_table varchar2) is

  pragma autonomous_transaction;
  begin
    un$process_log.log(get_prc_sld_online, p_table || '.Initiere completare xsld_compact_stats');

    v_sql := 'delete from xsld_compact_stats where source_name = :p_table';
    execute immediate v_sql using p_table;
    --
    v_sql := '
    insert into xsld_compact_stats (source_name, account, dep, rows_before)
    select '''||p_table||''', cont, dep, count(*)
    from (
      select cont, case when cont in (2171, 7112, 2414, 6112, 6111, 6118, 6119) then dep end dep
      from '||p_table||'
      where cont is not null
    )
    group by cont, dep';

    execute immediate v_sql;

    un$process_log.log(get_prc_sld_online, p_table || '.Finisare completare xsld_compact_stats');
    commit;
  end;
begin
  -- Т.к. compact вызывается при архивации при помощи Versions и в большинстве
  -- случаев при этом создаёт лишнюю нагрузку, то вызываетм только при явном
  -- задании параметра AutoCompactSLD
  un$process_log.log(get_prc_sld_online, p_table || '.Start compact online');

  if v_module in (lower('uniVersions.exe'),lower('un4Versions.exe'))
     and get_env('AutoCompactSLD') is null
  then
    un$process_log.log(get_prc_sld_online,'Iesire prin return din compact online');
    return;
  end if;

  check_table_name(p_table);

  fill_stats(p_table);

  un$process_log.log(get_prc_sld_online, p_table || '.Start prelucrare ciclu for');

  for c in (
    select account, dep
    from xsld_compact_stats
    where source_name = p_table
    order by account + 0, dep + 0  -- pentru full table scan
  )
  loop
      begin
        v_msg := ' cont ' || c.account || case when c.dep is not null then ' dep '||c.dep end;
        un$process_log.log(get_prc_sld_online, p_table || '.Initiere prelucrare' || v_msg);

        compact_int(p_table, c.account, c.dep);

        commit;
        un$process_log.log(get_prc_sld_online, p_table || '.Finisare prelucrare' || v_msg);
       exception when others then
         un$process_log.log_exception(get_prc_sld_online,p_table || '.Recalcul cont' || v_msg || '. Start rollback. Eroare: '||sqlcode||' -> '||sqlerrm);
         rollback;
         un$process_log.log_exception(get_prc_sld_online, p_table || '.Recalcul cont' || v_msg || '. End rollback.');
        end;
  end loop;
  un$process_log.log(get_prc_sld_online, p_table || '.End compact online');
exception when others then
  un$process_log.log_exception(get_prc_sld_online, p_table || '.End compact online with error');

end;
--------------------------------------------------------------------------------
procedure partial_compact_sld(p_table varchar2, p_raise boolean) is
 v_mutex varchar2(128);
begin
  un$process_log.log(get_prc_sld_online,'Start recalculare solduri compact online');
  dbms_application_info.set_module('pkg_sld_util','compact_partial_sld');

  -- Для исключения одновременного запуска
  v_mutex := pkg_docs_util.create_mutex(user||'_SaldoRebuild');

  --
  if p_table is null then
    partial_compact('TXSLD');
    partial_compact('TSLD');
  else
    partial_compact(p_table);
  end if;
  --
  say(dbms_lock.release(v_mutex));
  un$process_log.log(get_prc_sld_online,'Finisare recalculare solduri compact online');
exception when others then
  un$process_log.log_exception(get_prc_sld_online,'Finisare recalculare solduri compact online cu erori');
  if v_mutex is not null then
    say(dbms_lock.release(v_mutex));
  end if;
  if p_raise then
    raise;
  end if;
end;
--------------------------------------------------------------------------------
end;
/
