import argparse
import base64
import logging
from datetime import datetime
from pathlib import Path
import aiohttp_jinja2
import jinja2
import pytz
import qrcode
from aiohttp import web
from aiohttp_security import SessionIdentityPolicy
from aiohttp_security import (
    remember, forget, authorized_userid, permits,
    is_anonymous, has_permission, login_required
)
from aiohttp_security import setup as setup_security
from aiohttp_session import setup as setup_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet

from motokross.auth import auth_middleware, check_credentials, DictionaryAuthorizationPolicy
from motokross.config import *
from motokross.db import SqliteDb
from motokross.pages import get_kp_stat_table, get_stat_table, get_stat_csv
import os

def qr_code_for_url(url):
    return qrcode.make(url)

@aiohttp_jinja2.template('hello.jinja2')
async def hello(request):
    is_logged = not await is_anonymous(request)
    return {'race': request.app[RACE_PATH],
            'users':request.app[USER_DICT].keys(),
            'kpps':request.app[TABLE_HEADERS],
            'is_logged': is_logged}

def validate(user_id, timestamp, state_dict, min_lap=60 * 10):
    return timestamp - state_dict.get(user_id, 0) > min_lap


def write_log(user_id, timestamp, control_point, log_path):
    with open(log_path, 'a+') as fout:
        fout.write(f'{user_id}\t{timestamp}\t{control_point}\n')

@aiohttp_jinja2.template('mark.jinja2')
@login_required
async def mark_user(request):
    racer_id = request.match_info['user_id']
    app_state = request.app[APP_STATE]
    min_lap = request.app[MIN_LAP]
    timestamp = int(datetime.now().timestamp())

    user_id = await authorized_userid(request)
    control_point = request.app[USER_DICT][user_id].control_point

    if validate(racer_id, timestamp, app_state, min_lap):
        log_path = request.app[LOG_PATH]
        write_log(racer_id, timestamp, control_point, log_path)
        db = request.app[DB]
        db.save_event(racer_id, control_point, timestamp, user_id)
        app_state[racer_id] = timestamp
        return {'state': 'ok',
                'text': f'Гонщик {racer_id} отмечен'}
    else:
        return {'state': 'pause.png',
                'text': f'Гонщик {racer_id} уже учтен менее {min_lap // 60} минут назад'}


@aiohttp_jinja2.template('index.jinja2')
@login_required
async def index(request):
    is_admin = await permits(request, 'admin')
    username = await authorized_userid(request)
    control_point = request.app[USER_DICT][username].control_point
    
    return {'is_admin':is_admin, 'race_path': request.app[RACE_PATH], 
            'message': f"Пользователь: {username}, КП - {control_point}",
            'error_msg': request.query.get('msg','')}


@aiohttp_jinja2.template('login.jinja2')
async def do_login(request):
    is_logged = not await is_anonymous(request)
    if is_logged:
        return web.HTTPFound(request.app.router['index'].url_for())
    else:
        print(request.forwarded)
        return {'race_path':request.app[RACE_PATH],
                'ref_url': request.query.get('ref_url',''),
                'msg': request.query.get('msg','')}


async def login(request):
    form = await request.post()
    username = form.get('username')
    password = form.get('password')
    ref_url = form.get('ref_url') or request.app.router['index'].url_for()
    verified = await check_credentials(request.app[USER_DICT], username, password)
    if verified:
        response = web.HTTPFound(ref_url)
        await remember(request, response, username)
        return response
    return web.HTTPFound(request.app.router['do_login']\
        .url_for().with_query({'msg':"Неправильный логин/пароль"}))

@login_required
async def logout(request):
    response = web.HTTPFound(request.app.router['hello'].url_for())
    await forget(request, response)
    return response

@aiohttp_jinja2.template('qr_codes.jinja2')
@has_permission('admin')
async def generate_qr(request):
    n = min(300, int(request.match_info['n']))
    path_part = request.app[RACE_PATH]
    host = request.host
    scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
    qr_dir = request.app[QR_DIR]

    racers = []
    for i in range(0, n + 1):
        url = f'{scheme}://{host}/{path_part}/mark/{i}'
        qr_code_for_url(url).save(f'{qr_dir}/qr_{path_part}_{i}.png')
        racers.append((i, url, f'/qr/qr_{path_part}_{i}.png'))
    return {'racers': racers}

@has_permission('admin')
async def wipe_race(request):
    log_path = request.app[LOG_PATH]
    db = request.app[DB]
    db.wipe()
    open(log_path, 'w').close()
    request.app[APP_STATE].clear()
    response = web.Response(
        text=f'Файл {log_path} очищен\nБаза {db.db_path} очищена',
        content_type='text/html',
    )
    return response


def build_web_app(data_dir, timezone, config_path):
    logging.info(f"Using data dir {data_dir}")
    app = web.Application(middlewares=[auth_middleware])
    data_path = Path(data_dir)

    qr_dir = data_path / 'qr'
    qr_dir.mkdir(parents=True, exist_ok=True)


    race_name, user_map, control_points, table_titles, min_lap = load_config(config_path)
    logging.info(f"Race name: {race_name}")
    logging.info(f"Users: {list(user_map.keys())}")
    logging.info(f"Control points:{table_titles}")

    log_path = data_path / f'{race_name}.log'
    log_path.touch()
    
    db_path = data_path / f"{race_name}.sqlite"
    db = SqliteDb(db_path)

    app[DATA_DIR] = data_path
    app[QR_DIR] = str(qr_dir)
    app[DB] = db

    app[RACE_PATH] = race_name
    app[LOG_PATH] = str(log_path)
    app[MIN_LAP] = min_lap * 60
    app[TIMEZONE] = pytz.timezone(timezone)
    app[APP_STATE] = db.get_race_state()
    app[USER_DICT] = user_map
    app[TABLE_HEADERS] = table_titles
    app[CONTROL_POINTS] = control_points

    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)

    storage = EncryptedCookieStorage(secret_key, cookie_name='API_SESSION')
    setup_session(app, storage)

    policy = SessionIdentityPolicy()
    setup_security(app, policy, DictionaryAuthorizationPolicy(user_map))

    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('templates'))

    app_prefix = '/' + race_name
    if add_static():
        app.add_routes([
        web.static('/qr', qr_dir),
        web.static('/static', './static')])

    app.add_routes([
        web.post(app_prefix + '/login', login, name='login'),
        web.get("/" , hello, name='hello'),
        web.get(app_prefix , index, name='index'),
        web.get(app_prefix + '/do_login', do_login, name='do_login'),
        web.get(app_prefix + '/logout', logout, name='logout'),
        web.get(app_prefix + '/generate_qr/{n}', generate_qr, name='qr'),
        web.get(app_prefix + '/stat.html', get_stat_table, name='stat'),
        web.get(app_prefix + '/kp_stat/{kp_id}', get_kp_stat_table, name='kp_stat'),
        web.get(app_prefix + '/kp_stat', get_kp_stat_table, name='kp_stat_default'),
        web.get(app_prefix + '/stat.csv', get_stat_csv),
        web.get(app_prefix + '/mark/{user_id}', mark_user, name='mark'),
        web.get(app_prefix + '/wipe', wipe_race, name='wipe')
    ])
    return app

def add_static():
    return bool(int(os.getenv("PROD_ENV", "0")))

def parser():
    parser = argparse.ArgumentParser(description='Params for mark service.')
    parser.add_argument('--data', help='path to data dir')
    parser.add_argument('--config', help='json config file with users and control points')
    parser.add_argument('--timezone', help='Race timezone', default='Asia/Yekaterinburg')
    parser.add_argument('--port', help='Http port', type=int, default=8877)
    return parser

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                            format="%(asctime)s %(levelname)s %(threadName)s %(name)s %(message)s")
    args = parser().parse_args()
    app = build_web_app(args.data, args.timezone, args.config)
    web.run_app(app, port=args.port)
