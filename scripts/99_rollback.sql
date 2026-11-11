-- =====================================================================
-- 99_rollback.sql — откат к состоянию PROD до миграции.
-- Применять, если пересчёт не завершился / сальдо не сходится / нет места.
-- =====================================================================
set serveroutput on
alter session set ddl_lock_timeout = 300;

-- 1. Выключить онлайн-запись сальдо (как было на PROD) и снять блокировку проводок
alter trigger tmdb_cm_tsld_tr disable;
alter trigger tmdb_cm_restrict_dml_trg disable;

-- 2. Очистить частично заполненные таблицы сальдо (на PROD до миграции TXSLD была пустой)
truncate table txsld;
truncate table tsld;

-- 3. Вернуть исходный код пакета (копии сняты с PROD 11.11.2026)
-- выполнить оба файла копии пакета, снятой шагом P1 утилиты (папка sld_migrator\backups):
-- @<PROFILE>_pkg_sld_util_spec_<дата>.sql
-- @<PROFILE>_pkg_sld_util_body_<дата>.sql
show errors package body pkg_sld_util

-- 4. Новые объекты можно оставить (ни на что не влияют) или удалить:
-- drop table xsld_compact_stats purge;
-- drop index tsld_cont_dep;

-- 5. Задания: job 8 и job 13 НЕ менять. Запустить планировщик значением из снимка
--    (шаги 2–3 из 07_restore_jobs.sql):
-- alter system set job_queue_processes = 1000;
