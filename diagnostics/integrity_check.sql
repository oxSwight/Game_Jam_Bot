-- Диагностика целостности базы Game_Jam_Bot (задача C роадмапа app-for-rooms).
-- Только чтение, ничего не меняет. Запуск:
--   docker exec -i gamejam_bot-db-1 psql -U gamejam -d gamejam -f - < diagnostics/integrity_check.sql
-- или скопировать файл в контейнер и выполнить psql -f.

\echo '=== 1. Количество строк по таблицам ==='
select 'users' as tbl, count(*) from users
union all select 'applications', count(*) from applications
union all select 'logs', count(*) from logs
union all select 'player_code_counters', count(*) from player_code_counters;

\echo '=== 2. Дубликаты users по telegram_id (должно быть пусто; UNIQUE ix_users_telegram_id) ==='
select telegram_id, count(*) from users group by telegram_id having count(*) > 1;

\echo '=== 3. Дубликаты users по nickname / email (должно быть пусто; UNIQUE constraints) ==='
select 'nickname' as field, nickname as value, count(*) from users
  where nickname is not null group by nickname having count(*) > 1
union all
select 'email', email, count(*) from users
  where email is not null group by email having count(*) > 1;

\echo '=== 4. Больше одной активной (не rejected) заявки на пользователя (должно быть пусто) ==='
select user_id, count(*) from applications
  where status <> 'rejected' group by user_id having count(*) > 1;

\echo '=== 5. Дубликаты player_code (должно быть пусто; UNIQUE ix_applications_player_code) ==='
select player_code, count(*) from applications
  where player_code is not null group by player_code having count(*) > 1;

\echo '=== 6. player_code не из блока своей категории (перемешанные коды) ==='
with base as (
  select * from (values
    ('programming', 1000000), ('game_design', 2000000), ('art_2d', 3000000),
    ('art_3d', 4000000), ('audio', 5000000), ('management', 6000000)
  ) as t(category_id, code_base)
)
select a.id, a.main_category, a.player_code, b.code_base
from applications a join base b on b.category_id = a.main_category
where a.player_code is not null
  and (a.player_code < b.code_base or a.player_code >= b.code_base + 1000000);

\echo '=== 7. Счётчик отстаёт от максимального выданного кода (грозит дублем при следующей выдаче) ==='
with maxcodes as (
  select main_category, max(player_code) as max_code
  from applications where player_code is not null group by main_category
)
select m.main_category, m.max_code, c.last_code
from maxcodes m left join player_code_counters c on c.category_id = m.main_category
where c.last_code is null or c.last_code < m.max_code;

\echo '=== 8. Снапшот заявки разошёлся с users (nickname/email) ==='
select a.id, a.user_id, a.nickname as app_nick, u.nickname as user_nick,
       a.email as app_email, u.email as user_email
from applications a join users u on u.id = a.user_id
where a.status <> 'rejected'
  and (a.nickname is distinct from u.nickname or a.email is distinct from u.email);

\echo '=== 9. Сироты: заявки без пользователя / логи с несуществующей заявкой (FK должны не пускать) ==='
select 'app_without_user' as kind, a.id::text from applications a
  left join users u on u.id = a.user_id where u.id is null
union all
select 'log_dangling_app', l.id::text from logs l
  where l.application_id is not null
    and not exists (select 1 from applications a where a.id = l.application_id);

\echo '=== 10. Заявки с пустыми обязательными смысловыми полями ==='
select id, main_category, skill_category_id, experience_level, status
from applications
where coalesce(main_category, '') = '' or coalesce(skill_category_id, '') = ''
   or coalesce(experience_level, '') = '';

\echo '=== 11. Статусы вне ожидаемого набора ==='
select id, status from applications
where status not in ('pending_review', 'approved', 'rejected', 'waitlisted', 'invited');

\echo '=== 12. Версия миграций ==='
select version_num from alembic_version;
