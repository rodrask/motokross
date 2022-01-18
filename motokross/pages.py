from collections import Counter, defaultdict, namedtuple
from datetime import datetime, timedelta
import aiohttp_jinja2
from aiohttp_security import check_authorized
from aiohttp import web
import pytz

from motokross.config import *

UserRow = namedtuple('UserRow', ['user_id', 'timestamps', 'size'])


def get_time_str(timestamp, timezone):
    utc_datetime = datetime.fromtimestamp(timestamp, pytz.utc)
    return utc_datetime.astimezone(timezone).strftime('%H:%M:%S')


def get_delta(prev_ts, current_ts):
    if prev_ts > 0:
        return f' ({str(timedelta(seconds=current_ts - prev_ts))})'
    else:
        return ''


@aiohttp_jinja2.template('stat_table.jinja2')
async def get_stat_table(request):
    db = request.app[DB]
    data_dict = db.get_events(request.app[MIN_LAP])
    headers = ['# Гонщика', 'Кол-во отметок'] + request.app[TABLE_HEADERS]
    tz = request.app[TIMEZONE]

    user_rows = defaultdict(list)
    user_nums = Counter()
    user_last_ts = defaultdict(lambda: 0)
    control_points = request.app[CONTROL_POINTS]
    for point_id in control_points:
        for user_id, race_points in data_dict.items():
            if len(race_points) == 0:
                user_rows[user_id].append('--:--:--')
                continue
            log_ts, log_point_id = race_points[0]
            if point_id == log_point_id:
                ts_str = get_time_str(log_ts, tz)
                delta_str = get_delta(user_last_ts[user_id], log_ts)
                user_rows[user_id].append(f'{ts_str}{delta_str}')
                race_points.pop(0)
                user_nums[user_id] += 1
                user_last_ts[user_id] = log_ts
            else:
                user_rows[user_id].append('--:--:--')

    rows = [UserRow(user_id, timestamps, user_nums[user_id]) for user_id, timestamps in user_rows.items()]
    return {'rows': rows, 'headers': headers}


@aiohttp_jinja2.template('kp_stat_table.jinja2')
async def get_kp_stat_table(request):
    await check_authorized(request)
    db = request.app[DB]
    kp_id = request.match_info.get('kp_id',"")
    kp_data = []
    if kp_id:
        tz = request.app[TIMEZONE]
        prev_ts = None
        for p in db.get_kp_events(kp_id):
            if prev_ts is not None:
                delta = get_delta(p.timestamp, prev_ts)
            else:
                delta = '(--:--:--)'
            prev_ts = p.timestamp
            kp_data.append((p.racer, get_time_str(p.timestamp, tz), delta))
    kps = sorted(list(set(request.app[CONTROL_POINTS])))
    return {
        'headers': ["# Гонщика", "Время", "Интервал"],
        'kp_data': kp_data, 
        'kps': kps, 
        'current_kpp': kp_id, 
        'race_path':request.app[RACE_PATH]}

async def get_stat_csv(request):
    # await check_authorized(request)
    db = request.app[DB]
    tz = request.app[TIMEZONE]
    csv_path = request.app[DATA_DIR] / "result.csv"
    with open(csv_path, 'w', encoding='utf-8') as fp:
        for racer_id, kp_id, timestamp, user in db.get_raw_events():
            fp.write(f'{racer_id}\t{kp_id}\t{get_time_str(timestamp, tz)}\t{user}\n')
    return web.FileResponse(csv_path)
