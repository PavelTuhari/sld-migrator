-- =====================================================================
-- 06_enable_online.sql — сразу после успешного 05. Порядок важен:
-- сначала включаем запись в сальдо, потом снимаем блокировку проводок.
-- =====================================================================
whenever sqlerror exit failure rollback
alter session set ddl_lock_timeout = 300;

alter trigger tmdb_cm_tsld_tr enable;            -- проводки -> TXSLD/TSLD онлайн
alter trigger tmdb_cm_restrict_dml_trg disable;  -- пользователи снова могут проводить

select trigger_name, status from user_triggers
where trigger_name in ('TMDB_CM_TSLD_TR','TMDB_CM_RESTRICT_DML_TRG');
-- Ожидаем: TMDB_CM_TSLD_TR = ENABLED, TMDB_CM_RESTRICT_DML_TRG = DISABLED
