-- =====================================================================
-- 08_postcheck.sql — приёмка на PROD. Сравнение «быстрого» сальдо (TXSLD)
-- с классическим расчётом по проводкам (FC) на тех же аналитиках, что и на тесте.
-- Дату и счёт можно менять. Результат пишется в XSLD с разными ID.
-- XSLD = UN4PUBLIC.XSLD, GLOBAL TEMPORARY TABLE: весь скрипт выполнять в ОДНОЙ
-- сессии. Если запрос расхождений вернул 0 строк, проверьте, что в XSLD вообще есть
-- строки MIG_FAST / MIG_FC (при ON COMMIT DELETE ROWS они исчезают после commit).
-- =====================================================================
set serveroutput on timing on
whenever sqlerror continue

prompt === 1. Объекты валидны
select object_type, object_name, status, to_char(last_ddl_time,'yyyy-mm-dd hh24:mi') last_ddl
from user_objects
where object_name in ('PKG_SLD_UTIL','XSLD_COMPACT_STATS','XSLD_COMPACT_STATS_UK','TSLD_CONT_DEP')
order by 2,1;
select count(*) invalid_now from user_objects where status <> 'VALID';

prompt === 2. Сравнение сальдо: быстрое vs FC (счёт 2171, 4 аналитики, конец прошлого месяца)
declare
  v_dt date := trunc(sysdate,'mm') - 1;
begin
  delete from xsld where id in ('MIG_FAST','MIG_FC');
  dbms_output.put_line('fast start '||to_char(sysdate,'hh24:mi:ss'));
  un$sld.make(v_dt,'MIG_FAST','ACD1J','2171',' ','2905,2609,105520,9805');
  dbms_output.put_line('fast end / FC start '||to_char(sysdate,'hh24:mi:ss'));
  un$sld.make(v_dt,'MIG_FC','ACD1J','2171',' ','2905,2609,105520,9805', pOldMethod => true);
  dbms_output.put_line('FC end '||to_char(sysdate,'hh24:mi:ss'));
end;
/
prompt Расхождения (ожидаем 0 строк):
select nvl(a.cont,b.cont) cont, nvl(a.sc,b.sc) sc, nvl(a.dep,b.dep) dep,
       a.suma fast_suma, b.suma fc_suma, a.cant fast_cant, b.cant fc_cant
from (select * from xsld where id = 'MIG_FAST') a
full join (select * from xsld where id = 'MIG_FC') b
  on a.cont = b.cont and a.sc = b.sc and nvl(a.dep,-1) = nvl(b.dep,-1) and nvl(a.ap,'-') = nvl(b.ap,'-')
where nvl(a.suma,0) <> nvl(b.suma,0) or nvl(a.cant,0) <> nvl(b.cant,0);

prompt === 3. Онлайн-запись: проведите/измените/удалите тестовый документ в UNA и проверьте,
prompt     что строки по его счёту появились в TXSLD (TMDB_CM_TSLD_TR).
