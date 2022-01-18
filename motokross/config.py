from motokross.db import User
import json

DATA_DIR = 'data_dir'

QR_DIR = 'qr_dir'

RACE_PATH = 'race_path'

DB = 'db'

MIN_LAP = 'min_lap'

LOG_PATH = 'log_path'

APP_STATE = 'state'

TIMEZONE = 'race_timezone'

USER_DICT = 'users'

TABLE_HEADERS = 'table_titles'

CONTROL_POINTS = 'control_points'

def load_config(json_path):
    users = {}
    with open(json_path, 'r', encoding='utf-8') as fin_config:
        conf_dict = json.load(fin_config)
        race_name = conf_dict.get('race', 'race')
        min_lap  = conf_dict.get('min_lap', 5)
        users = {u.username:u for u in load_users(conf_dict.get('users', []))}
        points, titles = load_track(conf_dict.get('race_track', []))

    return race_name, users, points, titles, min_lap


def load_users(json_array):
    for user_dict in json_array:
        user = User(user_dict['username'],
                    user_dict['password'],
                    user_dict.get('permissions', 'user'),
                    user_dict['control_point'])
        yield user

def load_track(json_array):
    control_points = []
    table_titles = []
    for race_point in json_array:
        control_points.append(race_point['id'])
        table_titles.append(race_point['title'])
    return (control_points, table_titles)
