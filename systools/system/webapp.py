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
