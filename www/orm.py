import asyncio
import logging
import aiomysql


def log(sql, args=()):
    logging.info('SQL:%s' % sql)


# 创建一个全局的连接池，每个http请求都从池中获得数据库连接
async def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 20),
        minsize=kw.get('minsize', 1),
        loop=loop
    )


async def select(sql, args, size=None):
    log(sql, args)  # 每次执行查询前，记录sql语句日志
    global __pool
    async with __pool.get() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql.replace('?', '%s'), args or ())  # 应该是执行带参数的sql语句，先是把？占位符替换成%s。
            if size:
                rs = await cur.fetchmany(size)
            else:
                rs = await cur.fetchall()
        logging.info('rows returned:%s' % len(rs))
        return rs


async def execute(sql, args, autocommit=True):
    log(sql)
    async with __pool.get() as conn:
        if not autocommit:
            await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?', '%s'), args)
                affected = cur.rowcount
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.roolback()
            raise
        return affected


# 函数定义：添加sql语句的占位符:?，在metaclass中的底层运用
# 根据参数数量生成SQL占位符'?'列表，
def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    return ', '.join(L)
# 定义不同类型的衍生Field，表的不同列的字段的类型不一样


class Field(object):
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    # 此处代码的作用是打印Field类的实例时，返回的内容，或者说呈现将要打印的结果
    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)


class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)


class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)


class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)


class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)


class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)
# 定义Model的元类
# 所有的元类都继承自type，ModelMetaclass元类定义了所有Model基类（继承ModelMetaclass）的子类实现的操作

# ModelMetaclass的工作主要是为一个数据库表映射成一个封装的类做准备
# 读取具体子类（user）的映射信息
# 创建类时，排除对Model的修改
# 在当前类中查找所有的类属性（attrs），如果找到Field属性，就将其保存到__mappings__的dict中
# 同时从类属性中删除Field(防止实例属性遮住类的同名属性)
# 将数据库表名保存到__table__中
# 完成这些工作就可以在Model中定义各种数据库的操作方法


class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        # 排除Model本身
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        # 获取table名称:因为继承了dict所以有get方法，如果没有该类属性则默认tableName=类名
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        mappings = dict()  # 获取所有的field(包含主键在内的field)，字典，
        fields = []  # 存储主键外的field列表
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('  found mapping: %s===>%s' % (k, v))
                mappings[k] = v
                if v.primary_key:  # 找到主键
                    if primaryKey:  # 判断一下，防止出现两次主键
                        raise Exception('Duplicate primary key for field: %s' % k)
                    primaryKey = k
                else:
                    fields.append(k)  # 不是主键的字段都加入fields列表里去
        if not primaryKey:  # 再判断一下，防止没有主键。
            raise Exception('Primary key not found.')
        for k in mappings.keys():
            attrs.pop(k)  # 这里将类的原来类属性删除。
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))  # fields 这里是一个列表，['email','image']  escaped_fields将要得到 ['`email`', '`image`']
        attrs['__mappings__'] = mappings  # 这里其实是增加了一个__mapping__属性。保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey  # 主键属性名
        attrs['__fields__'] = fields  # 除主键外的属性名
        # 构造默认的SELECT, INSERT, UPDATE和DELETE语句, 这里__select__,__update__,__delete__都是格式化的字符串。
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default  # 这行代码啥玩意啊
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        sql = [cls.__select__]  # 类的__select__属性是一个长字符串代表这sql语句，放到列表里当作一个元素，再构造sql变量
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []  # args变成空列表
        orderBy = kw.get('orderBy', None)  # kw.get('orderBy') 得到关键字参数orderBy对应的值，又赋值给了orderBy变量
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)  # 此时sql变量将有三个元素了
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)  # limit值赋予args
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = await select(' '.join(sql), args)  # 调用select函数查询，传入参数sql字符串，args
        return [cls(**r) for r in rs]

    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)  # 调用select函数查询,传入参数sql字符串，args默认，size=1。前面是在准备sql语句
        logging.info(rs)  # 返回一个[{'_num_': 3}]字典列表
        if len(rs) == 0:
            return None
        return rs[0]['_num_']  # 把_num_值返回

    @classmethod
    async def find(cls, pk):
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s' % rows)

    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)
















































































