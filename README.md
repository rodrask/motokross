**Установка зависимостей:**

pip install -r requirements.txt

**Запускать можно из командной строки:**

python server.py --data ./moto/data --config ./sample/config.json --port 8877

**Либо через docker-compose, используется переменная LOCAL_DATAPATH**

docker-compose build && docker-compose up -d

**Пример конфига для гонки:**

sample/config.json
