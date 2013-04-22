from datetime import datetime, date, timedelta
from functools import update_wrapper
import calendar
import json

from bson.objectid import ObjectId

from flask import request, make_response, current_app


class JSONEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return int(calendar.timegm(obj.timetuple()))
        elif isinstance(obj, ObjectId):
            return str(obj)
        elif isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


def json_decoder(obj):
    for key, val in obj.items():
        if key in ('_id', 'user', 'org', 'cust'):
            if val is not None:
                val = ObjectId(val)
        elif key in ('users',):
            if isinstance(val, list):
                val = [ObjectId(k) for k in val]
        elif key in ('created', 'modified', 'last_login',):
            if isinstance(val, (float, int)):
                val = datetime.utcfromtimestamp(val)

        obj[key] = val

    return obj


class JSONSerializer(object):

    def encode(self, obj, fd=None):
        try:
            if fd:
                return json.dump(obj, fd, cls=JSONEncoder)
            else:
                return json.dumps(obj, cls=JSONEncoder)
        except (TypeError, ValueError), e:
            raise Exception(str(e))

    def decode(self, msg=None, fd=None):
        try:
            if msg:
                return json.loads(msg, object_hook=json_decoder)
            elif fd:
                return json.load(fd, object_hook=json_decoder)
        except (TypeError, ValueError), e:
            raise Exception(str(e))


def serialize(obj):
    return JSONSerializer().encode(obj)

def crossdomain(origin=None, methods=None, headers=None, max_age=21600,
        attach_to_all=True, automatic_options=True):
    if methods is not None:
        methods = ', '.join(sorted(x.upper() for x in methods))
    if headers is not None and not isinstance(headers, basestring):
        headers = ', '.join(x.upper() for x in headers)
    if not isinstance(origin, basestring):
        origin = ', '.join(origin)
    if isinstance(max_age, timedelta):
        max_age = max_age.total_seconds()

    def get_methods():
        if methods is not None:
            return methods

        options_resp = current_app.make_default_options_response()
        return options_resp.headers['allow']

    def decorator(f):
        def wrapped_function(*args, **kwargs):
            if automatic_options and request.method == 'OPTIONS':
                resp = current_app.make_default_options_response()
            else:
                resp = make_response(f(*args, **kwargs))
            if not attach_to_all and request.method != 'OPTIONS':
                return resp

            h = resp.headers

            h['Access-Control-Allow-Origin'] = origin
            h['Access-Control-Allow-Methods'] = get_methods()
            h['Access-Control-Max-Age'] = str(max_age)
            # if headers is not None:
            #     h['Access-Control-Allow-Headers'] = headers

            h['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
            return resp

        f.provide_automatic_options = False
        return update_wrapper(wrapped_function, f)
    return decorator

def run(app, host='0.0.0.0', port=8000):
    try:
        from gunicorn.app.base import Application

        class GunicornApp(Application):

            def __init__(self, options={}):
                '''__init__ method

                Load the base config and assign some core attributes.
                '''
                self.usage = None
                self.callable = None
                self.prog = None
                self.options = options
                self.do_load_config()

            def init(self, *args):
                '''init method

                Takes our custom options from self.options and creates a config
                dict which specifies custom settings.
                '''
                cfg = {}
                for k, v in self.options.items():
                    if k.lower() in self.cfg.settings and v is not None:
                        cfg[k.lower()] = v
                return cfg

            def load(self):
                return app

        options = {
            'bind': '%s:%s' % (host, port),
            }
        GunicornApp(options).run()

    except ImportError:
        app.run(host=host, port=port)
