#!/bin/bash
# Start MariaDB, Redis, the dev SMTP sink and the dev web server (idempotent). Dev sandbox only.
/home/claude/application-office/scripts/dev-services.sh >/dev/null 2>&1
python3 -c "import socket,sys;sys.exit(socket.socket().connect_ex(('127.0.0.1',1025)))" || \
  su frappe -c '(setsid nohup /home/frappe/frappe-bench/env/bin/python /home/claude/application-office/scripts/dev-mailsink.py >/tmp/mailsink.log 2>&1 </dev/null &)'
python3 -c "import socket,sys;sys.exit(socket.socket().connect_ex(('127.0.0.1',8000)))" || \
  su frappe -c 'cd ~/frappe-bench && (setsid nohup /home/frappe/fb.sh --site office.localhost serve --port 8000 --noreload >/tmp/serve.log 2>&1 </dev/null &)'
pgrep -f '[b]ench worker' >/dev/null || su frappe -c 'cd ~/frappe-bench && (setsid nohup /home/frappe/fb.sh worker --queue short,default,long >/tmp/worker.log 2>&1 </dev/null &)'
python3 -c "import socket,sys;sys.exit(socket.socket().connect_ex(('127.0.0.1',9000)))" || su frappe -c 'cd ~/frappe-bench && (PATH=/opt/node24/node_modules/.bin:$PATH setsid nohup node apps/frappe/socketio.js >/tmp/socketio.log 2>&1 </dev/null &)'
for i in $(seq 1 40); do curl -s -o /dev/null -H "Host: office.localhost:8000" http://127.0.0.1:8000/office-portal && echo "stack up" && exit 0; sleep 1; done; echo "web did not start"; exit 1
