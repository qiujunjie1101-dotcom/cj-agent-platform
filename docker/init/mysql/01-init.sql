-- 首次启动 MySQL 容器时自动执行（仅数据卷为空时运行一次）
-- MYSQL_DATABASE 会先创建 cj；这里显式兜底并设置字符集。

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS `cj`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `cj`;

-- 开发期健康检查用表，可按需删除
CREATE TABLE IF NOT EXISTS `health_check` (
  `id`         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
