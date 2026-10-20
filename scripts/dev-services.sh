#!/bin/bash
# Start the local development services (MariaDB + 2x Redis) if they are not running. Dev sandbox only.
mkdir -p /run/mysqld && chown mysql:mysql /run/mysqld
mariadb-admin -uroot -pdevroot-only-local ping >/dev/null 2>&1 || {
  setsid nohup mysqld_safe --user=mysql --skip-syslog >/tmp/mysqld.log 2>&1 </dev/null &
  for i in $(seq 1 40); do mariadb-admin -uroot -pdevroot-only-local ping >/dev/null 2>&1 && break; sleep 1; done; }
for p in 11000 13000; do redis-cli -p $p ping >/dev/null 2>&1 || redis-server --port $p --save "" --daemonize yes >/dev/null; done
mariadb-admin -uroot -pdevroot-only-local ping; redis-cli -p 11000 ping; redis-cli -p 13000 ping
