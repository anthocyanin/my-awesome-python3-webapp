import asyncio
import os
import inspect
import logging
import functools
from urllib import parse
from aiohttp import web
from www.apis import APIError


# 创建带参数的装饰器
def get(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator


def post(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator

# --- 使用inspect模块中的signature方法来获取函数的参数，实现一些复用功能--
# inspect.Parameter 的类型有5种：
# POSITIONAL_ONLY		只能是位置参数
# KEYWORD_ONLY			关键字参数且提供了key
# VAR_POSITIONAL		相当于是 *args
# VAR_KEYWORD			相当于是 **kw
# POSITIONAL_OR_KEYWORD	可以是位置参数也可以是关键字参数


def get_required_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    # 如果url处理函数需要传入关键字参数，且默认是空的话，获取这个key
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    # 如果url处理函数需要传入关键字参数，获取这个key
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


def has_named_kw_args(fn):
    params = inspect.signature(fn).parameters
    # 判断是否有关键字参数
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    # 判断是否有关键字变长参数，VAR_KEYWORD对应**kw
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True


def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    # 判断是否存在一个参数叫做request，并且该参数要在其他普通的位置参数之后
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY
                      and param.kind != inspect.Parameter.VAR_KEYWORD):
            # 如果判断为True，则表明param只能是位置参数POSITIONAL_ONLY
            raise ValueError('request parameter must be the last named parameter in funtcion: %s%s' % (fn.__name__,
                                                                                                       str(sig)))
    return found

# RequestHandler目的就是从URL处理函数（如handlers.index）中分析其需要接收的参数，从web.request对象中获取必要的参数，
# 调用URL处理函数，然后把结果转换为web.Response对象，这样，就完全符合aiohttp框架的要求


class RequestHandler(object):

    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)
    # 1.定义kw对象，用于保存参数
    # 2.判断URL处理函数是否存在参数，如果存在则根据是POST还是GET方法将request请求内容保存到kw
    # 3.如果kw为空(说明request没有请求内容)，则将match_info列表里面的资源映射表赋值给kw；如果不为空则把命名关键字参数的内容给kw
    # 4.完善_has_request_arg和_required_kw_args属性

    async def __call__(self, request):
        kw = None
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest('Missing Content-Type.')
                ct = request.content_type.lower()
                if ct.startswith('application/json'):
                    params = await request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('Json body must be object.')
                    kw = params
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = await request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:
            kw = dict(**request.match_info)
        else:
            if not self._has_var_kw_arg and self._named_kw_args:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args:%s' % k)
                kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        if self._required_kw_args:
            for name in self._required_kw_args:
                if name not in kw:
                    return web.HTTPBadRequest('Missing argument: %s' % name)
        logging.info('call with args: %s' % str(kw))
        try:
            r = await self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)


def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))
    # INFO:root:add static /static/ => /Users/gonghuidepro/PycharmProjects/awesome-python3-webapp/www/static


def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get and @post is not defined in %s.' % str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info('add route %s %s => %s(%s)' % (method, path, fn.__name__, ', '.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app, fn))


def add_routes(app, module_name):
    n = module_name.rfind('.')  # app.py文件里面调用了add_routes(),并传入参数app和 handlers,而handlers.rfind('.')显然返回-1
    if n == (-1):
        mod = __import__(module_name, globals(), locals())  # 这一步相当于动态导入handlers模块
    else:
        name = module_name[n+1:]
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    logging.info(mod)
    # <module 'handlers' from '/Users/gonghuidepro/PycharmProjects/awesome-python3-webapp/www/handlers.py'>
    logging.info(dir(mod))
    # INFO:root:['APIError', 'APIPermissionError', 'APIResourceNotFoundError', 'APIValueError', 'Blog', 'COOKIE_NAME',
    # 'Comment', 'Page', 'User', '_COOKIE_KEY', '_RE_EMAIL', '_RE_SHA1', '__builtins__', '__cached__', '__doc__',
    # '__file__', '__loader__', '__name__', '__package__', '__spec__', 'api_blogs', 'api_create_blog', 'api_get_blog',
    #  'api_register_user', 'asyncio', 'authenticate', 'base64', 'check_admin', 'configs', 'cookie2user', 'get',
    # 'get_blog', 'get_page_index', 'hashlib', 'index', 'json', 'logging', 'manage_blogs', 'manage_create_blog',
    # 'next_id', 'post', 're', 'register', 'signin', 'signout', 'text2html', 'time', 'user2cookie', 'web', 'www']

    for attr in dir(mod):  # 返回handlers模块的属性、方法列表
        if attr.startswith('_'):  # 跳过特殊属性和私有属性
            continue
        fn = getattr(mod, attr)
        if callable(fn):
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)








































