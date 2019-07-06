import logging; logging.basicConfig(level=logging.INFO)
import asyncio
from aiohttp import web
import os
import json
import time
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import www.orm
from www.coroweb import add_routes, add_static
from www.config import configs
from www.handlers import cookie2user, COOKIE_NAME


def init_jinja2(app, **kw):
    logging.info('init jinja2...')
    options = dict(
        autoescape=kw.get('autoescape', True),
        block_start_string=kw.get('block_start_string', '{%'),
        block_end_string=kw.get('block_end_string', '%}'),
        variable_start_string=kw.get('variable_start_string', '{{'),
        variable_end_string=kw.get('variable_end_string', '}}'),
        auto_reload=kw.get('auto_reload', True)  # 当模板文件被修改后，下次请求加载该模板文件的时候会自动重新加载修改后的模板文件

    )
    path = kw.get('path', None)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')  # os模块获取路径信息
    logging.info('set jinja2 template path: %s' % path)
    # set jinja2 template path: /Users/gonghuidepro/PycharmProjects/awesome-python3-webapp/www/templates
    # Environment是jinjia2中的一个核心类，它的实例用来保存配置、全局对象以及模板文件的路径
    env = Environment(loader=FileSystemLoader(path), **options)
    # filters: 一个字典描述的filters过滤器集合, 如果非模板被加载的时候, 可以安全的添加或较早的移除.
    filters = kw.get('filters', None)
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    # 所有的一切是为了给app添加__templating__字段
    # 前面将jinja2的环境配置都赋值给env了，这里再把env存入app的dict中，这样app就知道要到哪儿去找模板，怎么解析模板。
    app['__templating__'] = env


# 这个函数的作用就是当有http请求的时候，通过logging.info输出请求的信息，其中包括请求的方法和路径
async def logger_factory(app, handler):
    async def logger(request):
        logging.info('Request: %s %s' % (request.method, request.path))
        return await handler(request)
    return logger


async def auth_factory(app, handler):
    async def auth(request):
        logging.info('check user: %s %s' % (request.method, request.path))
        request.__user__ = None
        cookie_str = request.cookies.get(COOKIE_NAME)
        if cookie_str:
            user = await cookie2user(cookie_str)
            if user:
                logging.info('set current user: %s' % user.email)
                request.__user__ = user
        if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
            return web.HTTPFound('/signin')
        return await handler(request)
    return auth


async def data_factory(app, handler):
    async def parse_data(request):
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = await request.json()
                logging.info('request json: %s' % str(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = await request.post()
                logging.info('request form: %s' % str(request.__data__))
        return await handler(request)
    return parse_data

# 请求对象request的处理工序流水线先后依次是：
# logger_factory->response_factory->RequestHandler().__call__->get或post->handler
# 对应的响应对象response的处理工序流水线先后依次是:
# 由handler构造出要返回的具体对象
# 然后在这个返回的对象上加上'__method__'和'__route__'属性，以标识别这个对象并使接下来的程序容易处理
# RequestHandler目的就是从请求对象request的请求content中获取必要的参数，调用URL处理函数,然后把结果返回给response_factory
# response_factory在拿到经过处理后的对象，经过一系列类型判断，构造出正确web.Response对象，以正确的方式返回给客户端
# 在这个过程中，只关心handler的处理，其他的都走统一通道，如果需要差异化处理，就在通道中选择适合的地方添加处理代码。
# 注：在response_factory中应用了jinja2来渲染模板文件


async def response_factory(app, handler):
    async def response(request):
        logging.info('Response handler....')
        r = await handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, dict):
            template = r.get('__template__')
            if template is None:
                resp = web.Response(body=json.dumps(r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                r['__user__'] = request.__user__
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        if isinstance(r, int) and 600 > r >= 100:
            return web.Response(r)
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and 600 > t >= 100:
                return web.Response(status=t, text=str(m))
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp
    return response


def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s小时前' % (delta // 3600)
    if delta < 604800:
        return u'%s天前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)


async def init(loop):
    await www.orm.create_pool(loop=loop, **configs.db)  # 首先先连接数据库
    # 连接数据库之后会根据aiohttp来构造一个app类
    # 把app类与线程绑定并为app类添加middlewares
    # middlewares(中间件)设置3个中间处理函数(都是装饰器)
    # middlewares中的每个factory接受两个参数，app 和 handler(即middlewares中的下一个handler)
    # 譬如这里logger_factory的handler参数其实就是auth_factory
    # middlewares的最后一个元素的handler会通过routes查找到相应的，就是routes注册的对应handler处理函数
    # 这是装饰模式的体现，logger_factory, auth_factory, response_factory都是URL处理函数前（如handler.index）的装饰功能
    app = web.Application(loop=loop, middlewares=[logger_factory, auth_factory, response_factory])
    # 注册模板
    init_jinja2(app, filters=dict(datetime=datetime_filter))
    add_routes(app, 'handlers')  # 注册url处理函数 这一步其实做了很多工作，
    add_static(app)  # 添加静态文件
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 8000)
    await site.start()
    print('Server started at http://127.0.0.1:8000...')
    return site


loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
