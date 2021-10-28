# my-blog-python3-webapp
这个项目是学完廖雪峰官方网站python教程后的结课项目练习。第一遍基本上是照抄了一遍代码，理解的不是太好，因为他这个博客项目没有选用Django，Flask这样的框架，很多模块都是自己开发，比如Orm，过滤器。所以第一遍结束后实在是一知半解，仅能根据后台Log日志记录，大致理解代码的执行流程和处理逻辑。不过后来学习了Django，又练习了小米商城项目后。再回头看理解的好多了。而且也认识到不用框架比用框架能学到更多东西。
下面是和源代码稍有区别的几点：
- 一：协程写法从@asyncio.coroutine + yield from 换成 async和await。
- 二：from aiohttp import web 的app运行写法变了从srv = yield from loop.create_server(app.make_handler(), '127.0.0.1', 9000)换成    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 8000)
    await site.start()
- 三：部分html页面的标签属性有所更改，不然页面显示不出来。
