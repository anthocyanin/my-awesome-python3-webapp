# my-awesome-python3-webapp
这个项目是学完廖雪峰网站python教程后的节课项目练习。基本上是照抄了一边代码，并理解了一遍。
和源代码稍有区别的有以下几点：
一：协程写法从@asyncio.coroutine + yield from 换成 async和await。
二：from aiohttp import web 的app运行写法变了从    
    srv = yield from loop.create_server(app.make_handler(), '127.0.0.1', 9000)
    换成    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 8000)
    await site.start()
三：静态文件使用的vue，Jquery，Uikit版本不同，所以部分html页面的标签属性有所更改，不然页面显示不出来。
